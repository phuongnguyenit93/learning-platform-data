# Quy nạp theo kích thước đầu vào và cấu trúc lời giải

> **Chủ đề:** Computer Science Algorithms → Tính đúng và chi phí.  
> **Mục tiêu:** Biết viết chứng minh tính đúng của thuật toán dựa trên kích thước đầu vào, cấu trúc dữ liệu và cấu trúc của nghiệm; nhận ra giả thiết quy nạp cần thiết, tính dừng và trách nhiệm của bước ghép.

## 1. Quy nạp chứng minh điều gì?

Chạy thử một thuật toán trên vài bộ dữ liệu chỉ cho thấy những bộ đó có kết quả mong đợi. **Chứng minh tính đúng** phải bảo đảm kết luận đúng cho *mọi đầu vào thỏa tiền điều kiện*. Quy nạp là công cụ tự nhiên khi lời giải của một bài toán được tạo bằng lời giải của những bài toán nhỏ hơn.

Một thuật toán đệ quy thường có ba lớp cần giải thích:

1. **Trường hợp cơ sở:** bài toán nhỏ nhất được xử lý trực tiếp và đúng.
2. **Bước đệ quy:** mọi lời gọi con nhận bài toán nhỏ hơn và hợp lệ, nên được phép sử dụng kết luận của giả thiết quy nạp.
3. **Bước xây dựng kết quả:** kết hợp kết quả các lời gọi con theo cách bảo đảm hậu điều kiện của bài toán lớn hơn.

Câu “lời gọi đệ quy đúng nên cả thuật toán đúng” thiếu bước 3. Ví dụ, dù hai nửa của mảng đã được sắp xếp đúng, một hàm trộn làm mất phần tử vẫn sai.

Cần tách ba khái niệm:

- **Đúng bộ phận (*partial correctness*):** nếu thuật toán kết thúc, đầu ra thỏa đặc tả.
- **Dừng (*termination*):** mọi lần chạy hợp lệ đều kết thúc sau hữu hạn bước.
- **Đúng toàn phần (*total correctness*):** vừa đúng bộ phận, vừa dừng.

Một thuật toán luôn dừng vẫn có thể trả sai; một thuật toán chỉ trả đúng khi dừng vẫn có thể lặp vô hạn. Ngoài ra, **độ phức tạp thời gian/bộ nhớ** là vấn đề khác: thuật toán đúng và dừng có thể không đủ nhanh.

## 2. Cách phát biểu mệnh đề quy nạp

Giả sử `solve` xử lý đầu vào có kích thước nguyên không âm `n`. Ta thường chọn mệnh đề:

> `P(n)`: Với **mọi** đầu vào hợp lệ có kích thước `n`, `solve` kết thúc và trả kết quả đúng theo đặc tả.

Từ **“mọi”** rất quan trọng. Đầu vào đệ quy thường là một đoạn con không bắt đầu ở `0`, một cây con không cùng hình dạng cây gốc, hoặc một trạng thái DP khác với trạng thái ban đầu. Giả thiết quy nạp chỉ được áp dụng nếu phát biểu đủ tổng quát.

### 2.1. Quy nạp thường

- **Cơ sở:** chứng minh `P(0)` hoặc `P(1)` tùy miền đầu vào.
- **Giả thiết:** giả sử `P(k)` đúng.
- **Bước:** dùng `P(k)` và cấu trúc thuật toán để chứng minh `P(k+1)`.

Kiểu này phù hợp khi bài toán cỡ `k+1` chỉ phụ thuộc bài toán cỡ `k`. Nếu công thức dựa vào `n-1` và `n-2`, cần có đủ cơ sở và giả thiết phù hợp.

### 2.2. Quy nạp mạnh

- **Cơ sở:** chứng minh mọi trường hợp nhỏ nhất.
- **Giả thiết:** giả sử `P(m)` đúng cho **tất cả** kích thước hợp lệ `m < n`.
- **Bước:** từ lời giải đúng của những bài toán có kích thước nhỏ hơn `n`, chứng minh `P(n)`.

Đây là cách trình bày thuận tiện cho chia để trị, quy hoạch động và đệ quy theo cây có các nhánh kích thước khác nhau. Quy nạp thường và mạnh tương đương về sức chứng minh đối với các mệnh đề trên số tự nhiên; khác biệt chủ yếu nằm ở sự tiện lợi khi diễn đạt giả thiết.

