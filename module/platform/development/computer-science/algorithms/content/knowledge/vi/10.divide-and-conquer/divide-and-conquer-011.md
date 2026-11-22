# Chuyển một số lời giải đệ quy sang xử lý bằng ngăn xếp

Trong **chia để trị (divide and conquer)**, một lời giải thường có dạng: xử lý bài toán con, gọi hàm trên những phần nhỏ hơn, rồi **kết hợp kết quả sau khi các lời gọi con hoàn tất**. Ngôn ngữ lập trình thực thi việc này nhờ **ngăn xếp lời gọi (call stack)**: mỗi lần gọi đệ quy có một *frame* riêng lưu tham số, biến cục bộ và vị trí phải tiếp tục sau khi hàm con trả về.

Ta có thể tự mô phỏng cơ chế đó bằng một **ngăn xếp tường minh (explicit stack)** trong heap. Việc chuyển đổi không chỉ là đổi một lời gọi đệ quy thành vòng lặp: phải giữ nguyên **thứ tự công việc, trạng thái dở dang của từng frame, dữ liệu trả về, điều kiện dừng và bất biến**. Bài này trình bày khi nào chỉ cần stack chứa các “nhiệm vụ con”, khi nào phải có **frame nhiều giai đoạn**, và minh họa bằng **quicksort**, **merge sort** cùng phép cộng chia để trị trong Java 17+.

## 1. Đệ quy thực sự lưu những thông tin gì?

Xét mẫu chia để trị:

```text
solve(problem):
    if problem đủ nhỏ:
        return baseCase(problem)

    left, right = split(problem)
    leftResult = solve(left)
    rightResult = solve(right)
    return combine(leftResult, rightResult)
```

Trong mã trên, tại thời điểm `solve(left)` đang chạy, lời gọi cha **chưa xong**. Để trở lại đúng nơi, runtime phải nhớ ít nhất:

1. **Phạm vi/đối số của lời gọi cha**: ví dụ đoạn mảng `[lo, hi)` hay nút cây hiện tại.
2. **Biến cục bộ còn cần dùng**: `mid`, thông tin pivot, tham chiếu bộ đệm, kết quả nửa trái...
3. **Điểm tiếp tục**: đã chuẩn bị chia hay chưa, đã xử lý nửa trái hay chưa, lúc nào xử lý nửa phải, lúc nào kết hợp.
4. **Kết quả trả về**: con trả một giá trị, hoặc đã hoàn thành tác dụng phụ trên cấu trúc chung.
5. **Điều kiện dừng và quan hệ giữa cha–con**: tránh sinh vô hạn các bài toán con.

Gọi `solve` trên chính nó **không có gì thần bí**: runtime đưa frame mới lên call stack; khi hàm con trả về, frame con rời stack và frame cha tiếp tục chạy đúng dòng tiếp theo. Một vòng `while` với `ArrayDeque<Frame>` có thể mô phỏng quy tắc này.

**Hai khác biệt quan trọng:**

- **Call stack** chứa các frame do JVM quản lý; quá sâu có thể gây `StackOverflowError`. **Explicit stack** là đối tượng trong heap, có thể tránh giới hạn sâu của call stack nhưng vẫn tốn bộ nhớ và có thể gặp `OutOfMemoryError` nếu dữ liệu/state quá lớn.
- Chuyển sang explicit stack **không mặc nhiên cải thiện Big-O**. Nếu vẫn duyệt cùng số nút/bài toán con và giữ cùng số frame cần thiết, số phép xử lý và độ phức tạp thời gian thường cùng bậc. Có thể có khác biệt chi phí cấp phát, locality và mức độ tối ưu runtime.

## 2. Hai kiểu chuyển đổi thường gặp

| Dạng đệ quy | Ví dụ | Trạng thái cần đưa vào stack |
| --- | --- | --- |
| **Chỉ cần hoàn tất các nhiệm vụ con độc lập; không có bước “hợp” sau con** | Quicksort phân hoạch tại chỗ rồi sort hai đoạn; DFS duyệt nút chỉ để thăm | **Phạm vi/nút cần xử lý**; mỗi lần lấy một nhiệm vụ ra, có thể đưa các nhiệm vụ con vào |
| **Cần công việc sau khi một hoặc nhiều con hoàn tất** | Merge sort cần merge *sau cả hai nửa*; tính tổng/chiều cao cây cần kết quả hai con; duyệt hậu tự | **Frame có giai đoạn** (`phase/stage`), tham số và kết quả tạm; có thể cần truyền kết quả lên cha |
| **Đệ quy đuôi (tail recursion)** | Hàm gọi lại chính nó là hành động cuối cùng | Thường chuyển trực tiếp thành `while`, không cần lưu frame chờ kết quả |
| **Quay lui (backtracking)** | Thử nhánh, đánh dấu, gọi con rồi hoàn tác | Stack phải lưu **vị trí tiếp tục, trạng thái lựa chọn và hành động undo**; đôi khi cần snapshot |

Một quy tắc dễ nhớ:

> **Nếu cha còn việc phải làm sau khi con kết thúc, chỉ đẩy “địa chỉ con” thường là chưa đủ.** Phải lưu cả **vị trí đang tạm dừng** của cha.

