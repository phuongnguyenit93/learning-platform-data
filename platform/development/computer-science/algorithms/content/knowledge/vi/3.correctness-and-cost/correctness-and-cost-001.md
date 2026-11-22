# Bất biến vòng lặp và chứng minh từng bước xử lý

## 1. Vì sao cần bất biến vòng lặp?

Một chương trình có thể trả kết quả đúng với một vài bộ dữ liệu thử nhưng vẫn sai ở trường hợp khác. Để chứng minh **thuật toán đúng cho mọi đầu vào hợp lệ**, ta cần giải thích vì sao từng bước xử lý đều bảo toàn các điều kiện cần thiết và vì sao chương trình cuối cùng trả ra kết quả theo yêu cầu.

**Bất biến vòng lặp (loop invariant)** là một mệnh đề về trạng thái chương trình, được chọn sao cho nó **đúng tại một thời điểm thống nhất ở mọi lần lặp**, thường là ngay trước khi kiểm tra điều kiện lặp. Bất biến giúp nối trạng thái ban đầu với trạng thái khi kết thúc; nó không chỉ là một nhận xét về vài giá trị trung gian.

Ví dụ, trong một vòng lặp cộng dồn các phần tử của mảng, phát biểu “`sum` không âm” thường sai nếu mảng có số âm và không đủ mạnh để chứng minh kết quả. Phát biểu hữu ích hơn là: **`sum` chính bằng tổng của các phần tử đã xử lý**. Điều này mô tả chính xác công việc đã hoàn thành tại mỗi bước.

Một chứng minh vòng lặp hoàn chỉnh gồm hai phần khác nhau:

- **Tính đúng từng phần (partial correctness):** nếu chương trình kết thúc, đầu ra của nó thỏa yêu cầu.
- **Tính kết thúc (termination):** với mọi đầu vào hợp lệ, vòng lặp dừng sau hữu hạn bước.

Kết hợp hai phần là **tính đúng hoàn toàn (total correctness)**. Một bất biến dù đúng ở mọi lượt vẫn chưa tự bảo đảm chương trình sẽ dừng.

## 2. Từ đặc tả đến chứng minh: P, I, B, Q

Ta thường ký hiệu:

| Ký hiệu | Vai trò | Câu hỏi cần trả lời |
|---|---|---|
| `P` | Điều kiện trước (precondition) | Đầu vào phải thỏa điều gì trước khi chạy? |
| `I` | Bất biến (invariant) | Tính chất gì được giữ đúng tại đầu mỗi lần lặp? |
| `B` | Điều kiện tiếp tục lặp (loop guard) | Khi nào thân vòng lặp chạy? |
| `Q` | Điều kiện sau (postcondition) | Kết quả phải thỏa điều gì khi kết thúc? |
| `V` | Đại lượng tiến triển (variant/ranking function) | Giá trị nguyên không âm nào giảm nghiêm ngặt mỗi lượt? |

Mẫu vòng lặp:

```text
Khởi tạo trạng thái
while (B) {
    Xử lý và cập nhật trạng thái
}
Trả kết quả
```

Quy trình chứng minh:

1. **Khởi tạo:** từ `P` và trạng thái khởi tạo, suy ra `I` đúng trước lần kiểm tra `B` đầu tiên.
2. **Bảo toàn:** giả sử `I` và `B` cùng đúng tại đầu một lượt. Chứng minh thực hiện thân vòng lặp đưa chương trình trở về trạng thái thỏa `I` trước lần kiểm tra tiếp theo.
3. **Suy ra kết quả:** khi vòng lặp kết thúc bình thường, ta biết `I ∧ ¬B`; dùng hai dữ kiện để suy ra `Q`.
4. **Chứng minh dừng:** tìm `V` bị chặn dưới (thường `V ≥ 0`) và giảm nghiêm ngặt sau mỗi lần lặp còn tiếp tục. Với một vòng lặp có hữu hạn trạng thái hoặc các điều kiện khác được chỉ rõ, có thể dùng lập luận kết thúc tương đương; chỉ nói “`i` đang tăng” chưa đủ nếu không có chặn trên.

Ở mức trực giác, sơ đồ lý luận là:

```text
P
  └─ khởi tạo ──> I
                   │
            I và B │ chạy thân vòng lặp
                   └─> I  (giữ lại để xét lượt tiếp)
                   │
           I và ¬B └─> Q
Ngoài ra: V không âm và giảm mỗi lượt để bảo đảm dừng.
```