### 2.3. Chọn thước đo giảm

“Kích thước” không nhất thiết là biến tên `n`. Ví dụ:

| Bài toán | Thước đo để quy nạp/chứng minh dừng |
|---|---|
| Xử lý mảng `[lo, hi)` | Số phần tử `hi - lo` |
| Tìm kiếm nhị phân | Độ dài miền chưa loại `hi - lo` |
| Đệ quy trên cây | Số nút cây con hoặc cấu trúc cây con |
| Chia dãy thành đoạn nhỏ | Độ dài mỗi đoạn con |
| Bài toán trạng thái | Số quyết định còn lại, hoặc một thứ tự trạng thái có hướng |
| Đệ quy nhiều tham số | Tổng không âm hoặc bộ tham số theo thứ tự từ điển có chặn dưới |

Thước đo dùng để chứng minh dừng phải **giảm nghiêm ngặt trong mọi lời gọi đệ quy**, thuộc một tập không có chuỗi giảm vô hạn (ví dụ số nguyên không âm). Nếu thuật toán gọi lại chính trạng thái cũ, không thể viện dẫn quy nạp trên trạng thái đó.

## 3. Quy nạp theo độ dài: tổng của một đoạn mảng

Bài toán: cho mảng `a` và đoạn nửa mở `[lo, hi)`, trả tổng các phần tử từ chỉ số `lo` tới `hi-1`. Đoạn rỗng có tổng bằng `0`.

Lưu thành **RangeSumProof.java**:

```java
public class RangeSumProof {
    static long sum(int[] a, int lo, int hi) {
        if (a == null || lo < 0 || hi < lo || hi > a.length) {
            throw new IllegalArgumentException("Invalid array range");
        }
        if (lo == hi) {
            return 0L;
        }
        return (long) a[lo] + sum(a, lo + 1, hi);
    }

    public static void main(String[] args) {
        int[] a = {4, -1, 7};
        System.out.println("Sum: " + sum(a, 0, a.length));
        System.out.println("Empty: " + sum(a, 1, 1));
    }
}
```

```bash
javac -encoding UTF-8 RangeSumProof.java
java RangeSumProof
```

```text
Sum: 10
Empty: 0
```

**Mệnh đề:** `P(n)` phát biểu rằng với mọi mảng và mọi đoạn hợp lệ có độ dài `n = hi-lo`, `sum(a, lo, hi)` trả chính xác tổng các phần tử trên đoạn đó.

**Cơ sở (`n=0`):** `lo==hi`, trả `0`, đúng với tổng của đoạn rỗng.

**Giả thiết quy nạp:** `P(n-1)` đúng với mọi đoạn dài `n-1`.

**Bước (`n>0`):** hàm trả `a[lo] + sum(a, lo+1, hi)`. Đoạn con `[lo+1, hi)` vẫn hợp lệ, có `n-1` phần tử. Theo giả thiết, lời gọi con trả tổng chính xác từ `a[lo+1]` tới `a[hi-1]`. Cộng `a[lo]` được tổng cần tìm. Vậy `P(n)` đúng.

**Dừng:** mỗi lần gọi, `hi-lo` giảm đúng `1`, cuối cùng bằng `0`.

**Chi phí:** mỗi lời gọi làm `O(1)` thao tác ngoài lời gọi con; `T(n)=T(n-1)+O(1)`, nên thời gian `O(n)` và ngăn xếp lời gọi `O(n)`.

**Bài học:** nếu phát biểu mệnh đề chỉ cho các đoạn dạng `[0,n)`, giả thiết không đủ mạnh để áp dụng cho `[lo+1,hi)`. Khi chứng minh thuật toán, phải chọn hậu điều kiện đúng với các **đối tượng thật sự được đưa vào lời gọi con**.

## 4. Quy nạp cấu trúc trên dữ liệu đệ quy

**Quy nạp cấu trúc (*structural induction*)** phù hợp khi dữ liệu được xây từ các thành phần nhỏ cùng loại. Một cây nhị phân hữu hạn gồm:

- `Empty`: cây rỗng; hoặc
- `Node(value, left, right)`: một gốc và hai cây con hữu hạn.

Muốn chứng minh tính chất `Q(t)` đúng cho **mọi** cây `t`, ta làm như sau:

1. Chứng minh `Q(Empty)`.
2. Giả sử `Q(left)` và `Q(right)` đúng, chứng minh `Q(Node(value,left,right))`.

Không cần hai cây con có kích thước bằng nhau. Đây là quy nạp theo **cách cây được cấu tạo**, có thể viết tương đương thành quy nạp mạnh trên số nút.

### 4.1. Ví dụ: đếm số nút

Lưu thành **TreeSizeProof.java** (dùng `record` có trong Java 17):

```java
public class TreeSizeProof {
    record Node(int value, Node left, Node right) {}

    static int size(Node tree) {
        if (tree == null) {
            return 0;
        }
        return 1 + size(tree.left()) + size(tree.right());
    }

    public static void main(String[] args) {
        Node tree = new Node(
            8,
            new Node(3, null, null),
            new Node(10, new Node(9, null, null), null)
        );
        System.out.println("Nodes: " + size(tree));
        System.out.println("Empty nodes: " + size(null));
    }
}
```

```bash
javac -encoding UTF-8 TreeSizeProof.java
java TreeSizeProof
```

```text
Nodes: 4
Empty nodes: 0
```

Cây ví dụ:

```text
      8
     / \
    3  10
       /
      9
```

**Mệnh đề `Q(t)`:** `size(t)` trả đúng số nút thuộc cây hữu hạn `t`.

- **Cơ sở:** cây rỗng có `0` nút; hàm trả `0`.
- **Giả thiết:** hàm đếm đúng số nút của `left` và `right`.
- **Bước cấu trúc:** cây `Node` có đúng `1` gốc, các nút của cây con trái và các nút của cây con phải. Ba phần này không giao nhau. Vì thế `1 + size(left) + size(right)` chính là số nút toàn cây.

**Dừng:** trên cây hữu hạn, mỗi lời gọi chỉ nhận một cây con thật sự; độ sâu giảm dần theo đường đi từ gốc đến lá. Với `N` nút, thời gian `O(N)`, bộ nhớ ngăn xếp `O(h)` với `h` là chiều cao cây (`O(N)` trong trường hợp cây lệch).

**Điều kiện cần nêu:** dữ liệu thực sự là cây hữu hạn, không phải đồ thị có chu trình; nếu một nút trỏ lại tổ tiên, mã đệ quy này có thể không dừng. Với cây cực lớn, biểu diễn kết quả bằng `int` cũng phải được kiểm tra giới hạn.

Quy nạp cấu trúc còn dùng cho cây cú pháp biểu thức, danh sách liên kết đệ quy, JSON/AST và các loại dữ liệu đại số khác. Với kiểu có nhiều dạng node, cần có **trường hợp chứng minh cho từng constructor**.

## 5. Chia để trị: chứng minh luôn cả bước ghép

Với merge sort, mỗi lời gọi chia một đoạn thành hai nửa, sắp xếp hai nửa rồi trộn. Mệnh đề đúng cần đủ **hai thuộc tính**:

1. Đoạn kết quả được sắp xếp không giảm.
2. Đoạn kết quả chứa **đúng đa tập phần tử ban đầu**, kể cả số lần xuất hiện mỗi giá trị; các vị trí ngoài đoạn không đổi.

Nếu chỉ chứng minh thuộc tính thứ nhất, một chương trình thay toàn bộ phần tử bằng số `0` cũng có thể thỏa “không giảm” dù hoàn toàn không sắp xếp đúng.

Lưu thành **MergeSortProof.java**:

```java
import java.util.Arrays;

public class MergeSortProof {
    static void mergeSort(int[] a) {
        int[] buffer = new int[a.length];
        sort(a, buffer, 0, a.length);
    }

    // Đoạn đang xét là [lo, hi).
    static void sort(int[] a, int[] buffer, int lo, int hi) {
        if (hi - lo <= 1) {
            return;
        }

        int mid = lo + (hi - lo) / 2;
        sort(a, buffer, lo, mid);
        sort(a, buffer, mid, hi);

        int i = lo, j = mid, write = lo;
        while (i < mid && j < hi) {
            if (a[i] <= a[j]) {
                buffer[write++] = a[i++];
            } else {
                buffer[write++] = a[j++];
            }
        }
        while (i < mid) buffer[write++] = a[i++];
        while (j < hi) buffer[write++] = a[j++];

        System.arraycopy(buffer, lo, a, lo, hi - lo);
    }

    public static void main(String[] args) {
        int[] a = {5, -1, 5, 2, 0};
        mergeSort(a);
        System.out.println(Arrays.toString(a));
    }
}
```