Ví dụ quicksort có thể phân hoạch một đoạn rồi đưa hai đoạn chưa được sắp xếp vào stack; các đoạn có thể hoàn tất theo bất kỳ thứ tự phù hợp nào vì không cần ghép theo thứ tự sau đó. Trái lại, merge sort không thể gọi `merge(lo,mid,hi)` **ngay sau khi đẩy hai nhiệm vụ sort** lên stack: lúc ấy hai nửa có thể **chưa** được sắp xếp.

## 3. Nguyên tắc thiết kế một frame tường minh

Với lời gọi `solve(lo,hi)` trên khoảng nửa mở `[lo,hi)`, một frame có thể chứa:

```text
Frame {
    lo, hi             // phạm vi lời gọi
    mid                // điểm chia được tính từ lo, hi
    stage              // tiếp tục ở đâu?
    leftResult         // nếu combine cần giá trị trả về của con trái
}
```

Quy ước ví dụ:

- `stage=0`: vừa vào frame; chưa gọi con trái.
- `stage=1`: con trái đã hoàn tất; chuẩn bị gọi con phải.
- `stage=2`: con phải đã hoàn tất; kết hợp rồi hoàn thành frame.

Ở vòng lặp, **`peek()`** lấy frame trên cùng mà **chưa xóa** để cập nhật giai đoạn; **`push(child)`** tạo lời gọi con; **`pop()`** tương đương lời gọi hiện tại hoàn tất và quay về cha.

**Không được nhầm `peek()` với `pop()`:** Nếu xóa frame cha trước khi đưa con lên stack, có thể mất `mid` hoặc không còn nơi để thực hiện `combine`. Phải giữ frame cha ở dưới con đến lúc thực hiện bước sau lời gọi con.

Với Java:

```java
Deque<Frame> stack = new ArrayDeque<>();
stack.push(new Frame(0, n));
while (!stack.isEmpty()) {
    Frame current = stack.peek();
    // ... xử lý current.stage, push con hoặc pop khi hoàn tất ...
}
```

Đây là **mẫu minh họa**, chưa phải chương trình độc lập. `ArrayDeque` phù hợp với thao tác LIFO ở đầu deque; cần `import java.util.ArrayDeque; import java.util.Deque;`. Frame ở đây là một đối tượng tham chiếu có thể cập nhật `stage`. Không cần dùng `java.util.Stack` chỉ vì tên kiểu “Stack”.

Một lựa chọn khác là **stack các hành động** thay vì frame có stage, ví dụ đẩy `MERGE(lo,mid,hi)`, rồi đẩy `SORT(right)` và `SORT(left)` theo **thứ tự ngược** với thứ tự cần thực thi. Khi lấy từ stack LIFO, ta thực hiện `SORT(left)`, sau đó `SORT(right)`, cuối cùng `MERGE`. Đây cũng là kỹ thuật hợp lệ; điều kiện then chốt là sự kiện merge phải xảy ra **sau** hai nhiệm vụ sort.

## 4. Ví dụ một: quicksort dùng stack nhiệm vụ con

Quicksort làm hai loại việc:

1. **Phân hoạch** đoạn `[lo,hi)` quanh pivot `p` sao cho mọi phần tử ở miền trái `<p`, miền giữa `=p`, miền phải `>p`.
2. Tiếp tục sắp xếp **miền trái** và **miền phải**; miền giữa không cần xử lý nữa.

Khi phân hoạch xong, pivot và các phần tử bằng nó đã ở đúng **miền thứ tự tương đối theo giá trị** so với hai phía. Không có bước *merge* sau khi sort các miền con. Vì thế stack chỉ cần lưu **các đoạn còn phải xử lý**:

```text
push([0,n))

while stack not empty:
    [lo,hi) = pop()
    if hi-lo <= 1:
        continue

    phân hoạch ba miền [lo,lt), [lt,gt+1), [gt+1,hi)
    push các miền chưa sắp có hơn một phần tử
```

### Vì sao chọn phân hoạch ba miền?

Nếu dữ liệu có rất nhiều phần tử bằng nhau, phân hoạch ba miền (Dutch National Flag) giúp loại **toàn bộ nhóm bằng pivot** sau một lượt. Điều này ngăn việc tiếp tục đưa cùng các phần tử bằng pivot vào nhiều nhiệm vụ con không cần thiết.

Dùng các chỉ số:

```text
[lo, lt)     : < pivot
[lt, i)      : = pivot
[i, gt]      : chưa phân loại
(gt, hi)     : > pivot
```

Ban đầu `lt=i=lo` và `gt=hi−1`. Trong khi `i≤gt`:

- `a[i]<pivot`: đổi chỗ `a[lt]` với `a[i]`, tăng cả `lt` lẫn `i`.
- `a[i]>pivot`: đổi `a[i]` với `a[gt]`, giảm `gt` nhưng **không tăng `i`**, vì phần tử từ phải chuyển lên chưa được kiểm tra.
- `a[i]==pivot`: tăng `i`.

Khi vùng chưa phân loại rỗng, hai đoạn con là `[lo,lt)` và `[gt+1,hi)`. Cả hai đều **ngắn hơn** đoạn cha vì pivot được chọn từ trong đoạn, nên tiến trình kết thúc.

### Thứ tự push và độ sâu stack