Cần chọn **một vị trí kiểm tra bất biến nhất quán**. Với vòng `for (init; condition; update)`, nếu chọn đầu lượt là *trước khi kiểm tra `condition`*, thì thao tác `update` cũng phải được tính trong bước bảo toàn. Với lệnh `break` hoặc `return`, phải chứng minh riêng rằng nhánh thoát đó đáp ứng điều kiện sau.

### Bất biến “đủ mạnh” nghĩa là gì?

Chẳng hạn `0 ≤ i ≤ n` là một bất biến tốt về **phạm vi chỉ số**, nhưng không chứng minh được rằng tổng cộng dồn có giá trị chính xác. Ta thường cần **nhiều mệnh đề đồng thời**, gồm ràng buộc chỉ số lẫn quan hệ giữa biến và phần dữ liệu đã xử lý.

Không có một công thức tự động cho mọi bài toán. Mẹo thực hành là nhìn **kết quả mong muốn ở cuối** và thay “toàn bộ dữ liệu” bằng “phần dữ liệu đã duyệt” để suy ra một ứng viên bất biến.

## 3. Ví dụ 1 — Cộng dồn: chứng minh theo tiền tố mảng

**Bài toán:** cho mảng số nguyên `a` không phải `null`, tính tổng toàn bộ phần tử. Mảng có thể rỗng, có số âm hoặc giá trị trùng.

Dùng ký hiệu `Σ a[0..i)` cho tổng các phần tử ở chỉ số `0, 1, …, i-1`; tiền tố rỗng có tổng bằng 0.

```java
static long sumArray(int[] a) {
    long sum = 0;
    for (int i = 0; i < a.length; i++) {
        sum += a[i];
    }
    return sum;
}
```

**Đặc tả:**

- `P`: `a != null`.
- `Q`: kết quả bằng `Σ a[0..n)` với `n = a.length`.
- `I` (ngay trước khi kiểm tra điều kiện `i < n`): `0 ≤ i ≤ n` **và** `sum = Σ a[0..i)`.

**Bước 1 — Khởi tạo.** Trước lượt đầu, `i = 0` và `sum = 0`. Tiền tố `[0,0)` rỗng nên có tổng bằng 0. Cả hai vế của `I` đều đúng.

**Bước 2 — Bảo toàn.** Giả sử đầu một lượt có `0 ≤ i < n` và `sum = Σ a[0..i)`. Lệnh `sum += a[i]` bổ sung đúng phần tử kế tiếp, thành `Σ a[0..i+1)`. Sau đó `for` thực hiện `i++`; vì vậy ở đầu lần kiểm tra tiếp theo, `sum = Σ a[0..i)` với chỉ số mới. Không phần tử nào bị bỏ sót hoặc cộng hai lần.

**Bước 3 — Khi thoát.** Điều kiện `i < n` sai. Do bất biến vẫn bảo đảm `i ≤ n`, suy ra `i = n`. Thay vào công thức tổng tiền tố: `sum = Σ a[0..n)`, đúng `Q`.

**Bước 4 — Kết thúc.** Đặt `V = n - i`. Khi còn lặp, `V > 0`; sau mỗi lượt, `i` tăng 1 nên `V` giảm 1. Vì `V` là số nguyên không âm tại các điểm kiểm tra, vòng lặp phải dừng.

### Truy vết từng lần kiểm tra

Với `a = [4, -2, 7]`, bảng sau ghi trạng thái **ngay trước khi kiểm tra `i < 3`**:

| Lần kiểm tra | `i` | `sum` | Phần tử đã xử lý | `V = 3 - i` |
|---|---:|---:|---|---:|
| Đầu tiên | 0 | 0 | Tiền tố rỗng | 3 |
| Sau lượt 1 | 1 | 4 | `[4]` | 2 |
| Sau lượt 2 | 2 | 2 | `[4, -2]` | 1 |
| Sau lượt 3 | 3 | 9 | `[4, -2, 7]` | 0 |

Tại hàng cuối, điều kiện lặp sai và `sum = 9` là tổng chính xác. Bảng chỉ giúp **nhìn thấy** bất biến; lập luận khởi tạo–bảo toàn–kết thúc mới là chứng minh cho *mọi* mảng hợp lệ.