```bash
javac -encoding UTF-8 MergeSortProof.java
java MergeSortProof
```

```text
[-1, 0, 2, 5, 5]
```

### 5.1. Chứng minh bằng quy nạp mạnh trên độ dài

Đặt `P(n)`:

> Với mọi mảng và đoạn hợp lệ `[lo,hi)` có `hi-lo=n`, `sort(a,buffer,lo,hi)` kết thúc, tạo đoạn không giảm, bảo toàn đa tập phần tử và không thay giá trị bên ngoài đoạn.

**Cơ sở `n=0` hoặc `n=1`:** đoạn vốn đã được sắp xếp và hàm không thay đổi dữ liệu.

**Giả thiết:** `P(k)` đúng cho tất cả `k<n`.

**Bước `n>=2`:**

1. `mid` chia đoạn thành hai đoạn có độ dài `floor(n/2)` và `ceil(n/2)`. Cả hai đều từ `1` tới `n-1`, nên áp dụng được giả thiết.
2. Sau hai lời gọi đệ quy, mỗi nửa đã có thứ tự, chứa đúng phần tử của nửa ban đầu.
3. Khi trộn, hai con trỏ `i` và `j` chỉ vào phần tử nhỏ nhất chưa lấy của mỗi nửa. Chọn phần tử nhỏ hơn ở hai đầu tức là chọn phần tử nhỏ nhất chưa lấy của **toàn bộ** đoạn.
4. Mỗi lần trộn chỉ sao chép một phần tử và tăng đúng một con trỏ; vòng cuối sao chép toàn bộ phần tử còn lại. Vì vậy không mất/nhân đôi phần tử.
5. `System.arraycopy` chỉ ghi vào `[lo,hi)`. Kết quả vừa được sắp xếp vừa bảo toàn các phần tử, nên `P(n)` đúng.

**Bất biến vòng trộn:** phần đã ghi của `buffer` luôn là các phần tử đã lấy từ hai nửa, theo đúng số lượng, và có thứ tự không giảm. Bất biến này chứng minh **bước ghép** mà quy nạp cấp trên đang dựa vào.

**Dừng:** với `n>=2`, cả hai lời gọi nhỏ hơn `n`, còn các vòng `while` tăng con trỏ hữu hạn.

**Chi phí:** `T(n)=T(floor(n/2))+T(ceil(n/2))+O(n)`, nên thời gian `O(n log n)`. Buffer kích thước `n` dùng `O(n)` bộ nhớ phụ; độ sâu ngăn xếp `O(log n)`. Truy hồi về thời gian cần chứng minh riêng với mệnh đề đúng về kết quả.

## 6. Quy nạp theo cấu trúc của lời giải tối ưu

Trong quy hoạch động (*dynamic programming*), trạng thái thường mô tả bài toán con, nhưng **vì sao công thức chuyển cho nghiệm tối ưu?** Lập luận phải đi qua cách cấu tạo *nghiệm hoàn chỉnh*.

Ví dụ: có các mệnh giá nguyên **dương**, mỗi mệnh giá được dùng không giới hạn lần. Tìm số đồng ít nhất để tạo tổng `x`. Đặt `OPT(x)` là số đồng ít nhất, hoặc `+∞` nếu không tạo được.

Công thức:

- `OPT(0) = 0`.
- Với `x > 0`, `OPT(x) = 1 + min { OPT(x-c) | c là mệnh giá, c <= x }`; dùng quy ước `1 + ∞ = ∞`.

### 6.1. Tại sao truy hồi đúng? Cần hai chiều

**Chiều tạo nghiệm:** với một mệnh giá `c` và nghiệm tối ưu cho `x-c`, thêm một đồng `c` được nghiệm hợp lệ cho `x`, nên `OPT(x)` không lớn hơn số đồng của bất kỳ ứng viên hữu hạn nào được tạo.

**Chiều bao phủ nghiệm:** với bất kỳ nghiệm tối ưu cho `x>0` dùng `k` đồng, chọn một đồng `c` của nghiệm. Bỏ đồng đó còn một nghiệm cho `x-c` có `k-1` đồng. Vì `OPT(x-c) <= k-1`, ứng viên `1+OPT(x-c) <= k=OPT(x)`. Vậy phép `min` đã xét một lựa chọn không kém nghiệm tối ưu.