Do stack là LIFO, nếu muốn **xử lý đoạn nhỏ trước**, cần **đẩy đoạn lớn trước rồi đoạn nhỏ sau**. Điều này làm số đoạn đang chờ ở stack được kiểm soát: mỗi lần có một đoạn lớn bị giữ chờ, ta đi sâu vào đoạn nhỏ dài tối đa một nửa đoạn hiện tại. Với chiến lược này, số nhiệm vụ chờ tăng theo **`O(log n)`** trên thuật toán phân hoạch hợp lệ, kể cả khi phân hoạch rất lệch; nếu một miền có độ dài 0 hoặc 1 thì không cần push.

Điều đó **không** bảo đảm thời gian `O(n log n)`. Nếu pivot chọn tệ liên tiếp, quicksort vẫn có thể mất `Θ(n²)` thời gian, dù explicit stack được tổ chức tiết kiệm. Mẫu dùng pivot tại **vị trí giữa của đoạn** để dễ hiểu, không phải bộ chọn pivot ngẫu nhiên hay bảo đảm chống mọi input xấu.

## 5. Ví dụ hai: merge sort phải nhớ “đợi con về rồi merge”

Mẫu merge sort đệ quy:

```java
static void mergeSort(int[] a, int[] tmp, int lo, int hi) {
    if (hi - lo <= 1) return;
    int mid = lo + (hi - lo) / 2;
    mergeSort(a, tmp, lo, mid);
    mergeSort(a, tmp, mid, hi);
    merge(a, tmp, lo, mid, hi);
}
```

Đây là **phác thảo**, chưa có hàm `merge`, nên không độc lập để biên dịch. Điểm quan trọng là `merge` chỉ chạy **sau khi** hai lời gọi con đã hoàn tất, mỗi nửa đã được sort.

### Sơ đồ stage tương ứng

Cho frame `F(lo,hi,stage)` với `mid=(lo+hi)/2`:

| Stage của frame | Ý nghĩa trước khi xử lý | Hành động |
| --- | --- | --- |
| `0` | Vừa bắt đầu, nửa trái chưa xử lý | Đặt `stage=1`, push `F(lo,mid,0)` |
| `1` | Nửa trái đã sort; nửa phải chưa xử lý | Đặt `stage=2`, push `F(mid,hi,0)` |
| `2` | Cả hai nửa đã sort | Gọi `merge(lo,mid,hi)`, rồi pop frame |
| `hi−lo≤1` | Trường hợp cơ sở (không có việc merge) | Pop frame ngay |

Vì frame cha vẫn ở dưới frame con, nó được lấy ra lại bằng `peek()` **sau khi** con trái hoặc con phải bị pop. `stage` đã được cập nhật trước khi push, nên cha biết tiếp tục ở đâu.

Ví dụ `[4,1,3,2]`:

```text
S(0,4)
├── S(0,2)
│   ├── S(0,1) -> base
│   ├── S(1,2) -> base
│   └── merge(0,1,2): [1,4]
├── S(2,4)
│   ├── S(2,3) -> base
│   ├── S(3,4) -> base
│   └── merge(2,3,4): [2,3]
└── merge(0,2,4): [1,2,3,4]
```

**Điểm kiểm chứng:** Merge ở gốc xảy ra **sau** merge của cả hai nhánh. Nếu đẩy hai con vào stack rồi merge gốc ngay lập tức, ta sẽ ghép hai nửa vẫn chưa được sắp và làm sai thuật toán.

### Bất biến đúng cho merge sort có frame

Khi xử lý frame ở `stage=2`, **hai đoạn `[lo,mid)` và `[mid,hi)` đều đã sắp tăng không giảm**. Đây là điều kiện đầu vào cần thiết cho thủ tục merge tuyến tính.

- **Cơ sở:** Đoạn có 0 hoặc 1 phần tử đã sắp, nên có thể pop ngay.
- **Bước quy nạp:** Sau khi stage 0 và stage 1 lần lượt xử lý các con, cả hai nửa đã sắp theo giả thiết quy nạp. Merge đúng sẽ tạo đoạn `[lo,hi)` tăng không giảm mà không thêm/bỏ phần tử.
- **Kết thúc:** Frame gốc pop khi toàn bộ mảng đã sắp.

Thủ tục merge **ổn định** khi hai phần tử đầu của nửa trái và nửa phải có khóa bằng nhau thì lấy **phần tử bên trái trước**. Chuyển sang explicit stack không tự làm mất/được tính ổn định; nó phụ thuộc vào hành vi merge.

### Độ phức tạp

Merge sort chia gần cân bằng có **`Θ(n log n)` thời gian**, cần **`O(n)` bộ đệm merge**; ngăn xếp frame đạt **`O(log n)` phần tử cùng lúc**. Có thể tạo tổng cộng `O(n)` đối tượng frame qua toàn bộ quá trình, nhưng số frame **đồng thời** chỉ có bậc logarit nhờ độ sâu cây. Phiên bản đệ quy cũng có độ sâu call stack `O(log n)`; bản tường minh chủ yếu cho **kiểm soát tiến trình và vùng lưu trữ**, không làm giảm bậc thời gian.

## 6. Khi hàm con trả về giá trị: phải truyền kết quả lên cha