**Chi phí:** `n` lần cộng, thời gian `Θ(n)` và bộ nhớ phụ `Θ(1)`. Dùng `long` tránh tràn `int` khi tổng các `int` lớn; với độ dài mảng Java được biểu diễn bởi `int`, tổng của các giá trị `int` vẫn nằm trong phạm vi `long`. Nếu bài toán có dữ liệu ngoài phạm vi này hoặc phép tính trung gian khác, phải phân tích lại nguy cơ tràn số.

## 4. Ví dụ 2 — Tìm vị trí xuất hiện đầu tiên

**Bài toán:** với mảng `a` không phải `null`, trả về chỉ số **nhỏ nhất** `i` có `a[i] == target`; nếu không có thì trả `-1`. Không đòi hỏi mảng đã sắp xếp.

```java
static int firstIndexOf(int[] a, int target) {
    int i = 0;
    while (i < a.length && a[i] != target) {
        i++;
    }
    return i == a.length ? -1 : i;
}
```

**Bất biến ở đầu lượt:** `0 ≤ i ≤ n` và **mọi phần tử ở các vị trí `j < i` đều khác `target`**. Dạng ký hiệu là `∀j, 0 ≤ j < i : a[j] != target`.

- **Khởi tạo:** `i = 0`, chưa có vị trí nào trước `i`; mệnh đề “mọi phần tử trước `i` đều khác `target`” đúng trên tập rỗng.
- **Bảo toàn:** một lượt chỉ chạy khi `i < n` và `a[i] != target`. Vậy sau `i++`, toàn bộ tiền tố mới `[0,i)` vẫn không có `target`.
- **Thoát vì `i == n`:** toàn mảng đã bị loại trừ, nên `-1` là đúng.
- **Thoát vì `a[i] == target`:** chỉ số `i` thực sự chứa `target`; bất biến bảo đảm mọi chỉ số nhỏ hơn không chứa nó, nên đây là **lần xuất hiện đầu tiên**.
- **Kết thúc:** `V = n - i` giảm 1 ở mỗi lượt. Phép truy cập `a[i]` an toàn nhờ toán tử `&&` đánh giá từ trái sang phải và dừng sớm khi `i < n` sai.

Ví dụ `[5, 8, 5, 2]` với `target = 5` trả `0`, không trả `2`. Nếu chỉ đặt bất biến “mọi phần tử đã duyệt là số nguyên” thì phát biểu có thể đúng nhưng **không đủ mạnh** để suy ra tính *đầu tiên* của kết quả.

**Chi phí:** trường hợp tốt nhất `Θ(1)`; trường hợp xấu nhất `Θ(n)`; bộ nhớ phụ `Θ(1)`.

## 5. Ví dụ 3 — Tìm vị trí chèn đầu tiên bằng khoảng nửa mở

Bài toán này đòi hỏi bất biến chặt chẽ hơn vì ta loại **nhiều vị trí trong một lượt**.

**Bài toán:** cho mảng `a` **đã sắp xếp không giảm** và khóa `key`. Trả về chỉ số `p` nhỏ nhất sao cho `a[p] ≥ key`. Nếu mọi phần tử nhỏ hơn `key` thì trả `a.length`. Đây là thao tác thường gọi là `lowerBound`. Khi có nhiều phần tử bằng `key`, kết quả chính là chỉ số đầu tiên của chúng.

```java
static int lowerBound(int[] a, int key) {
    int left = 0;
    int right = a.length;

    while (left < right) {
        int mid = left + (right - left) / 2;
        if (a[mid] < key) {
            left = mid + 1;
        } else {
            right = mid;
        }
    }
    return left;
}
```

**Lựa chọn mô hình:** khoảng ứng viên là `[left, right)`, **bao gồm `left` và loại trừ `right`**. Đặt `n = a.length`.

**Bất biến tại đầu mỗi lượt** gồm ba phần:

1. `0 ≤ left ≤ right ≤ n`.
2. Với mọi `j < left`: `a[j] < key`.
3. Với mọi `j ≥ right` và `j < n`: `a[j] ≥ key`.

Cách đọc: toàn bộ vùng bên trái đã được chứng minh **quá nhỏ**, toàn bộ vùng bên phải đã được chứng minh **đủ lớn**; chỉ khoảng giữa còn cần xem xét vị trí ranh giới.

