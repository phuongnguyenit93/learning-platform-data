# Chứng minh tính đầy đủ và tránh sinh trùng kết quả

Khi bài toán yêu cầu **liệt kê nghiệm**, một chương trình chạy ra nhiều kết quả đúng vẫn có thể **sai**: nó có thể bỏ sót một nghiệm hoặc in cùng một nghiệm nhiều lần. Với bài toán tổ hợp, truy hồi, duyệt đồ thị và sinh phương án, cần chứng minh đồng thời **tính hợp lệ, tính đầy đủ, tính duy nhất và tính kết thúc**. Việc loại trùng chỉ an toàn khi biết rõ thế nào là *hai nghiệm giống nhau* theo đặc tả.

## 1. Bốn trách nhiệm của một thuật toán liệt kê

Đặt `S` là tập mọi nghiệm hợp lệ **phân biệt theo yêu cầu đề bài**; `R` là danh sách các kết quả thuật toán phát ra (danh sách có thể có phần tử trùng).

1. **Hợp lệ (soundness):** Mọi kết quả `r∈R` đều là nghiệm trong `S`. Không xuất kết quả sai điều kiện.
2. **Đầy đủ (completeness):** Với **mọi** `s∈S`, thuật toán sẽ phát ra ít nhất một kết quả đại diện cho `s`. Không bỏ sót nghiệm.
3. **Duy nhất (no duplicates):** Mỗi nghiệm phân biệt trong `S` được phát ra **đúng một lần**. Một danh sách như `[(1,2),(1,2)]` có thể hợp lệ và đầy đủ nếu `S={(1,2)}`, nhưng không duy nhất.
4. **Kết thúc (termination):** Các vòng lặp hay lời gọi đệ quy tiến tới trạng thái dừng hữu hạn. Nếu có nhánh chạy vô hạn trước khi đến nghiệm khác thì chưa bảo đảm tính đầy đủ thực tế.

Chứng minh **hợp lệ + đầy đủ** có thể chỉ cho biết **tập** kết quả là đúng. Ta phải chứng minh thêm **không trùng** vì thuật toán phát ra một **danh sách**, nơi số lần xuất hiện có ý nghĩa.

### “Trùng” theo chỉ số, giá trị hay thứ tự?

Xét mảng `[1,1,2]` tại vị trí `0,1,2` và yêu cầu tổng bằng `3`:

| Ý nghĩa của một nghiệm | Những nghiệm phân biệt | Số lượng |
| --- | --- | --- |
| **Cặp chỉ số** `(i,j)`, `i<j` | `(0,2)`, `(1,2)` | 2 |
| **Cặp giá trị** không xét thứ tự | Chỉ `(1,2)` | 1 |
| **Cặp vị trí có thứ tự** `(i,j)`, `i≠j` | `(0,2),(2,0),(1,2),(2,1)` | 4 |

Dùng `Set` để gộp hai cặp cùng giá trị là đúng ở hàng thứ hai, nhưng **làm mất nghiệm** ở hàng đầu. Do đó phải định nghĩa phép tương đương `x~y` (hai biểu diễn được xem là cùng một nghiệm) **trước khi** quyết định loại trùng.

Những câu hỏi cần trả lời: thứ tự có quan trọng không; mỗi vị trí được dùng mấy lần; hai vị trí chứa cùng giá trị có tạo ra hai nghiệm riêng không; kết quả là tập giá trị, dãy có thứ tự, danh sách chỉ số hay đường đi? Ví dụ **tổ hợp** `[1,2]` và `[2,1]` được coi là một, còn **hoán vị** có thể coi là hai.

## 2. Chọn một biểu diễn chuẩn (canonical representation)

Biểu diễn chuẩn cho phép mỗi đối tượng toán học có một “tên” duy nhất:

- Cặp chỉ số không xét thứ tự: bắt buộc `i<j`.
- Cặp giá trị không xét thứ tự: viết `(min(x,y),max(x,y))`.
- Tổ hợp: các vị trí được chọn tăng nghiêm ngặt; dãy giá trị đã chọn được in theo thứ tự tăng không giảm sau khi sắp xếp input.
- Đường đi: biểu diễn bằng **toàn bộ dãy đỉnh/cạnh** nếu chính đường đi là nghiệm. Hai đường khác nhau không trở thành một chỉ vì cùng đích.