Merge sort trên đây **không trả một giá trị** từ mỗi lời gọi con; hàm con đã sửa vùng dữ liệu chung rồi trở về. Nhưng với phép tính chia để trị:

```text
sum(lo, hi):
    if hi-lo == 0: return 0
    if hi-lo == 1: return a[lo]
    mid = lo + (hi-lo)/2
    left = sum(lo, mid)
    right = sum(mid, hi)
    return left + right
```

Khi chuyển sang stack, cha cần giữ **`left`** trong khi đang xử lý con phải. Có thể dùng:

- Trường `leftValue` trong frame cha;
- Một biến `returned` giữ **giá trị mà frame vừa pop đã trả**, vì mô phỏng duyệt sâu (DFS) xử lý đúng **một lời gọi con tại một thời điểm**;
- `stage=0/1/2` để phân biệt chưa gọi trái, đang nhận kết quả trái để gọi phải, và đang nhận kết quả phải để kết hợp.

Dòng hoạt động tại cha:

```text
stage 0:
    stage = 1
    push(left child)

stage 1:                 // left child đã pop, returned là tổng trái
    leftValue = returned
    stage = 2
    push(right child)

stage 2:                 // right child đã pop, returned là tổng phải
    returned = leftValue + returned
    pop(parent)          // trả tổng của cha về frame trên
```

**Chốt:** Một biến `returned` chỉ an toàn ở mẫu điều khiển này vì ta luôn xử lý con **theo DFS tuần tự**, và cha đọc kết quả **ngay** sau khi frame con kết thúc. Nếu chuyển sang xử lý song song, hàng đợi hoặc nhiều nhiệm vụ xen kẽ, không thể mặc định giá trị trả về cuối cùng còn thuộc đúng cha; cần lưu liên kết nhiệm vụ/kết quả rõ ràng.

Với phép cộng `int` có nguy cơ tràn, ví dụ Java đầy đủ dùng `long` cho tổng. Đối với số nguyên cực lớn vượt `long`, muốn chính xác tuyệt đối phải chọn kiểu khác như `BigInteger` theo yêu cầu bài toán.

## 7. Công thức chuyển đổi từ recursion sang explicit stack

Một quy trình có thể áp dụng cho nhiều thuật toán:

1. **Viết rõ đệ quy trước**, ghi tiền điều kiện, trường hợp cơ sở, tham số và hành động trước/sau khi gọi con. Nếu không xác định được các điểm đó, chuyển đổi sớm thường tạo lỗi khó gỡ.
2. **Đánh dấu “điểm tạm dừng” trong mỗi hàm**: trước con trái, sau con trái/trước con phải, sau con phải/trước combine. Đây là các stage hoặc action cần mô phỏng.
3. **Định nghĩa frame tối thiểu** chứa các biến còn cần sau khi quay lại. Với bài chỉ có công việc độc lập, đôi khi chỉ cần `Range(lo,hi)`; với bài combine cần `Frame(lo,hi,mid,stage,partialResult)`.
4. **Đưa frame gốc lên stack**, vòng lặp khi stack không rỗng; mỗi bước chỉ thực hiện một sự kiện logic: push con, cập nhật stage, combine hoặc pop.
5. **Giữ quy ước thứ tự**: LIFO lấy phần tử mới nhất trước. Muốn con trái chạy trước, phải push con phải trước (với worklist thuần), hoặc dùng stage để tạo đúng thứ tự gọi.
6. **Đối chiếu tính đúng** bằng bất biến: frame ở stage nào bảo đảm điều gì? Trước combine, các con đã hoàn tất chưa? Có xử lý một trạng thái hai lần hoặc bỏ sót không?
7. **Kiểm soát bộ nhớ và độ sâu**: nếu có thể chọn thứ tự nhiệm vụ, ưu tiên xử lý nhánh nhỏ trước để giảm stack chờ; tránh snapshot lớn không cần thiết.
8. **Kiểm thử đối chiếu** với hàm đệ quy và một oracle độc lập (ví dụ `Arrays.sort`) trên dãy nhỏ, dãy rỗng, một phần tử, giá trị trùng, dữ liệu đã sắp và đảo chiều.

Không cần chuyển đổi mọi hàm đệ quy. Nếu độ sâu có bảo đảm nhỏ, ví dụ merge sort cân bằng với `log2(n)` mức, đệ quy thường rõ ràng hơn. Ngược lại, duyệt đồ thị sâu, cây lệch hoặc các quá trình có thể chạy nhiều nghìn mức là những ứng viên đáng xem xét; dù vậy explicit stack vẫn cần bộ nhớ phù hợp.

## 8. Java 17+ — ba kiểu explicit stack trong một chương trình

Chương trình **RecursionStackDemo.java** có:

- `mergeSortStack(Item[])`: mô phỏng đệ quy merge sort bằng `Frame` có `stage`, xử lý **merge hậu tự**; giữ tính ổn định của các bản ghi cùng khóa.
- `mergeSortRecursive(Item[])`: phiên bản đệ quy tương ứng dùng làm đối chiếu.
- `quickSortTasks(int[])`: explicit stack chỉ chứa các đoạn cần sort; phân hoạch **ba miền** và ưu tiên xử lý đoạn nhỏ.
- `sumStack(int[])`: dùng `SumFrame` có `leftValue` và biến `returned` để mô phỏng kết quả trả về.
- `checkSmallCases()`: kiểm tra các triển khai trên mọi dãy độ dài `0..5` từ tập `{-1,0,1}`, đối chiếu với `Arrays.sort` và phép tính tổng tuyến tính; đồng thời kiểm tra stable qua mã định danh gốc của mỗi phần tử.