**Khởi tạo.** `left = 0`, `right = n`. Hai vùng đã loại trừ đều rỗng, nên các mệnh đề về chúng đúng; chỉ số thỏa `0 ≤ 0 ≤ n ≤ n`.

**Bảo toàn, nhánh `a[mid] < key`.** Vì mảng không giảm, mọi phần tử ở vị trí `j ≤ mid` cũng nhỏ hơn `key`. Ta có thể loại cả `mid` và phần bên trái bằng `left = mid + 1`. Vùng bên phải đã được chứng minh từ trước không đổi.

**Bảo toàn, nhánh `a[mid] ≥ key`.** Vì mảng không giảm, mọi vị trí `j ≥ mid` đều có phần tử `≥ key`. Ta đặt `right = mid`, giữ lại `mid` làm ứng viên có thể là vị trí đầu tiên; vùng bên trái đã được chứng minh không đổi.

**Kết thúc.** Khi `left < right` sai, phần giới hạn chỉ số của bất biến cho `left == right == p`. Các vị trí trước `p` đều có giá trị nhỏ hơn `key`; các vị trí từ `p` đến cuối mảng đều có giá trị `≥ key`. Vậy `p` là ranh giới nhỏ nhất cần tìm. Trường hợp mảng rỗng cho `left = right = 0` ngay từ đầu, nên trả 0 là đúng.

**Chứng minh dừng.** Chọn `V = right - left`. Mỗi lượt có `V > 0` và `left ≤ mid < right`. Nhánh đầu tăng `left` lên ít nhất một; nhánh còn lại giảm `right` xuống ít nhất một. Vì thế `V` luôn giảm nghiêm ngặt và không âm. Cách tính `mid = left + (right - left) / 2` cũng tránh phép cộng `left + right` có thể tràn `int`.

### Truy vết với phần tử trùng nhau

Với `a = [1, 3, 3, 8, 10]` và `key = 3`:

| Trạng thái trước lượt | `mid` | `a[mid]` | Chứng minh để thu hẹp | Trạng thái sau lượt |
|---|---:|---:|---|---|
| `[0, 5)` | 2 | 3 | `a[2] ≥ 3`; vị trí đầu tiên không nằm sau 2 | `[0, 2)` |
| `[0, 2)` | 1 | 3 | `a[1] ≥ 3`; giữ lại chỉ số 1 | `[0, 1)` |
| `[0, 1)` | 0 | 1 | `a[0] < 3`; loại chỉ số 0 | `[1, 1)` |

Khi thoát, `left = right = 1`. Đáp án là 1 dù `a[2]` cũng bằng 3. Với `key = 5`, kết quả 3 (chỉ số của giá trị 8); với `key = 11`, kết quả 5 (vị trí chèn sau phần tử cuối).

**Chi phí:** mỗi lượt giảm khoảng ứng viên xuống cỡ một nửa, nên thời gian xấu nhất `Θ(log(n + 1))`, bộ nhớ phụ `Θ(1)`. Đây là khác biệt quan trọng: phép chứng minh tính đúng dựa vào *phân hoạch chỉ số và thứ tự mảng*, còn chứng minh độ phức tạp dựa vào *mức thu hẹp khoảng*.

**Không được bỏ điều kiện trước:** nếu mảng chưa sắp xếp, lập luận “mọi phần tử bên trái cũng nhỏ hơn” hoặc “mọi phần tử bên phải cũng lớn hơn” không hợp lệ. Khi đó mã vẫn có thể kết thúc, nhưng kết quả không được bảo đảm đúng.

## 6. Ví dụ 4 — Vòng lặp lồng nhau trong sắp xếp chèn

Chứng minh thuật toán nhiều vòng lặp nên được tách thành **bất biến vòng ngoài** và **bất biến vòng trong**.

Sắp xếp chèn (`insertion sort`) lấy từng phần tử ở vị trí `i`, giữ nó trong biến `key`, dời các phần tử lớn hơn sang phải rồi đặt `key` vào vị trí thích hợp.

```java
static void insertionSort(int[] a) {
    for (int i = 1; i < a.length; i++) {
        int key = a[i];
        int j = i - 1;

        while (j >= 0 && a[j] > key) {
            a[j + 1] = a[j];
            j--;
        }
        a[j + 1] = key;
    }
}
```