Tạo biểu diễn chuẩn **không tự bảo đảm đủ nghiệm**. Nó chỉ mở đường cho chứng minh mỗi nghiệm có một đường sinh chuẩn và không có hai đường chuẩn phát cùng kết quả.

Có hai phương pháp phổ biến:

1. **Ngăn trùng khi sinh:** Đặt ràng buộc về thứ tự chỉ số, hoặc chọn một đại diện cho mỗi nhóm giá trị trùng ở cùng mức đệ quy. Giảm số nhánh vô ích, nhưng cần chứng minh không bỏ mất nghiệm.
2. **Sinh rồi loại trùng:** Chuẩn hóa kết quả, lưu vào `Set`. Thường dễ dùng làm baseline kiểm chứng, nhưng vẫn tốn thời gian sinh các nhánh lặp và bộ nhớ giữ kết quả; kiểu khóa phải có ngữ nghĩa bằng nhau phù hợp.

Không được dùng cùng một chiến lược cho mọi bài nếu định nghĩa nghiệm khác nhau.

## 3. Chứng minh với vòng lặp: tất cả cặp chỉ số `i<j`

Không gian cặp chỉ số là `{(i,j) | 0≤i<j<n}`. Cách liệt kê trực tiếp là:

```java
// Đoạn minh họa cấu trúc duyệt; n và isValid do bài toán định nghĩa.
for (int i = 0; i < n; i++) {
    for (int j = i + 1; j < n; j++) {
        if (isValid(i, j)) {
            // Phát ra cặp chỉ số (i, j).
        }
    }
}
```

**Hợp lệ:** Chỉ phát khi `isValid` đúng; điều kiện vòng trong bảo đảm hai vị trí khác nhau và `i<j`.

**Đầy đủ:** Lấy **một cặp hợp lệ tùy ý** `(p,q)` với `p<q`. Vòng ngoài đi qua `i=p`; trong lượt đó, vòng trong đi qua `j=q`. Vì vậy cặp `(p,q)` chắc chắn được kiểm tra và được phát ra.

**Không trùng theo chỉ số:** Mỗi lượt lặp gắn với duy nhất một cặp `(i,j)`. Hai lượt khác nhau không thể cùng mang bộ chỉ số đó. Cặp đảo `(j,i)` không được sinh vì không thỏa `i<j`.

**Kết thúc:** Các biến nguyên `i,j` tăng dần trong các khoảng hữu hạn; số lần kiểm tra khi duyệt hết là `n(n−1)/2=Θ(n²)`, bộ nhớ duyệt phụ `O(1)` nếu in dần.

Đây **không phải** chứng minh chống trùng **theo giá trị**. Với `[1,1,2]`, hai cặp chỉ số `(0,2)` và `(1,2)` khác nhau nhưng đều cho cặp giá trị `(1,2)`. Khi yêu cầu cặp giá trị duy nhất, phải có thêm quy tắc gộp/không sinh trùng.

Mặt khác, nếu đề yêu cầu xuất **mọi cặp chỉ số** bất kể giá trị, output có `Θ(n²)` cặp, nên riêng việc ghi kết quả đã cần `Ω(n²)` thời gian. Không thể có thuật toán in toàn bộ output ấy trong `O(n)`.

## 4. Khuôn chứng minh tổng quát: một nghiệm, một đường sinh

Để chứng minh một bộ sinh nghiệm, có thể nghĩ đến ánh xạ từ **đường thực thi đi đến lệnh emit** sang **nghiệm được phát ra**.

**Hợp lệ:** Chỉ ra bất biến giữ sau mỗi bước. Ví dụ “các chỉ số đang chọn tăng nghiêm ngặt”, “đường đi hiện tại không lặp đỉnh”, “tổng đã tính bằng tổng các giá trị thực sự chọn”. Tại `emit`, bất biến cùng điều kiện dừng phải suy ra mọi ràng buộc của nghiệm.