### Mã Java đầy đủ

```java
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Comparator;
import java.util.Deque;

public class RecursionStackDemo {
    record Item(int key, String id) {
        @Override
        public String toString() {
            return key + ":" + id;
        }
    }

    // Frame mô phỏng mergeSort(lo,hi) và dòng tiếp tục.
    static final class Frame {
        final int lo, hi, mid;
        int stage; // 0: trái, 1: phải, 2: merge

        Frame(int lo, int hi) {
            this.lo = lo;
            this.hi = hi;
            this.mid = lo + (hi - lo) / 2;
        }
    }

    // Merge ổn định: key bằng nhau lấy phần tử bên trái trước.
    static void merge(Item[] a, Item[] temp,
                      int lo, int mid, int hi) {
        int i = lo, j = mid, k = lo;
        while (i < mid && j < hi) {
            if (a[i].key() <= a[j].key()) {
                temp[k++] = a[i++];
            } else {
                temp[k++] = a[j++];
            }
        }
        while (i < mid) {
            temp[k++] = a[i++];
        }
        while (j < hi) {
            temp[k++] = a[j++];
        }
        System.arraycopy(temp, lo, a, lo, hi - lo);
    }

    static void mergeSortStack(Item[] a) {
        if (a.length < 2) {
            return;
        }
        Item[] temp = new Item[a.length];
        Deque<Frame> frames = new ArrayDeque<>();
        frames.push(new Frame(0, a.length));

        while (!frames.isEmpty()) {
            Frame f = frames.peek();
            if (f.hi - f.lo <= 1) {
                frames.pop();
            } else if (f.stage == 0) {
                f.stage = 1; // Khi con trái về: đi sang stage 1.
                frames.push(new Frame(f.lo, f.mid));
            } else if (f.stage == 1) {
                f.stage = 2; // Khi con phải về: merge.
                frames.push(new Frame(f.mid, f.hi));
            } else {
                merge(a, temp, f.lo, f.mid, f.hi);
                frames.pop();
            }
        }
    }

    private static void mergeRec(Item[] a, Item[] temp,
                                 int lo, int hi) {
        if (hi - lo <= 1) {
            return;
        }
        int mid = lo + (hi - lo) / 2;
        mergeRec(a, temp, lo, mid);
        mergeRec(a, temp, mid, hi);
        merge(a, temp, lo, mid, hi);
    }

    static void mergeSortRecursive(Item[] a) {
        Item[] temp = new Item[a.length];
        mergeRec(a, temp, 0, a.length);
    }

    record Range(int lo, int hi) {}

    private static void swap(int[] a, int x, int y) {
        int tmp = a[x];
        a[x] = a[y];
        a[y] = tmp;
    }

    // Không gọi đệ quy; mỗi Range là nhiệm vụ chưa hoàn tất.
    static void quickSortTasks(int[] a) {
        if (a.length < 2) {
            return;
        }
        Deque<Range> tasks = new ArrayDeque<>();
        tasks.push(new Range(0, a.length));

        while (!tasks.isEmpty()) {
            Range task = tasks.pop();
            int lo = task.lo(), hi = task.hi();
            if (hi - lo <= 1) {
                continue;
            }

            int pivot = a[lo + (hi - lo) / 2];
            int lt = lo, i = lo, gt = hi - 1;

            // [lo,lt) < pivot; [lt,i) == pivot;
            // [i,gt] unknown; (gt,hi) > pivot.
            while (i <= gt) {
                if (a[i] < pivot) {
                    swap(a, lt++, i++);
                } else if (a[i] > pivot) {
                    swap(a, i, gt--);
                } else {
                    i++;
                }
            }

            Range left = new Range(lo, lt);
            Range right = new Range(gt + 1, hi);
            int leftSize = lt - lo;
            int rightSize = hi - (gt + 1);

            // LIFO: push đoạn lớn trước để xử lý đoạn nhỏ trước.
            if (leftSize >= rightSize) {
                if (leftSize > 1) {
                    tasks.push(left);
                }
                if (rightSize > 1) {
                    tasks.push(right);
                }
            } else {
                if (rightSize > 1) {
                    tasks.push(right);
                }
                if (leftSize > 1) {
                    tasks.push(left);
                }
            }
        }
    }

    static final class SumFrame {
        final int lo, hi, mid;
        int stage;
        long leftValue;

        SumFrame(int lo, int hi) {
            this.lo = lo;
            this.hi = hi;
            this.mid = lo + (hi - lo) / 2;
        }
    }

    // Mô phỏng lời gọi trả về long bằng biến returned.
    static long sumStack(int[] a) {
        Deque<SumFrame> frames = new ArrayDeque<>();
        frames.push(new SumFrame(0, a.length));
        long returned = 0;

        while (!frames.isEmpty()) {
            SumFrame f = frames.peek();
            if (f.hi - f.lo <= 1) {
                returned = (f.hi == f.lo) ? 0L : a[f.lo];
                frames.pop();
            } else if (f.stage == 0) {
                f.stage = 1;
                frames.push(new SumFrame(f.lo, f.mid));
            } else if (f.stage == 1) {
                f.leftValue = returned; // Con trái vừa trả về.
                f.stage = 2;
                frames.push(new SumFrame(f.mid, f.hi));
            } else {
                returned = f.leftValue + returned;
                frames.pop(); // Trả tổng cha lên cấp trên.
            }
        }
        return returned;
    }

    static int checkSmallCases() {
        int variants = 1;
        int checked = 0;
        for (int n = 0; n <= 5; n++) {
            for (int encoded = 0; encoded < variants; encoded++) {
                int[] values = new int[n];
                int code = encoded;
                long expectedSum = 0;

                Item[] items = new Item[n];
                for (int i = 0; i < n; i++) {
                    values[i] = code % 3 - 1;
                    code /= 3;
                    expectedSum += values[i];
                    items[i] = new Item(values[i], "i" + i);
                }

                int[] expectedInts = values.clone();
                Arrays.sort(expectedInts);
                int[] actualInts = values.clone();
                quickSortTasks(actualInts);

                Item[] expectedItems = items.clone();
                Arrays.sort(expectedItems,
                            Comparator.comparingInt(Item::key));
                Item[] stackItems = items.clone();
                Item[] recursiveItems = items.clone();
                mergeSortStack(stackItems);
                mergeSortRecursive(recursiveItems);

                if (!Arrays.equals(expectedInts, actualInts)
                        || !Arrays.equals(expectedItems, stackItems)
                        || !Arrays.equals(expectedItems, recursiveItems)
                        || sumStack(values) != expectedSum) {
                    throw new AssertionError(
                        "Failed input: " + Arrays.toString(values));
                }
                checked++;
            }
            variants *= 3;
        }
        return checked;
    }

    public static void main(String[] args) {
        Item[] original = {
            new Item(3, "A"),
            new Item(1, "B"),
            new Item(3, "C"),
            new Item(2, "D"),
            new Item(1, "E")
        };
        Item[] sorted = original.clone();
        mergeSortStack(sorted);

        System.out.println("Original items: "
                           + Arrays.toString(original));
        System.out.println("Stack merge: "
                           + Arrays.toString(sorted));

        Item[] recursivelySorted = original.clone();
        mergeSortRecursive(recursivelySorted);
        System.out.println("Recursive agrees: "
                           + Arrays.equals(sorted, recursivelySorted));

        int[] quick = {4, 1, 4, -2, 3, 1};
        quickSortTasks(quick);
        System.out.println("Task quicksort: "
                           + Arrays.toString(quick));

        System.out.println("Frame sum: "
                           + sumStack(new int[]{3, -1, 4, 1, 5}));
        Item[] empty = {};
        mergeSortStack(empty);
        System.out.println("Empty merge: "
                           + Arrays.toString(empty));
        int[] single = {7};
        quickSortTasks(single);
        System.out.println("Single quick: "
                           + Arrays.toString(single));

        System.out.println("Small exhaustive check: OK ("
                           + checkSmallCases() + " arrays)");
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 RecursionStackDemo.java
java RecursionStackDemo
```