**Bất biến vòng ngoài:** trước lượt có chỉ số `i`, tiền tố `a[0..i)` đã **sắp xếp không giảm** và chứa đúng **tập hợp đa bội (multiset)** các giá trị ban đầu của tiền tố đó, tức không làm mất hay tự tạo thêm giá trị sau khi hoàn thành mỗi lượt ngoài.

- **Khởi tạo:** trước `i = 1`, tiền tố một phần tử hiển nhiên đã sắp xếp.
- **Bảo toàn:** lấy `key = a[i]`. Vì `a[0..i)` đã sắp xếp, ta dời sang phải những phần tử lớn hơn `key`, rồi chèn `key` vào “khoảng trống” thu được. Tiền tố `a[0..i+1)` trở thành có thứ tự, chứa đúng các giá trị của tiền tố cũ cộng `key`.
- **Kết thúc:** khi `i = n`, toàn bộ `a[0..n)` đã sắp xếp; cùng tính bảo toàn multiset, đây là một hoán vị được sắp xếp của đầu vào.

**Bất biến vòng trong:** tại đầu mỗi lượt trong, `key` còn được giữ nguyên trong biến riêng; các phần tử đã dời vào vùng từ `j+2` đến `i` đều **lớn hơn `key`**, theo đúng thứ tự của đoạn ban đầu. Vị trí `j+1` là nơi sẽ đặt `key` nếu không còn phần tử nào cần dời. Khi `j < 0` hoặc `a[j] ≤ key`, đặt `key` vào `a[j+1]` làm tiền tố có thứ tự. Trong quá trình dời, mảng có thể tạm thời chứa bản sao của một giá trị; vì vậy chỉ khẳng định bảo toàn multiset **sau khi chèn lại `key`**, không áp dụng máy móc bất biến vòng ngoài ở giữa thân vòng trong.

Đại lượng dừng của vòng trong là `j + 1`: khi vòng còn chạy nó dương và giảm 1 mỗi lượt. Vòng ngoài có đại lượng `n - i`. Do dùng điều kiện `a[j] > key`, các phần tử bằng `key` không vượt qua nhau; thuật toán giữ được thứ tự tương đối của các giá trị bằng nhau (**ổn định**).

Với đầu vào `[5, 2, 4, 1]`, sau từng lượt ngoài ta được:

| Lượt ngoài | Tiền tố đã sắp xếp | Mảng sau khi chèn |
|---|---|---|
| `i = 1` | `[2, 5]` | `[2, 5, 4, 1]` |
| `i = 2` | `[2, 4, 5]` | `[2, 4, 5, 1]` |
| `i = 3` | `[1, 2, 4, 5]` | `[1, 2, 4, 5]` |

Độ phức tạp thời gian xấu nhất `Θ(n²)` do có thể dời gần `i` phần tử ở lượt `i`; tốt nhất `Θ(n)` khi mảng đã sắp xếp. Bộ nhớ phụ `Θ(1)`.

## 7. Chương trình Java 17+ có thể biên dịch và chạy

Toàn bộ ví dụ được ghép thành một chương trình độc lập để thử dữ liệu thật và đối chiếu kết quả với các chứng minh vừa trình bày.

Lưu nguyên mã sau vào tệp `LoopInvariantDemo.java`:

```java
import java.util.Arrays;

public final class LoopInvariantDemo {
    static long sumArray(int[] a) {
        long sum = 0;
        for (int i = 0; i < a.length; i++) {
            sum += a[i];
        }
        return sum;
    }

    static int firstIndexOf(int[] a, int target) {
        int i = 0;
        while (i < a.length && a[i] != target) {
            i++;
        }
        return i == a.length ? -1 : i;
    }

    // Preconditions: a != null; a sorted in nondecreasing order.
    static int lowerBound(int[] a, int key) {
        int left = 0;
        int right = a.length;
        while (left < right) {
            int mid = left + (right - left) / 2;
            if (a[mid] < key) {
                left = mid + 1;
            } else {
                right = mid;
            }
        }
        return left;
    }

    static void insertionSort(int[] a) {
        for (int i = 1; i < a.length; i++) {
            int key = a[i];
            int j = i - 1;
            while (j >= 0 && a[j] > key) {
                a[j + 1] = a[j];
                j--;
            }
            a[j + 1] = key;
        }
    }

    public static void main(String[] args) {
        System.out.println("Sum: " + sumArray(new int[]{4, -2, 7}));
        System.out.println("First 5: " + firstIndexOf(new int[]{5, 8, 5, 2}, 5));
        System.out.println("Missing 7: " + firstIndexOf(new int[]{5, 8, 5, 2}, 7));

        int[] sorted = {1, 3, 3, 8, 10};
        System.out.println("Bound 3: " + lowerBound(sorted, 3));
        System.out.println("Bound 5: " + lowerBound(sorted, 5));
        System.out.println("Bound 11: " + lowerBound(sorted, 11));
        System.out.println("Empty bound: " + lowerBound(new int[0], 2));

        int[] toSort = {5, 2, 4, 1};
        insertionSort(toSort);
        System.out.println("Sorted: " + Arrays.toString(toSort));
    }
}
```