**Đầy đủ:** Lấy nghiệm hợp lệ **bất kỳ** `s`. Dựng một đường lựa chọn cụ thể đưa thuật toán đến `s`: mỗi bước lấy phần tử tiếp theo trong biểu diễn chuẩn của `s`. Chứng minh điều kiện sinh nhánh không chặn đường này. Nếu thuật toán loại bỏ miền ứng viên, phải chứng minh **không còn nghiệm chưa phát** trong miền bị bỏ. Với cây đệ quy có thể lập luận quy nạp theo số lựa chọn còn lại.

**Không trùng:** Giả sử hai đường thực thi khác nhau phát cùng một nghiệm. Tìm **độ sâu/vòng lặp đầu tiên** nơi chúng chọn khác nhau, rồi chứng minh quy tắc chuẩn chỉ cho phép một trong hai lựa chọn đại diện. Tức là hai đường phát nghiệm phải không thể trùng theo định nghĩa tương đương của đề.

**Kết thúc:** Chỉ ra một đại lượng hữu hạn giảm nghiêm ngặt (số phần tử còn chọn, kích thước khoảng hai con trỏ, số vị trí chưa duyệt...) hoặc một chỉ số tăng trong phạm vi hữu hạn.

Câu “đã thử mọi trường hợp” không thay thế được bước đầy đủ: cần chỉ ra chính xác **mỗi nghiệm tùy ý xuất hiện ở đâu**.

## 5. Ví dụ A: Liệt kê mỗi cặp **giá trị** có tổng bằng target đúng một lần

**Đặc tả:** `int[] input` không null, có thể rỗng, âm hoặc chứa nhiều phần tử giống nhau; `int target`. In mỗi cặp giá trị `(x,y)` với `x≤y`, tồn tại hai vị trí **khác nhau** mang giá trị `x,y` và có tổng toán học `x+y=target`. Không làm thay đổi input.

Baseline để đối chiếu: duyệt mọi `i<j`; nếu tổng đúng, chuẩn hóa `(min,max)` và đưa vào `Set<Pair>`. Baseline có `Θ(n²)` phép kiểm tra nhưng rõ ràng về tính đầy đủ.

Cách nhanh hơn khi chỉ cần **cặp giá trị**: sao chép mảng, sắp xếp tăng dần; đặt `left=0`, `right=n−1`; xét `sum=(long)a[left]+a[right]`.

| Điều kiện | Cập nhật | Vì sao an toàn |
| --- | --- | --- |
| `sum<target` | `left++` | Vì mảng tăng dần, với mọi `j` giữa `left` và `right` đều có `a[left]+a[j]≤sum<target`. Không có nghiệm sử dụng giá trị đầu trái trong đoạn còn lại |
| `sum>target` | `right--` | Với mọi `i` trong đoạn còn lại, `a[i]+a[right]≥sum>target`. Không có nghiệm sử dụng giá trị đầu phải trong đoạn còn lại |
| `sum==target` | Phát `(x,y)=(a[left],a[right])`; bỏ mọi bản sao `x` từ trái và `y` từ phải | Với `x` cố định, chỉ có `y=target−x` tạo được tổng đúng. Mọi bản sao `x` hoặc `y` chỉ tái tạo cùng **cặp giá trị** đã phát |

**Chứng minh đầy đủ:** Lấy một cặp giá trị hợp lệ `(x,y)` chưa được phát. Ở bước có tổng nhỏ, giá trị đầu trái bị bỏ không thể ghép với bất kỳ giá trị còn lại để đạt target; do đó không thể bỏ mất `(x,y)`. Bước có tổng lớn tương tự với giá trị đầu phải. Ở bước có tổng đúng, mọi cặp dùng giá trị `x` hoặc `y` và đạt target đều phải có cùng cặp giá trị `(x,y)` vừa phát, nên bỏ các bản sao chỉ xóa các cách biểu diễn trùng. Theo đó một nghiệm chưa phát không thể biến mất vì các bước trên. Khoảng tiếp tục thu hẹp, nên mọi nghiệm cuối cùng được phát hoặc không tồn tại.