Stdout dự kiến:

```text
Original items: [3:A, 1:B, 3:C, 2:D, 1:E]
Stack merge: [1:B, 1:E, 2:D, 3:A, 3:C]
Recursive agrees: true
Task quicksort: [-2, 1, 1, 3, 4, 4]
Frame sum: 12
Empty merge: []
Single quick: [7]
Small exhaustive check: OK (364 arrays)
```

### Cách hiểu kết quả

- `mergeSortStack` và `mergeSortRecursive` cùng trả thứ tự theo khóa `[1,1,2,3,3]`, đồng thời giữ nhãn `B` trước `E` và `A` trước `C`; đó là **stable** do merge ưu tiên nửa trái khi bằng khóa.
- `quickSortTasks` trả đúng mảng số nguyên tăng không giảm. **Quicksort trong mã này không cam kết stable**, và nhiệm vụ cần xử lý chỉ lưu `Range`, không có frame chờ merge.
- `sumStack` nhận lại giá trị `returned` từ con trái, cất trong `leftValue`, rồi nhận giá trị con phải và cộng lại. Đây là việc phiên bản chỉ lưu các Range **không thể mô tả đầy đủ**.
- Trường hợp mảng rỗng và một phần tử không có việc cần chia. Các khoảng nửa mở `[lo,hi)` khiến kích thước đoạn là `hi−lo`, không phải `hi−lo+1`.
- Kiểm thử sinh tất cả `1+3+9+27+81+243=364` dãy độ dài 0 đến 5 trên ba giá trị `−1,0,1`. Kết quả quicksort so với `Arrays.sort(int[])`; merge sort trên `Item` so với sắp xếp object bằng comparator trên khóa và kiểm tra cả `id` trong `record`; tổng đối chiếu với cộng tuyến tính.
- Mỗi phép kiểm thử chỉ tìm được phản ví dụ trong miền dữ liệu nhỏ; **chứng minh bất biến**, điều kiện dừng và hợp đồng frame là cơ sở để tin rằng thuật toán đúng với miền đầu vào hợp lệ tổng quát.