Trong terminal tại thư mục chứa tệp:

```bash
javac LoopInvariantDemo.java
java LoopInvariantDemo
```

Kết quả:

```text
Sum: 9
First 5: 0
Missing 7: -1
Bound 3: 1
Bound 5: 3
Bound 11: 5
Empty bound: 0
Sorted: [1, 2, 4, 5]
```

Mã giả định các mảng truyền vào khác `null`. Riêng `lowerBound` còn giả định đã sắp xếp không giảm. Nếu thay đổi hợp đồng (ví dụ yêu cầu trả về lỗi rõ ràng khi nhận `null`), cần bổ sung xử lý đầu vào và chứng minh phù hợp.

## 8. Những lỗi chứng minh và lỗi cài đặt thường gặp

| Lỗi | Vì sao nguy hiểm | Cách kiểm tra hoặc khắc phục |
|---|---|---|
| Chọn bất biến quá yếu, như “`i ≥ 0`” | Khi thoát vẫn không suy được đầu ra đúng | Liên hệ bất biến với phần dữ liệu đã xử lý và `Q` |
| Chọn một điều kiện chỉ đúng ở cuối, không đúng ở đầu | Không chứng minh được bước khởi tạo | Thử ngay trạng thái trước lượt đầu tiên, kể cả mảng rỗng |
| Chỉ xét thân vòng lặp mà quên phần `for` cập nhật | Bất biến có thể sai ở lần kiểm tra kế tiếp | Mô phỏng đủ chu kỳ kiểm tra → thân → cập nhật → kiểm tra |
| Nhầm đoạn `[left,right]` với `[left,right)` | Lệch một chỉ số hoặc truy cập ngoài mảng | Ghi rõ cận nào được lấy, cận nào không; thử n = 0, 1 |
| Đổi `left = mid + 1` thành `left = mid` | Khi `mid == left`, khoảng không giảm; vòng có thể lặp mãi | Chỉ ra `V` và chứng minh nó giảm ở **mọi** nhánh |
| Trong `lowerBound` dùng `right = mid - 1` | Có thể loại vị trí `mid` dù đó là đáp án đầu tiên | Nhánh `a[mid] ≥ key` phải giữ lại `mid`: `right = mid` |
| Bỏ qua phần tử trùng nhau hoặc số âm | Kết quả đúng với dữ liệu mẫu nhưng sai ở đầu vào hợp lệ khác | Xác định hợp đồng và kiểm tra các trường hợp biên |
| Chứng minh tính đúng nhưng không chứng minh dừng | Thuật toán có thể lặp vô hạn | Xây dựng đại lượng không âm giảm nghiêm ngặt |
| Xem kiểm thử trên vài đầu vào là chứng minh | Chưa bao phủ vô hạn hoặc rất nhiều đầu vào có thể có | Kiểm thử để tìm lỗi, lập luận để chứng minh tính tổng quát |
| Dùng bất biến vòng ngoài giữa lúc vòng trong đang dời phần tử | Mảng có thể tạm chứa giá trị bị nhân đôi | Phân biệt điểm kiểm tra của hai vòng; lưu `key` riêng |

**Phản ví dụ quan trọng:** nếu trong tìm kiếm nhị phân viết `left = mid` khi `a[mid] < key`, với `a = [1]` và `key = 2`, trạng thái `left = 0, right = 1` cho `mid = 0` ở mọi lượt; `left` không đổi, nên vòng lặp không dừng. Ví dụ này bác bỏ được lời khẳng định “mỗi lượt chắc chắn thu hẹp khoảng” dù một vài lần chạy khác có vẻ đúng.