**Chứng minh hợp lệ:** Chỉ phát khi tổng đúng; `left<right` bảo đảm hai **vị trí** khác nhau. Do đã sắp tăng dần, cặp luôn có `x≤y`. Khi `x=y`, vẫn phải có ít nhất hai bản sao ở hai vị trí để vòng lặp cho phép phát.

**Chứng minh duy nhất:** Sau khi phát `(x,y)`, mọi bản sao `x` ở đầu trái bị bỏ. Do đó về sau giá trị đầu trái không thể là `x` nữa. Vì đối tác của mỗi `x` là duy nhất `target−x`, cặp giá trị `(x,y)` không thể xuất hiện lần nữa.

**Kết thúc:** Mỗi vòng tăng `left` hoặc giảm `right` ít nhất một, khiến khoảng `right-left` giảm cho đến khi `left≥right`.

Độ phức tạp gồm sao chép `O(n)`, sắp xếp `T_sort(n)` (thường `O(n log n)`), pha hai con trỏ `O(n)` và lưu `k` kết quả `O(k)`. Bản sao tốn `O(n)` bộ nhớ, giữ nguyên input. Nếu cần **chỉ số gốc** thay vì **giá trị**, cách này phải đổi để giữ thông tin chỉ số; bỏ trùng theo giá trị là **sai đặc tả** nếu các cặp chỉ số khác nhau đều là nghiệm.

**Tràn số:** Hai giá trị `int` có thể cộng tràn trước khi so sánh với target. Ép một toán hạng sang `long` trước phép cộng để đánh giá tổng toán học đúng. Phép tính phần bù `target−x` cũng có thể tràn nếu thực hiện bằng `int`.

## 6. Ví dụ B: Backtracking sinh tổ hợp có phần tử trùng

Cho `[1,1,2]` và `k=2`. Đề yêu cầu mọi tổ hợp **giá trị** không xét thứ tự, nhưng vẫn được dùng hai bản sao của số `1` vì chúng ở **hai vị trí**:

```text
[1, 1]
[1, 2]
```

Không được in `[1,2]` hai lần, nhưng cũng không được bỏ `[1,1]`.

Quy tắc: sắp xếp mảng; gọi đệ quy với `start` là chỉ số nhỏ nhất được phép chọn tiếp; trong vòng lặp của **một lời gọi** từ `i=start`, bỏ `a[i]` nếu `i>start && a[i]==a[i-1]`; sau khi chọn tại `i`, đệ quy với `start=i+1`. **Bỏ trùng ở cùng độ sâu**, không bỏ bản sao trên toàn bộ cây.

Cụ thể, tại độ sâu đầu tiên `start=0` chỉ chọn nhánh bắt đầu bởi số `1` ở chỉ số 0; nhánh chọn số `1` ở chỉ số 1 sẽ trùng đại diện. Nhưng trong nhánh đã chọn chỉ số 0, bước tiếp theo có `start=1` được chọn số `1` ở chỉ số 1: vậy `[1,1]` không bị mất.

**Hợp lệ:** Chỉ số đã chọn tăng nghiêm ngặt, nên không dùng một vị trí hai lần; chỉ phát khi đã chọn đủ `k` phần tử. Vì input sắp tăng, dãy giá trị xuất ra tăng không giảm.

**Đầy đủ:** Lấy một tổ hợp giá trị hợp lệ tùy ý, viết theo thứ tự tăng không giảm. Ở độ sâu đầu tiên, chọn **bản sao đầu tiên còn khả dụng** của giá trị cần chọn. Chọn bản sao sớm nhất không làm giảm số vị trí còn lại so với bản sao muộn hơn, nên mọi phần đuôi của tổ hợp vẫn có thể được xây dựng. Lặp ở độ sâu kế tiếp sẽ đi đến tổ hợp ấy. Điều kiện skip chỉ bỏ các bản sao muộn hơn tại **cùng một độ sâu**, không bỏ đường chuẩn này.

**Không trùng:** Giả sử hai đường đệ quy khác nhau phát cùng dãy giá trị. Tại độ sâu đầu tiên chúng chọn khác chỉ số, nhưng hai giá trị được chọn phải bằng nhau vì đầu ra bằng nhau. Quy tắc skip ở cùng độ sâu cho phép **chỉ một** chỉ số đại diện của mỗi giá trị — mâu thuẫn. Vì vậy mỗi tổ hợp được phát đúng một lần.