Hai chiều suy ra công thức bằng nhau. Nếu không có nghiệm, không tồn tại quyết định `c` dẫn đến trạng thái con khả thi, nên giá trị là `∞`. Điều kiện **mệnh giá dương** bảo đảm `x-c<x`, là điểm tựa cho quy nạp lẫn tính dừng.

### 6.2. Vì sao cách tính bảng DP đúng?

Giả sử tính lần lượt `dp[0]`, `dp[1]`, ..., `dp[W]` bằng công thức trên:

- Cơ sở: `dp[0]=0=OPT(0)`.
- Giả thiết quy nạp mạnh: `dp[y]=OPT(y)` cho mọi `0<=y<x`.
- Bước: mọi `c>0` nên `x-c<x`; theo giả thiết, từng `dp[x-c]` đã đúng. Phép lấy `min` trong code do đó tính đúng vế phải của truy hồi, bằng `OPT(x)`.

Như vậy, chứng minh có **hai tầng**: (1) công thức mô hình hóa mọi nghiệm tối ưu; (2) chương trình tính đúng công thức theo thứ tự trạng thái.

**Phản ví dụ cho tham lam:** với các đồng `{1,3,4}` và tổng `6`, chọn đồng lớn nhất trước được `4+1+1` (3 đồng), nhưng tối ưu là `3+3` (2 đồng). Quy nạp không thể cứu một công thức chuyển sai hoặc một chiến lược tự ý bỏ khả năng.

**Giới hạn mô hình:** nếu mỗi đồng chỉ được dùng một lần, trạng thái cần thêm chỉ số món/đồng còn khả dụng. Công thức trên mô tả bài toán *không giới hạn số lần dùng*, không thể áp dụng nguyên vẹn cho phiên bản 0/1. Nếu đặt giá trị “vô cực” bằng số nguyên lớn trong code, phải tránh tràn ở phép cộng `1`.

## 7. Tìm kiếm nhị phân: bất biến và thước đo giảm

Đệ quy theo kích thước không phải cách duy nhất biểu diễn quy nạp. Với vòng lặp, **bất biến** là mệnh đề đúng sau số bước bất kỳ, chứng minh bằng quy nạp theo số lần lặp. Thước đo giảm bổ sung chứng minh dừng.

Ví dụ tìm chỉ số đầu tiên có `a[i] >= target` trên một mảng đã **sắp xếp không giảm**. Nếu không có, trả `a.length`.

Lưu thành **LowerBoundProof.java**:

```java
public class LowerBoundProof {
    static int lowerBound(int[] a, int target) {
        int lo = 0;
        int hi = a.length;

        while (lo < hi) {
            int mid = lo + (hi - lo) / 2;
            if (a[mid] < target) {
                lo = mid + 1;
            } else {
                hi = mid;
            }
        }
        return lo;
    }

    public static void main(String[] args) {
        int[] a = {1, 2, 2, 2, 5, 9};
        System.out.println(lowerBound(a, 2));
        System.out.println(lowerBound(a, 4));
        System.out.println(lowerBound(a, 10));
    }
}
```

```bash
javac -encoding UTF-8 LowerBoundProof.java
java LowerBoundProof
```

```text
1
4
6
```

**Bất biến ở đầu mỗi vòng lặp:**

- Mọi vị trí có chỉ số `i < lo` đều mang giá trị `< target`.
- Mọi vị trí có chỉ số `i >= hi` đều mang giá trị `>= target`.

**Khởi tạo:** `lo=0`, `hi=n`; hai miền đã loại đều rỗng, nên bất biến đúng.

**Bảo toàn:** nếu `a[mid]<target`, nhờ mảng có thứ tự, tất cả phần tử từ `lo` đến `mid` đều nhỏ hơn `target`; đặt `lo=mid+1` an toàn. Ngược lại, nếu `a[mid]>=target`, tất cả phần tử từ `mid` đến `hi-1` đều `>=target`; đặt `hi=mid` an toàn.

**Dừng:** khi `lo<hi`, `mid` nằm trong `[lo,hi)`, và cả hai nhánh đều làm `hi-lo` giảm ít nhất `1`. Cuối cùng `lo==hi`.