## 9. Phân tích chi phí và rủi ro khi chuyển đổi

| Cách làm | Thời gian | Bộ nhớ phụ điển hình | Điểm cần thận trọng |
| --- | --- | --- | --- |
| Merge sort đệ quy cân bằng | `Θ(n log n)` | `O(n)` buffer + `O(log n)` call stack | Phải merge sau khi hai con hoàn tất |
| Merge sort explicit Frame | `Θ(n log n)` | `O(n)` buffer + `O(log n)` frame đang chờ | Stage, `peek/pop` phải mô phỏng đúng vị trí tiếp tục |
| Quicksort đệ quy pivot kém | Xấu nhất `Θ(n²)` | Call stack có thể `O(n)` nếu xử lý ngây thơ | Dữ liệu đối kháng, pivot, nhóm phần tử trùng |
| Quicksort explicit work stack, nhỏ trước | Kỳ vọng/điển hình tùy pivot; xấu nhất `Θ(n²)` | `O(log n)` nhiệm vụ chờ với cách push lớn trước, chỉ push đoạn dài hơn 1 | Không nhầm giới hạn stack với bảo đảm thời gian |
| Tổng chia để trị với frame trả về | `Θ(n)` | `O(log n)` frame nếu chia cân bằng | Giữ đúng `leftValue` và kết quả con phải |

**Không có phép màu loại bỏ bộ nhớ:** Explicit stack chuyển vùng lưu frame sang heap, song vẫn tiêu tốn bộ nhớ tỉ lệ số nhiệm vụ còn chờ. Với thuật toán có **độ sâu `Θ(n)`** không thể thay đổi bằng việc sắp thứ tự nhánh, một explicit stack mô phỏng sát từng lời gọi cũng có thể cần **`Θ(n)` frame**, dù tránh được giới hạn call stack.

**Không tự động nhanh hơn:** Với merge sort, mỗi bước còn tạo `Frame` object; chi phí cấp phát và quản lý có thể tăng so với phiên bản đệ quy ngắn gọn. Benchmark phải đo trên JVM thực, dữ liệu phù hợp; không kết luận nhanh hơn chỉ vì không gọi đệ quy.

**Tính đúng của output vẫn như cũ:** Nếu thuật toán gốc in kết quả theo một thứ tự, dùng stack thuần có thể **đảo thứ tự thăm con**. Với DFS tiền tự trên cây, muốn đi trái trước cần đẩy con phải lên trước, rồi mới đẩy con trái. Với DFS hậu tự hoặc thuật toán có bước combine, phải mô phỏng thêm sự kiện “sau khi con đã chạy”.

## 10. Các bẫy dễ gặp

1. **Đẩy hai con rồi combine ngay.** Với merge sort, hai nửa chưa được sort; combine phải là **hành động hậu tự**, qua `stage` hoặc action được đẩy xuống dưới các nhiệm vụ con.
2. **Làm mất frame cha.** Gọi `pop()` trước khi lưu `mid`, `stage` hoặc `leftValue` khiến không còn trạng thái để trở về sau khi xử lý con.
3. **Quên cập nhật stage trước khi push.** Khi con pop xong, cha vẫn ở stage cũ và lại push chính con đó → lặp vô hạn hoặc tạo công việc trùng.
4. **Đảo thứ tự do LIFO.** Push trái rồi phải khiến phải được xử lý trước. Nếu thứ tự có nghĩa với output/side effect, phải push theo hướng ngược.
5. **Dùng sai quy ước khoảng.** `[lo,hi)` có phần tử cuối `hi−1`; xử lý base `hi−lo≤1`. Nhầm `hi` là chỉ số cuối bao gồm dễ gây bỏ phần tử hoặc out-of-bounds.
6. **Bỏ qua nhóm bằng pivot.** Quicksort hai miền với dữ liệu toàn khóa trùng có thể tái xử lý quá nhiều; ba miền cho phép dừng trên toàn nhóm bằng.
7. **Tăng `i` sau swap với `gt`.** Trong phân hoạch ba miền, giá trị chuyển từ cuối lên `i` chưa được kiểm tra; tăng `i` bỏ sót phần tử.
8. **Chỉ lưu tham số, quên kết quả tạm.** Hàm trả về `combine(left,right)` phải nhớ `left` trong lúc tính `right`; một biến `returned` cần cách truyền kết quả rõ nghĩa.
9. **Dùng chung trạng thái mutable giữa frame sai chỗ.** Nếu hai nhánh cùng trỏ đến một bản sao dữ liệu đang bị chỉnh mà thuật toán yêu cầu độc lập, thứ tự xử lý có thể thay đổi kết quả; cần làm rõ hợp đồng chia sẻ và snapshot.
10. **Nhầm không dùng call stack với `O(1)` bộ nhớ.** Explicit stack vẫn tốn `O(depth)` hoặc `O(number of pending tasks)`; merge còn cần buffer `O(n)`.
11. **Bỏ qua điều kiện giảm kích thước bài toán.** Mỗi frame không-base phải sinh bài toán con nhỏ hơn; nếu lặp lại nguyên khoảng cũ (đặc biệt với pivot/ties), stack có thể phát triển vô hạn.
12. **Thay đệ quy bằng BFS dù yêu cầu DFS hậu tự.** Queue FIFO không giữ hành vi trả về của call stack; có thể dùng nhưng phải thiết kế lại điều kiện sẵn sàng combine hoặc lưu phụ thuộc.
13. **Không xét ngoại lệ và hoàn tác.** Đệ quy backtracking thường có logic undo khi nhánh kết thúc; explicit stack phải tái hiện cả đường quay lui. Nếu có exception, cần thiết kế cleanup tương ứng, không chỉ thêm `pop()` ở đường thành công.
14. **Tin rằng test nhỏ là đủ.** Test giúp bắt off-by-one, lỗi stage và thứ tự; chứng minh bất biến và tiến triển vẫn cần cho mọi input.