**Kết thúc:** Mỗi lời gọi con tăng `start`, giảm số phần tử còn thiếu, nên đệ quy hữu hạn. `k=0` có đúng **một tổ hợp rỗng** `[]`; `k>n` không có tổ hợp.

Trường hợp xấu nhất (mọi giá trị khác nhau) có `C(n,k)` tổ hợp. Chỉ việc sao chép từng nghiệm `k` phần tử đã cần `Ω(k·C(n,k))` thời gian; nếu lưu hết kết quả thì bộ nhớ output cũng cùng bậc. Không có cách “tối ưu” vượt qua cận dưới phải xuất chính output đó.

**Sai lầm điển hình:** Đổi điều kiện thành `i>0 && a[i]==a[i-1]` sẽ cấm chọn bản sao ở độ sâu sâu hơn, làm mất `[1,1]`. Ngược lại, không skip ở cùng độ sâu sẽ in cùng một tổ hợp từ nhiều vị trí chứa giá trị như nhau.

## 7. Chương trình Java 17+ hoàn chỉnh

Chương trình gồm bộ sinh cặp giá trị duy nhất, bộ sinh tổ hợp duy nhất và baseline duyệt mọi cặp để đối chiếu. Mã dùng `record Pair`, có ngữ nghĩa so sánh bằng **giá trị các trường**, phù hợp cho `HashSet`. Lưu vào file **UniqueEnumerationDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class UniqueEnumerationDemo {
    // Cặp ở dạng chuẩn low <= high.
    record Pair(int low, int high) {
        @Override
        public String toString() {
            return "(" + low + ", " + high + ")";
        }
    }

    static List<Pair> uniqueValuePairs(int[] input, int target) {
        int[] a = input.clone(); // Không đổi input.
        Arrays.sort(a);
        List<Pair> answer = new ArrayList<>();
        int left = 0;
        int right = a.length - 1;

        while (left < right) {
            long sum = (long) a[left] + a[right];
            if (sum < target) {
                left++;
            } else if (sum > target) {
                right--;
            } else {
                int x = a[left];
                int y = a[right];
                answer.add(new Pair(x, y));

                // Bỏ mọi bản sao của cặp giá trị đã phát.
                while (left < right && a[left] == x) {
                    left++;
                }
                while (left < right && a[right] == y) {
                    right--;
                }
            }
        }
        return answer;
    }

    static List<List<Integer>> uniqueCombinations(int[] input, int k) {
        if (k < 0) {
            throw new IllegalArgumentException("k must be nonnegative");
        }
        int[] a = input.clone();
        Arrays.sort(a);
        List<List<Integer>> answer = new ArrayList<>();
        choose(a, 0, k, new ArrayList<>(), answer);
        return answer;
    }

    private static void choose(int[] a, int start, int missing,
                               List<Integer> path,
                               List<List<Integer>> answer) {
        if (missing == 0) {
            answer.add(new ArrayList<>(path));
            return;
        }
        // Giữ đủ vị trí cho các phần tử còn phải chọn.
        for (int i = start; i <= a.length - missing; i++) {
            if (i > start && a[i] == a[i - 1]) {
                continue; // Chỉ bỏ trùng ở cùng độ sâu.
            }
            path.add(a[i]);
            choose(a, i + 1, missing - 1, path, answer);
            path.remove(path.size() - 1); // Backtrack.
        }
    }

    // Oracle: thử mọi cặp chỉ số, chuẩn hóa và gộp theo giá trị.
    static List<Pair> bruteOracle(int[] a, int target) {
        Set<Pair> found = new HashSet<>();
        for (int i = 0; i < a.length; i++) {
            for (int j = i + 1; j < a.length; j++) {
                if ((long) a[i] + a[j] == target) {
                    found.add(new Pair(Math.min(a[i], a[j]),
                                       Math.max(a[i], a[j])));
                }
            }
        }
        List<Pair> answer = new ArrayList<>(found);
        answer.sort(Comparator.comparingInt(Pair::low)
                              .thenComparingInt(Pair::high));
        return answer;
    }

    // Mọi mảng dài 0..5 từ các giá trị {-2,-1,0,1,2}
    // và target trong [-4,4]: tổng cộng 35_154 trường hợp.
    static void checkSmallCases() {
        int variations = 1;
        for (int n = 0; n <= 5; n++) {
            for (int encoded = 0; encoded < variations; encoded++) {
                int[] a = new int[n];
                int code = encoded;
                for (int i = 0; i < n; i++) {
                    a[i] = code % 5 - 2;
                    code /= 5;
                }
                for (int target = -4; target <= 4; target++) {
                    List<Pair> expected = bruteOracle(a, target);
                    List<Pair> actual = uniqueValuePairs(a, target);
                    if (!expected.equals(actual)) {
                        throw new AssertionError(
                            Arrays.toString(a) + ", target=" + target);
                    }
                }
            }
            variations *= 5;
        }
    }

    public static void main(String[] args) {
        System.out.println("Value pairs: "
            + uniqueValuePairs(
                new int[]{-2, 5, 5, 0, 3, 1, 2, -2, 0, 3, 1}, 3));
        System.out.println("Repeated value: "
            + uniqueValuePairs(new int[]{2, 2, 2}, 4));
        System.out.println("Single position: "
            + uniqueValuePairs(new int[]{2}, 4));
        System.out.println("Unique 2-combinations: "
            + uniqueCombinations(new int[]{1, 1, 2}, 2));
        System.out.println("Choose zero: "
            + uniqueCombinations(new int[]{1, 1, 2}, 0));
        System.out.println("Overflow guard: "
            + uniqueValuePairs(
                new int[]{Integer.MAX_VALUE, Integer.MAX_VALUE}, -2));

        checkSmallCases();
        System.out.println("Small exhaustive check: OK (35154 cases)");
    }
}
```

Dùng JDK 17 trở lên:

```bash
javac -encoding UTF-8 UniqueEnumerationDemo.java
java UniqueEnumerationDemo
```

Stdout:

```text
Value pairs: [(-2, 5), (0, 3), (1, 2)]
Repeated value: [(2, 2)]
Single position: []
Unique 2-combinations: [[1, 1], [1, 2]]
Choose zero: [[]]
Overflow guard: []
Small exhaustive check: OK (35154 cases)
```

**Diễn giải đầu ra:**

- Ba cặp giá trị trong ví dụ đầu tiên đều xuất **một lần** dù mỗi giá trị có thể xuất hiện ở nhiều vị trí.
- Mảng `[2,2,2]` sinh đúng một cặp `(2,2)`, do tồn tại **ít nhất hai vị trí**; mảng `[2]` không thể tạo cùng cặp.
- Tổ hợp `[1,1]` được giữ lại nhờ skip đúng *cùng độ sâu*; `[1,2]` không bị lặp.
- `k=0` cho danh sách chứa một tổ hợp rỗng `[[]]`. Điều này khác danh sách nghiệm trống `[]`.
- Hai `Integer.MAX_VALUE` có tổng toán học rất lớn, không phải `-2`; phép tính `long` ngăn kết quả sai do tràn `int`.
- Số bộ input trong phép đối chiếu là `(1+5+25+125+625+3125)×9=35.154`. Test có thể tìm phản ví dụ, nhưng **không thay thế** chứng minh đúng với mọi input.

**Lưu ý Java:** `HashSet<Pair>` hoạt động theo các trường `low, high` do `record` tự có `equals` và `hashCode`. `HashSet<int[]>` mặc định so sánh mảng theo tham chiếu, nên không dùng nó để loại các mảng nội dung giống nhau nếu chưa bọc bằng kiểu so sánh theo nội dung.

## 8. Cắt nhánh an toàn khác với bỏ trùng

Với backtracking, một nhánh có thể bị bỏ vì:

- **Không thể có nghiệm:** Ví dụ cần chọn thêm `r` phần tử nhưng còn ít hơn `r` vị trí — việc duyệt nhánh đó vô ích. Đó là lý do có cận `i <= a.length - missing` trong chương trình.
- **Chỉ tạo nghiệm đã có đại diện:** Ví dụ chọn bản sao thứ hai của giá trị `1` tại **cùng một độ sâu** trong cây sinh tổ hợp giá trị.
- **Không thể cải thiện nghiệm tối ưu:** Chỉ hợp lệ nếu đề yêu cầu tìm nghiệm tốt nhất và có cận chứng minh nhánh không thể tốt hơn. Nếu đề yêu cầu **tất cả nghiệm**, không được loại một nghiệm hợp lệ chỉ vì “kém tối ưu”.

Điều kiện cắt nhánh phải kèm một mệnh đề chắc chắn: “Mọi phần mở rộng của trạng thái này đều không hợp lệ, hoặc mọi nghiệm có thể có đã được đại diện bởi một nhánh còn giữ”. Không thể suy ra chỉ từ cảm giác “khả năng thấp”.

**Phản ví dụ:** Khi tìm tổ hợp có tổng `target` với các giá trị có thể âm, cắt ngay khi tổng tạm thời vượt target sẽ bỏ sót nghiệm. Phần tử âm chọn sau có thể giảm tổng. Quy tắc cắt dựa vào tổng chỉ an toàn nếu có các giả định/bất đẳng thức bảo đảm không thể quay lại target.

### Cảnh báo với visited trong đồ thị

Nếu chỉ kiểm tra **có đường đi hay không**, đánh dấu `visited[vertex]` toàn cục thường hợp lý. Nhưng nếu liệt kê **mọi đường đi đơn** từ `s` đến `t`, hai đường hợp lệ khác nhau có thể đi qua cùng một đỉnh trung gian. Dùng `visited` toàn cục có thể chặn đường thứ hai và **mất tính đầy đủ**.

Khi liệt kê mọi đường đi đơn, trạng thái cấm lặp đỉnh thường phải gắn với **đường đi hiện tại**, được hoàn tác khi backtrack. “Trùng trạng thái trung gian” không đồng nghĩa “trùng kết quả hoàn chỉnh”; muốn loại trùng đường đi phải so sánh theo đúng dãy đỉnh/cạnh nếu đó là định nghĩa nghiệm.

Tương tự, `memo[state]` có thể đúng cho bài **đếm** số cách nếu công thức tổng hợp đầy đủ, nhưng không tự cho phép bỏ các nhánh khác nhau khi cần **liệt kê** mọi cách cụ thể.

## 9. Chi phí phải tính cả kích thước output

Một lời giải có thể sinh kết quả duy nhất mà vẫn rất chậm đơn giản vì có **rất nhiều nghiệm cần xuất**.

| Bài toán | Khối lượng cần xét hoặc xuất | Điều cần lưu ý |
| --- | --- | --- |
| Tất cả cặp chỉ số `i<j` | `C(n,2)=n(n−1)/2` | Nếu cần xuất tất cả, thời gian xuất đã `Ω(n²)` |
| Cặp giá trị duy nhất tổng bằng target | Tối đa `O(n)` cặp khác nhau sau sắp xếp | Pha quét hai con trỏ `O(n)`; cộng chi phí sort và output |
| Tổ hợp chọn `k` từ `n` phần tử phân biệt | `C(n,k)` nghiệm, mỗi nghiệm dài `k` | Chỉ sao chép/xuất nghiệm đã cần `Ω(k·C(n,k))` |
| Sinh rộng rồi gộp `Set` | Số **nhánh đã sinh** có thể lớn hơn nhiều số nghiệm duy nhất | Tính cả công tạo bản sao, chuẩn hóa, băm và bộ nhớ tập |

Nếu cần giữ toàn bộ `K` kết quả, mỗi kết quả dài `L` phần tử, bộ nhớ lưu đáp án ít nhất `Ω(K·L)`. Nếu có thể xử lý/stream từng kết quả, bộ nhớ thêm có thể thấp hơn, nhưng **thời gian xuất** không biến mất. Không nên ghi `O(n)` cho một giải pháp mà riêng lượng kết quả là cấp số tổ hợp.

## 10. Lỗi thường gặp và cách tự kiểm

- **Chưa xác định quan hệ tương đương.** Gộp các cặp chỉ số khác nhau thành một cặp giá trị dù đề yêu cầu mọi cặp chỉ số.
- **Đồng nhất “đã thăm” với “đã có nghiệm”.** Đặc biệt nguy hiểm khi liệt kê đường đi hoặc liệt kê mọi cách đến một trạng thái.
- **Bỏ giá trị trùng ở tất cả các độ sâu.** Khi sinh tổ hợp từ `[1,1,2]` có thể làm mất `[1,1]`. Quy tắc đúng phải phụ thuộc `start` của lời gọi hiện tại.
- **Chỉ nói “không bỏ sót” mà không xây được đường đến nghiệm bất kỳ.** Chứng minh đầy đủ cần lập luận riêng cho mỗi điều kiện skip/prune.
- **Dùng cấu trúc Set sai ngữ nghĩa.** Mảng Java không tự so sánh bằng nội dung; cần `record`, danh sách có `equals` thích hợp hoặc wrapper.
- **Quên trường hợp hai giá trị bằng nhau.** Cặp `(x,x)` cần hai vị trí nếu không được chọn lặp một vị trí.
- **Bỏ qua tràn số.** So sánh tổng/hiệu `int` có thể sinh false positive/false negative.
- **Quên chi phí output và copy kết quả.** Tránh trùng không thể vượt qua cận dưới kích thước kết quả.

**Checklist chứng minh trước khi nộp:**

1. Viết chính xác tập nghiệm và định nghĩa trùng của đề.
2. Nêu bất biến của vòng lặp/đệ quy; chứng minh kết quả phát ra hợp lệ.
3. Lấy **nghiệm tùy ý** và chỉ ra đường duyệt không bị skip, chứng minh đầy đủ.
4. Giả sử hai đường khác nhau phát cùng nghiệm, tìm lựa chọn khác nhau đầu tiên và chứng minh quy tắc chuẩn ngăn điều ấy.
5. Chỉ ra đại lượng tiến triển bảo đảm kết thúc.
6. Kiểm input rỗng, một phần tử, toàn phần tử bằng nhau, số âm, giới hạn kiểu số, `k=0`, `k>n`, nhiều nghiệm/không nghiệm.
7. Đối chiếu với baseline trên input nhỏ và ước tính thời gian, bộ nhớ theo **kích thước output**.

## 11. Tự luyện

**Bài 1 — Đúng đối tượng cần liệt kê.** Với `[1,1,2,2]` và target `3`, chứng minh có **bốn** cặp chỉ số `i<j` nhưng chỉ **một** cặp giá trị `(1,2)`. Vì sao dùng `Set<Pair>` sẽ sai nếu đề yêu cầu cặp chỉ số?

**Bài 2 — Skip theo độ sâu.** Với `[1,1,2,2]` và `k=2`, hãy liệt kê `[1,1]`, `[1,2]`, `[2,2]`. Dựng cây lựa chọn và giải thích vì sao điều kiện `i>start` là thiết yếu.

**Bài 3 — Chứng minh loại trừ.** Với mảng tăng dần, từ `a[left]+a[right]<target` hãy chứng minh không có `j` thuộc đoạn đang xét sao cho `a[left]+a[j]=target`. Chỉ ra vì sao không được dùng cùng suy luận khi input chưa sắp xếp.

**Bài 4 — Đường đi.** Tạo một đồ thị có ít nhất hai đường đi đơn khác nhau từ `s` đến `t` qua cùng một đỉnh. Chứng minh việc dùng `visited` toàn cục có thể làm mất một đường; nêu bất biến cần có khi backtrack.

**Bài 5 — Cận dưới output.** Có `C(20,10)=184.756` tổ hợp chọn 10 từ 20 phần tử khác nhau. Giải thích vì sao không thể in đầy đủ từng tổ hợp trong thời gian `O(20)`.

**Tiêu chí hoàn thành:** Với bất kỳ thuật toán liệt kê nào, bạn có thể giải thích một cách kiểm chứng được **vì sao không có nghiệm sai, không thiếu nghiệm, không trùng nghiệm, thuật toán luôn kết thúc**, đồng thời đánh giá chi phí duyệt, loại trùng và xuất kết quả theo đúng định nghĩa của bài.