**Đúng khi dừng:** các phần tử trước `lo` đều `<target`, các phần tử tại/từ `hi` đều `>=target`; vì `lo==hi`, đây là vị trí đầu tiên thỏa điều kiện hoặc `n` khi không tồn tại.

**Chi phí:** `O(log(n+1))` thời gian, `O(1)` bộ nhớ. Nếu đầu vào không được sắp xếp, bước suy ra “cả nửa này có cùng quan hệ” mất hiệu lực, nên chứng minh không áp dụng.

## 8. Các tình huống cần tăng cường mệnh đề

**Mệnh đề quá yếu:** “Merge sort tạo đoạn có thứ tự” không đủ nếu cần bảo toàn dữ liệu. Tăng mệnh đề thành “có thứ tự, là hoán vị của đoạn ban đầu, không ghi ngoài đoạn”.

**Sai lượng từ:** biết thuật toán đúng với *một* mảng độ dài `n-1` không cho phép suy ra đúng với mọi đoạn con; giả thiết phải đúng với mọi đầu vào hợp lệ cùng kích thước.

**Không giữ tiền điều kiện:** hàm được chứng minh trên mảng đã sắp xếp nhưng đệ quy/truyền vào mảng chưa được sắp xếp; hoặc truy hồi cần mệnh giá dương nhưng lại cho phép `0`.

**Bài toán con không nhỏ hơn:** quicksort phân hoạch sai có thể gọi lại nguyên đoạn cũ; khi đó quy nạp theo độ dài và chứng minh dừng đều thất bại.

**Thiếu trường hợp cơ sở:** hàm được thử với `n=1`, nhưng input hợp lệ gồm cả `n=0`; nhánh rỗng có thể gây truy cập sai hoặc đệ quy vô hạn.

**Lập luận tối ưu một chiều:** tìm được cách ghép *một nghiệm hợp lệ* chưa chứng minh đó là nghiệm tốt nhất. Với công thức `min` hoặc `max`, phải chứng minh mọi nghiệm tối ưu được biểu diễn bởi ít nhất một nhánh của công thức.

**Đánh đồng tính đúng với chi phí:** chứng minh lời gọi con đúng không tự suy ra `O(n log n)`. Phải đếm số lời gọi, chi phí bước ghép và bộ nhớ. Một thuật toán `O(2^n)` vẫn có thể hoàn toàn đúng.

**Đồ thị có chu trình:** “đệ quy xuống đỉnh kề” không làm giảm kích thước một cách hiển nhiên. Với DFS, cần trạng thái đã thăm và chứng minh mỗi đỉnh/cạnh được xử lý hữu hạn lần.

**Đệ quy đồng thời:** hai hàm `f` và `g` gọi lẫn nhau đòi hỏi chứng minh một thước đo chung giảm trên mọi nhánh, hoặc quy nạp đồng thời trên các mệnh đề của cả hai hàm.

**Lỗi thi hành:** chứng minh trên số nguyên toán học không ngăn tràn `int`, ngoại lệ `null`, chỉ số vượt biên hoặc đệ quy quá sâu gây `StackOverflowError`. Ghi rõ tiền điều kiện và giới hạn môi trường khi cần.

## 9. Bản đồ chọn phương pháp chứng minh

| Dạng thuật toán | Cách quy nạp thường phù hợp | Phần quyết định cần chứng minh |
|---|---|---|
| Đệ quy giảm một phần tử | Theo kích thước `n` | Bổ sung phần tử khôi phục đáp án đúng |
| Chia để trị trên mảng | Quy nạp mạnh theo độ dài | Mọi nhánh nhỏ hơn và phép ghép đúng |
| Dữ liệu cây, AST | Quy nạp cấu trúc theo constructor | Trường hợp rỗng và mỗi dạng node |
| DP theo tổng/chỉ số | Quy nạp mạnh theo thứ tự trạng thái | Công thức chuyển đúng, không bỏ nghiệm |
| Bài toán tối ưu tổ hợp | Phân rã cấu trúc lời giải | Mọi nghiệm tối ưu được xét, ứng viên hợp lệ |
| Vòng lặp tìm kiếm | Bất biến theo số vòng lặp | Khởi tạo, bảo toàn, kết luận lúc dừng |
| Đệ quy nhiều biến | Thước đo hữu hạn/thứ tự từ điển | Mỗi lời gọi nhỏ hơn nghiêm ngặt |