## 11. Bài tập tự luyện

**Bài 1 — Theo dõi frame.** Với merge sort trên `[4,1,3,2]`, ghi nội dung stack sau mỗi lần push/pop, stage của frame `[0,4)` và thứ tự các lệnh `merge`. Chứng minh merge của gốc phải xảy ra cuối.

**Bài 2 — Đổi sang action stack.** Thay `Frame.stage` bằng ba loại hành động `SORT(lo,hi)`, `MERGE(lo,mid,hi)` và `RETURN` nếu cần. Viết thứ tự push để khi pop chạy trái, phải, merge. So sánh độ rõ ràng và bộ nhớ.

**Bài 3 — Quicksort với ties.** Phân hoạch `[3,1,3,2,3,1]` quanh pivot `3`. Tìm các ranh giới `lt,gt`; nêu hai nhiệm vụ con cần push và lý do không cần sort miền bằng pivot.

**Bài 4 — Thứ tự push.** Trên stack LIFO, nếu muốn xử lý nhánh `A` trước nhánh `B`, phải push theo thứ tự nào? Nếu xử lý mỗi nhánh chỉ tạo side effect “in tên nhánh”, sai thứ tự sẽ gây kết quả gì?

**Bài 5 — Hàm trả về.** Tự chuyển hàm đệ quy tính tổng đoạn bằng hai con sang `SumFrame`. Tại sao chỉ lưu `(lo,hi)` chưa đủ để kết hợp sau khi con trả về? Tại sao `returned` phải được cha đọc ngay ở stage tương ứng?

**Bài 6 — Độ phức tạp.** Với `n` phần tử, so sánh merge sort đệ quy và explicit stack về thời gian, bộ đệm và độ sâu frame. Vì sao chuyển sang heap không làm thời gian `Θ(n log n)` thành `Θ(n)`?

**Bài 7 — Cây nghiêng sâu.** Một DFS đệ quy đi xuống đường dài 100.000 nút. Hãy thiết kế explicit stack chỉ giữ nút/công việc cần làm, rồi phân biệt chi phí heap và nguy cơ stack overflow của bản đệ quy. Nếu cần **tính chiều cao cây**, thông tin trả về của con phải được lưu thế nào?

**Bài 8 — Kiểm thử đúng và ổn định.** Sinh các mảng rỗng, một phần tử, trùng nhiều khóa, tăng/giảm, âm/dương và input lớn. So sánh quicksort với `Arrays.sort(int[])`, merge sort theo khóa với `Arrays.sort(Item[], comparator)` và bảo toàn thứ tự các `id` cùng khóa. Giải thích vì sao phải kiểm **cả nhãn**, không chỉ danh sách khóa.

## 12. Checklist khi chuyển một thuật toán đệ quy

- **Frame đủ thông tin?** Lưu tham số, trạng thái dở dang, biến cục bộ còn cần và kết quả con nếu có.
- **Base case chính xác?** Xử lý được rỗng, một phần tử hoặc nút null theo hợp đồng; không sinh con vô hạn.
- **LIFO đúng thứ tự?** Xác định các thao tác phải chạy trước/giữa/sau con; push theo thứ tự phù hợp.
- **Cha có thực sự chờ?** Dùng `peek` và stage cho công việc hậu tự; chỉ `pop` khi frame đã hoàn tất.
- **Bất biến được bảo toàn?** Trước merge, hai nửa đã sort; trước trả kết quả tổng, đã nhận đủ hai giá trị con; với quicksort, hai miền ngoài đã được phân hoạch đúng.
- **Kích thước công việc giảm?** Mọi nhiệm vụ con dài nhỏ hơn cha và không bị push lại vô cớ.
- **Bộ nhớ thực tế?** Tính cả explicit stack trên heap, buffer merge, bản sao input và dữ liệu phụ; không mặc định `O(1)`.
- **Tính ổn định/side effect?** Nếu thuật toán cần stable hoặc thứ tự thăm nút, việc đổi hướng push/merge có làm thay đổi quan sát không?
- **Kiểm chứng độc lập?** So output với đệ quy và oracle, thử edge case, giá trị lặp và các đường stage.

**Tiêu chí hoàn thành:** Bạn nhận diện được **frame và điểm tiếp tục** trong một lời giải chia để trị; biết trường hợp nào chỉ cần work stack, trường hợp nào cần **frame nhiều stage và giá trị trả về**; chuyển đúng merge sort/quicksort sang `ArrayDeque`, giải thích bằng bất biến vì sao các bước diễn ra đúng thứ tự, và tính chính xác thời gian/bộ nhớ thay vì mặc định explicit stack luôn tốt hơn.