Một cách hữu ích để tìm lỗi là **truy vết bằng bảng**: ghi trạng thái trước khi kiểm tra điều kiện, xác định nhánh thực thi, ghi trạng thái sau cập nhật, rồi đối chiếu lại bất biến và đại lượng tiến triển. Nếu một nhánh không giảm `V` hoặc không bảo toàn `I` thì phải sửa mã hay sửa lập luận trước khi tuyên bố đúng.

## 9. Luyện tập tự chứng minh

**Bài 1 — Đếm phần tử dương.** Viết hàm trả về số phần tử `> 0` trong mảng. Chọn bất biến liên hệ biến `count` với số phần tử dương trong tiền tố `[0,i)`, chứng minh khởi tạo–bảo toàn–kết thúc, rồi cho biết độ phức tạp.

*Gợi ý:* khi duyệt đến vị trí `i`, chỉ tăng `count` nếu `a[i] > 0`. Dùng `V = n - i`.

**Bài 2 — Sửa vòng lặp sai.** Một người dùng `left = mid` trong nhánh `a[mid] < key` của `lowerBound`. Tìm một đầu vào khiến vòng lặp không dừng và sửa đúng một lệnh.

*Đáp án đối chiếu:* `a = [1], key = 2`; thay bằng `left = mid + 1`.

**Bài 3 — Chứng minh phần tử nhỏ nhất.** Với mảng không rỗng, thiết kế vòng lặp duy trì `min` là giá trị nhỏ nhất của tiền tố đã xét. Viết `P`, `I`, `Q` và `V`; giải thích vì sao điều kiện “mảng không rỗng” cần thiết nếu khởi tạo `min = a[0]`.

*Gợi ý:* bắt đầu xét từ `i = 1`; ở đầu lượt, `min` là giá trị nhỏ nhất trong `a[0..i)`. Kết thúc khi `i = n`.

**Bài 4 — Bất biến vòng lồng nhau.** Giải thích vì sao câu “toàn bộ mảng luôn được sắp xếp” **không phải** bất biến đúng của sắp xếp chèn. Nêu tiền tố nào đã sắp xếp ở đầu vòng ngoài và lý do phải lưu `key` trước khi dời các phần tử.

*Gợi ý:* ở đầu lượt ngoài `i`, chỉ tiền tố `[0,i)` chắc chắn đã sắp xếp. Trong quá trình dịch, giữ `key` bảo đảm không làm mất giá trị cần chèn.

**Bài 5 — Đối chiếu chứng minh và chi phí.** `sumArray` và `lowerBound` đều có bất biến và đại lượng tiến triển. Vì sao một hàm cần `Θ(n)` bước ở trường hợp xấu nhất, còn hàm kia chỉ cần `Θ(log(n+1))`?

*Gợi ý:* `sumArray` xử lý thêm đúng một phần tử mỗi lượt; `lowerBound` loại xấp xỉ một nửa các ứng viên ở mỗi lượt nhờ điều kiện sắp xếp.

## Ghi nhớ

- **Phát biểu đúng bài toán trước:** chỉ rõ điều kiện đầu vào `P` và điều kiện đầu ra `Q`.
- **Chọn bất biến đủ mạnh:** mô tả cái gì đã được chứng minh đúng về phần dữ liệu đã xử lý, đồng thời giữ chỉ số trong phạm vi hợp lệ.
- **Chứng minh theo ba điểm:** bất biến đúng lúc khởi tạo, được bảo toàn sau mỗi lượt và kết hợp với điều kiện thoát để suy ra kết quả.
- **Chứng minh vòng lặp dừng riêng:** tìm đại lượng bị chặn dưới và giảm nghiêm ngặt ở mọi nhánh còn tiếp tục.
- **Dùng truy vết và kiểm thử để kiểm tra lập luận:** đặc biệt với đầu vào rỗng, một phần tử, trùng nhau và ranh giới chỉ số. Chúng hỗ trợ phát hiện phản ví dụ, nhưng không thay thế chứng minh tổng quát.

Khi làm được các bước trên, ta có thể giải thích **vì sao từng lần cập nhật trạng thái là hợp lệ**, thay vì chỉ nói “chương trình chạy ra kết quả đúng”.