Đừng ép mọi chứng minh vào cùng một công thức. Nếu chương trình xử lý **cấu trúc cây**, quy nạp theo constructor thường dễ đọc nhất. Nếu thuật toán xây **nghiệm tối ưu**, phải mô tả các quyết định tạo nên nghiệm. Nếu thuật toán dùng **vòng lặp**, bất biến vòng lặp thường là cách trực tiếp nhất.

## 10. Quy trình thực hành chứng minh một bài thuật toán

1. **Đặc tả:** đầu vào nào hợp lệ, đầu ra phải thỏa tính chất gì? Xử lý rõ đầu vào rỗng, phần tử trùng, thiếu nghiệm, giá trị âm, phạm vi chỉ số.
2. **Chọn đại lượng:** độ dài đoạn, số nút, số trạng thái chưa xử lý hay cấu trúc nghiệm; xác minh mọi lời gọi con giảm nghiêm ngặt.
3. **Viết mệnh đề `P(n)` hoặc `Q(t)`:** dùng lượng từ **mọi đầu vào hợp lệ**, thêm mọi thuộc tính cần cho bước ghép.
4. **Xét cơ sở:** đủ tất cả trường hợp tối thiểu, không tự bỏ `n=0` nếu hợp lệ.
5. **Đặt giả thiết:** chỉ rõ được sử dụng kết luận cho những kích thước/cây con nào.
6. **Chứng minh bước:** mô tả lời gọi con, phép ghép, bất biến hoặc quyết định cuối của nghiệm; bảo đảm mọi nghiệm hợp lệ được bao phủ nếu tối ưu.
7. **Chứng minh dừng:** thước đo giảm có chặn dưới; với vòng lặp, chỉ ra biến tiến và điều kiện kết thúc.
8. **Tính chi phí:** lập truy hồi thời gian hoặc đếm số trạng thái, số cạnh, số lần thao tác; phân tích bộ nhớ/stack.
9. **Đối chiếu code:** dữ liệu, chỉ số, điều kiện so sánh và overflow có phù hợp lập luận không?
10. **Thử phản ví dụ:** rỗng, một phần tử, toàn phần tử bằng nhau, mảng có số âm, cây lệch, đồ thị có chu trình, mảng biên lớn.

### Bài tự kiểm tra ngắn

**A. Đếm lá của cây nhị phân.** Hãy định nghĩa: cây rỗng có `0` lá; một node không có con có `1` lá; node có ít nhất một con có số lá bằng tổng số lá các con. Dùng quy nạp cấu trúc chứng minh chương trình đếm đúng. Chú ý trường hợp node lá là một **cơ sở cấu trúc riêng** trong phép tính, dù constructor vẫn là `Node`.

**B. Tìm max trong đoạn không rỗng.** Đặt `P(n)` cho mọi đoạn dài `n>=1`, cơ sở `n=1`, bước `max(a[lo], max(rest))`. Không dùng kết quả mặc định `0` vì mảng có thể toàn số âm.

**C. Đếm cách bước 1 hoặc 2 bậc lên cầu thang.** Với `ways(0)=1`, `ways(1)=1`, `ways(n)=ways(n-1)+ways(n-2)` cho `n>=2`: chứng minh bằng cách chia mọi đường đi theo bước **cuối**, rồi dùng quy nạp mạnh để chứng minh bảng DP tính đúng. Các nhóm bước cuối phải rời nhau và bao phủ mọi đường đi.

**D. Nhận diện chứng minh sai.** Một quicksort đệ quy lại trên đoạn dài bằng ban đầu khi phần tử trùng nhau. Liệu có thể nói “theo quy nạp trên `n` nên chương trình dừng” không? Không: lời gọi con không nhỏ hơn `n`, nên giả thiết quy nạp không được áp dụng.

**Kết luận học tập:** một chứng minh thuật toán theo quy nạp phải trả lời được: **điều gì đúng ở cơ sở, tại sao bài toán con thuộc miền đã chứng minh, tại sao kết quả con ghép thành kết quả toàn cục, và điều gì bảo đảm thuật toán dừng**. Khi những điều kiện đó rõ ràng, phân tích chi phí mới có nền tảng chính xác.
