# Tìm kiếm tuyến tính và điều kiện dừng sớm

**Tìm kiếm tuyến tính (linear search, sequential search)** lần lượt kiểm tra các phần tử của một dãy để tìm phần tử thỏa điều kiện. Đây là phương pháp tìm kiếm cơ bản, dùng được cả khi dữ liệu chưa sắp xếp và không có cấu trúc chỉ mục hỗ trợ. Sức mạnh của kỹ thuật nằm ở sự đơn giản và tính đúng đắn dễ chứng minh. Tuy nhiên, **dừng vòng lặp ở đâu** ảnh hưởng trực tiếp đến kết quả, số lần kiểm tra và điều kiện áp dụng.

Bài học tập trung vào hai câu hỏi: (1) khi nào được trả kết quả ngay sau khi gặp phần tử phù hợp; (2) khi nào có thể kết luận rằng **không phần tử nào còn lại** có thể phù hợp, từ đó dừng sớm một cách đúng đắn.

**Mục tiêu:** viết được thuật toán tìm vị trí đầu tiên hoặc cuối cùng theo yêu cầu; giải thích bất biến vòng lặp; dùng điều kiện dừng sớm hợp lệ trên dãy có thứ tự; nhận biết các phản ví dụ khi dữ liệu chưa sắp xếp; đếm số phép so sánh và phân tích best/worst/average case; triển khai và kiểm thử bằng Java 17+.

## 1. Bài toán tìm kiếm phải quy định chính xác kết quả

Cho dãy `a[0], a[1], ..., a[n−1]`, số nguyên `target` và chỉ số **0-based**. Cụm từ “tìm phần tử target” chưa đủ để chọn điểm dừng. Một số hợp đồng phổ biến là:

| Mục tiêu | Kết quả cần trả về | Có thể dừng khi gặp lần khớp đầu tiên từ trái? |
|---|---|---|
| Kiểm tra sự tồn tại | `true` nếu có ít nhất một phần tử bằng `target` | **Có** |
| Tìm chỉ số đầu tiên | Chỉ số nhỏ nhất `i` thỏa `a[i] == target`, nếu không có thì `-1` | **Có** |
| Tìm một vị trí bất kỳ | Một chỉ số hợp lệ có giá trị khớp, hoặc `-1` | **Có** |
| Tìm chỉ số cuối cùng | Chỉ số lớn nhất `i` có giá trị khớp, hoặc `-1` | **Không**, nếu quét từ trái trên dãy chưa biết quy luật |
| Đếm số lần xuất hiện | Số chỉ số `i` có `a[i] == target` | **Không**, nếu chưa loại trừ được những phần tử còn lại |
| Liệt kê tất cả vị trí | Danh sách mọi chỉ số khớp, theo yêu cầu thứ tự | **Không**, trừ khi có một quy tắc chặn phần còn lại |

Ví dụ với `a = [8, 3, 9, 3, 6]` và `target = 3`: chỉ số đầu tiên là 1; chỉ số cuối cùng là 3; số lần xuất hiện là 2; một vị trí bất kỳ có thể là 1 hoặc 3. Nếu dừng tại vị trí 1, thuật toán **đúng cho câu hỏi “đầu tiên”** nhưng **sai cho câu hỏi “cuối cùng” hoặc “đếm tất cả”**.

Cần làm rõ thêm: mảng rỗng có hợp lệ không? Phần tử có thể trùng không? “Bằng” nghĩa là `==` cho kiểu nguyên, `equals` cho đối tượng hay phép so sánh do đề bài quy định? Nếu không tìm thấy, trả `-1`, `null`, giá trị tùy chọn hay ném ngoại lệ? Ví dụ bên dưới dùng mảng `int[]` và trả `-1` khi không tìm thấy.

## 2. Thuật toán tìm kiếm tuyến tính cơ bản

Giả sử `a` là mảng số nguyên không sắp xếp và cần **vị trí xuất hiện đầu tiên** của `target`:

~~~java
static int firstIndex(int[] a, int target) {
    for (int i = 0; i < a.length; i++) {
        if (a[i] == target) {
            return i;
        }
    }
    return -1;
}
~~~

Đây là phương thức Java minh họa, cần đặt trong một lớp để biên dịch độc lập. Cách hoạt động:

1. Duyệt từ chỉ số 0 tới `n−1`.
2. Mỗi lần kiểm tra, nếu `a[i] == target` thì trả `i` ngay.
3. Nếu đã kiểm tra hết dãy mà không thấy, trả `-1`.

Khi tìm **chỉ số đầu tiên**, không cần xét phần sau phần tử khớp đầu tiên: mọi vị trí về sau đều có chỉ số lớn hơn `i`, nên không thể cải thiện đáp án “nhỏ nhất”. Đây là **dừng sớm do mục tiêu đã được đáp ứng**, hoàn toàn không cần mảng được sắp xếp.

Đặc điểm quan trọng: thuật toán không yêu cầu giá trị dương, không yêu cầu các phần tử khác nhau, không yêu cầu kích thước lớn hay nhỏ và không đòi hỏi vùng nhớ phụ tăng theo `n`.

## 3. Chứng minh tính đúng đắn bằng bất biến vòng lặp

Với thuật toán tìm vị trí đầu tiên ở trên, bất biến trước lượt kiểm tra tại chỉ số `i` là:

**“Tất cả các phần tử có chỉ số nhỏ hơn i đã được kiểm tra và đều khác target.”**

- **Khởi tạo:** khi `i = 0`, chưa có phần tử đứng trước i, nên bất biến đúng.
- **Duy trì:** nếu `a[i] != target`, việc tăng i thêm 1 bảo đảm toàn bộ các chỉ số nhỏ hơn i mới đều không khớp.
- **Dừng do tìm thấy:** nếu `a[i] == target`, bất biến chứng minh không có phần tử khớp nào ở vị trí nhỏ hơn i. Trả i vì vậy chính là trả **lần xuất hiện đầu tiên**.
- **Dừng do hết dãy:** khi `i = n` mà chưa trả về, mọi phần tử đều đã được kiểm tra và đều khác target; trả `-1` là đúng.

Cấu trúc chứng minh này cũng cho thấy **vì sao dừng ngay khi gặp giá trị lớn hơn target trên dãy chưa sắp xếp là sai**: bất biến chỉ nói gì về phần đã duyệt, không chứng minh được phần chưa duyệt chứa những gì.

Ví dụ phản chứng:

`a = [10, 2, 7, 3], target = 3`.

Nếu tại `a[0]=10` ta dừng vì `10 > 3`, thuật toán trả `-1`, nhưng `a[3]=3`. Điều kiện “lớn hơn target” chỉ giúp loại trừ phần còn lại khi dữ liệu có **bảo đảm thứ tự thích hợp**.

## 4. Phân tích chi phí: tốt nhất, xấu nhất và trung bình

Gọi `n = a.length` và đếm một lần so sánh khóa khi thực hiện `a[i] == target`.

| Tình huống | Số lần so sánh khóa | Thời gian theo mô hình RAM |
|---|---:|---|
| Mảng rỗng `n=0` | 0 | Θ(1) cho lời gọi và trả kết quả |
| Có `target` ngay tại chỉ số 0, `n>0` | 1 | Θ(1) |
| Lần xuất hiện đầu tiên ở chỉ số `k` | `k+1` | Θ(k+1) |
| Không có `target` | `n` | Θ(n) khi `n>0` |
| Chỉ xuất hiện ở vị trí cuối | `n` | Θ(n) |

**Best case:** với `n>0` và target ở vị trí đầu, chỉ cần một phép so sánh, nên Θ(1).

**Worst case:** target vắng mặt hoặc xuất hiện lần đầu ở cuối dãy, phải kiểm tra n phần tử, nên Θ(n).

**Average case:** phải có **giả thiết phân bố đầu vào**. Chẳng hạn target chắc chắn xuất hiện đúng một lần và vị trí của nó phân bố đều trên `0..n−1`, số phép so sánh kỳ vọng là:

`E[C] = (1 + 2 + ... + n)/n = (n+1)/2 = Θ(n)`.

Nếu có xác suất không tìm thấy, có thể xuất hiện nhiều lần hoặc xác suất các vị trí không đều nhau, giá trị kỳ vọng cần tính lại. Không nên nói “trung bình là n/2” mà không đưa giả thiết.

**Không nhầm O(n) với luôn chạy n lần:** O(n) là cận trên tiệm cận. Dừng sớm giúp giảm số phép kiểm tra trên nhiều đầu vào và có thể cải thiện hiệu năng thực tế, nhưng **không biến worst-case từ O(n) thành O(1)**.

Về bộ nhớ phụ, thuật toán chỉ lưu một biến chỉ số và tham số, nên **Θ(1)**. Nếu đầu vào được truyền dưới dạng mảng đã tồn tại, không tính bộ nhớ của mảng gốc vào bộ nhớ phụ.

## 5. Dừng sớm khi tìm thấy: điều kiện thuộc về mục tiêu

**Điều kiện thứ nhất:** phần tử hiện tại đã cung cấp một đáp án đủ để kết thúc công việc.

- Tìm **sự tồn tại**: chỉ cần một phần tử khớp.
- Tìm **chỉ số đầu tiên**: khi duyệt từ trái sang phải, chỉ số khớp đầu tiên là nhỏ nhất.
- Tìm **chỉ số cuối cùng**: khi duyệt từ phải sang trái, chỉ số khớp đầu tiên gặp theo hướng đó là lớn nhất.
- Tìm **bất kỳ** vị trí thỏa điều kiện: có thể trả ngay khi gặp một vị trí phù hợp.
- Tìm **giá trị tối ưu** (ví dụ nhỏ nhất/lớn nhất) hoặc **tất cả** kết quả: việc thấy một ứng viên chưa chắc đủ, trừ khi có chứng minh rằng nó đã tối ưu hoặc không còn ứng viên khác.

Ví dụ tìm chỉ số cuối cùng trên mảng chưa sắp xếp bằng cách đi từ phải sang trái:

~~~java
static int lastIndex(int[] a, int target) {
    for (int i = a.length - 1; i >= 0; i--) {
        if (a[i] == target) {
            return i;
        }
    }
    return -1;
}
~~~

Dù dữ liệu không sắp xếp, cách quét ngược vẫn bảo đảm vị trí đầu tiên khớp khi quét từ phải có **chỉ số lớn nhất**. Nếu một đề bài bắt buộc duyệt theo luồng chỉ tiến (không thể quay ngược), phải lưu vị trí khớp mới nhất và tiếp tục đọc tới cuối để tìm “cuối cùng”.

Cùng một lệnh `return` là đúng hay sai phụ thuộc vào **định nghĩa kết quả cần trả**, không đơn thuần vào việc điều kiện `a[i] == target` đã đúng.

## 6. Dừng sớm nhờ dãy đã sắp xếp tăng dần

Giả sử đặc tả bảo đảm mảng đã sắp xếp theo **thứ tự không giảm**:

`a[0] ≤ a[1] ≤ ... ≤ a[n−1]`.

Tìm lần xuất hiện đầu tiên của target bằng quét từ trái sang phải:

~~~java
static int firstIndexSorted(int[] a, int target) {
    for (int i = 0; i < a.length; i++) {
        if (a[i] == target) {
            return i;
        }
        if (a[i] > target) {
            break;
        }
    }
    return -1;
}
~~~

Đây cũng là phương thức minh họa đặt trong một lớp Java. Ngoài dừng khi đã tìm thấy, thuật toán dừng sớm khi **`a[i] > target`**. Tại sao hợp lệ?

Do mảng không giảm, với mọi `j > i` ta có `a[j] ≥ a[i] > target`. Vậy **không vị trí còn lại nào có thể bằng target**, nên trả `-1` là đúng.

Nhìn dưới góc độ bất biến, phần đã duyệt không chứa target; khi gặp phần tử lớn hơn target thì **cả phần chưa duyệt cũng được chứng minh là không chứa target**. Chính chứng minh bổ sung này cho phép dừng trước khi tới cuối mảng.

### Ví dụ có trùng lặp

`a = [1, 3, 3, 3, 6, 8]`:

- Tìm `target = 3`: so sánh lần lượt 1, 3; gặp 3 tại chỉ số 1 thì trả 1, chính là **vị trí đầu tiên**.
- Tìm `target = 4`: so sánh 1, 3, 3, 3, 6; gặp 6 > 4 thì có thể dừng, trả -1. Không cần kiểm tra 8.
- Tìm `target = 0`: gặp phần tử đầu tiên 1 > 0, trả -1 sau **một** lần so sánh.
- Tìm `target = 9`: không có phần tử nào vượt 9, phải đi hết sáu phần tử, trả -1.

Lưu ý quan trọng: **dừng sớm trên mảng sắp xếp không đổi worst-case Θ(n)**. Nếu target lớn hơn mọi phần tử hoặc xuất hiện cuối mảng, vẫn phải duyệt hết n phần tử.

### Mảng giảm dần thì điều kiện đảo lại

Nếu `a[0] ≥ a[1] ≥ ... ≥ a[n−1]` và duyệt từ trái qua phải để tìm target, có thể kết luận phần còn lại không khớp khi gặp **`a[i] < target`**, bởi tất cả phần sau đều không lớn hơn `a[i]`. Dùng `a[i] > target` như với mảng tăng dần sẽ sai.

### Đừng nhầm `>=` với `>`

Nếu code kiểm tra `if (a[i] >= target) break;` **trước** điều kiện bằng nhau, nó sẽ bỏ lỡ chính phần tử target. Với thuật toán tìm vị trí, phải xét bằng nhau trước rồi mới xét điều kiện loại trừ. Có thể viết một nhánh gộp `if (a[i] >= target) return a[i] == target ? i : -1;`, nhưng cách tách hai điều kiện thường dễ đọc và kiểm chứng hơn.

## 7. Tìm lần xuất hiện cuối cùng trên mảng tăng dần

Khi có phần tử trùng nhau, tìm lần cuối không thể trả ngay khi quét từ trái và gặp target lần đầu. Có hai cách đúng:

**Cách 1: quét từ trái, ghi nhận vị trí khớp mới nhất.** Khi gặp phần tử lớn hơn target, có thể dừng do dãy tăng dần. Nếu số lượng target có thể lớn, phải đi qua các phần tử bằng target để biết vị trí cuối.

**Cách 2: quét từ phải sang trái và trả ngay khi gặp target.** Do đi từ chỉ số lớn về nhỏ, đây chính là vị trí cuối. Có thể dừng sớm nếu gặp phần tử **nhỏ hơn** target, vì các phần tử còn lại ở phía trái cũng không lớn hơn phần tử vừa gặp:

~~~java
static int lastIndexSorted(int[] a, int target) {
    for (int i = a.length - 1; i >= 0; i--) {
        if (a[i] == target) {
            return i;
        }
        if (a[i] < target) {
            break;
        }
    }
    return -1;
}
~~~

Với `[1,3,3,3,6,8]` và target 3, quét ngược so sánh 8, 6, 3; trả chỉ số 3 sau ba lượt. Nếu target 4, quét 8, 6, 3 rồi dừng khi 3 < 4, trả -1.

Sự khác biệt giữa “lần đầu” và “lần cuối” cho thấy **hướng duyệt cũng là một yếu tố của điều kiện dừng sớm**.

## 8. Khi nào hoàn toàn không được dùng dừng sớm theo giá trị?

Mọi quy tắc loại trừ cần dựa trên **bảo đảm về các phần tử chưa xem**. Các tình huống sau không đủ điều kiện:

1. **Dãy chưa sắp xếp:** gặp số lớn hơn target không chứng minh các số về sau cũng lớn. Phản ví dụ `[10,2,7,3]`, target 3.
2. **Chỉ một đoạn con được sắp xếp:** gặp số vượt target trong đoạn đầu không suy ra những đoạn sau cũng có thứ tự tương ứng.
3. **Thứ tự sắp xếp không khớp kiểu so sánh tìm kiếm:** ví dụ dãy đã sắp theo một comparator phân biệt dấu nhưng tìm theo comparator không phân biệt dấu; quy tắc `>` có thể không còn đúng theo tiêu chí đang tìm.
4. **Dữ liệu thay đổi trong lúc duyệt:** nếu các phần tử được thêm, sửa hoặc hoán đổi mà không duy trì điều kiện thứ tự, chứng minh dựa trên dãy không đổi không áp dụng được.
5. **Mục tiêu cần toàn bộ vị trí hoặc số lần xuất hiện:** dừng ngay sau khi thấy một vị trí khớp không đáp ứng yêu cầu.
6. **Điều kiện so sánh không có tính bắc cầu hoặc không ổn định:** nếu cách so sánh có side effect hoặc trả kết quả thay đổi theo thời điểm, không thể áp dụng suy luận từ thứ tự một cách tùy tiện.

Với một luồng dữ liệu chưa sắp xếp, chỉ việc đã đọc `k` phần tử không cho biết gì chắc chắn về phần còn lại. Để chứng minh không có target, trong trường hợp xấu nhất **phải kiểm tra toàn bộ**. Đây là lý do tính đúng đắn và cận xấu nhất Θ(n) của tìm kiếm tuyến tính có liên hệ trực tiếp.

### Bất biến tổng quát của dừng sớm

Mọi phép dừng sớm đều cần một trong hai chứng minh:

- **Đã đủ lời giải:** câu trả lời hiện tại thỏa hợp đồng và không cần thông tin nào từ phần còn lại để kết luận.
- **Đã loại trừ mọi ứng viên còn lại:** một bất biến, cận trên/cận dưới, thứ tự hoặc điều kiện đơn điệu chứng minh tất cả phần chưa xử lý không thể thay đổi đáp án.

Nếu không chỉ ra được ít nhất một chứng minh như trên, “dừng khi thấy có vẻ không còn đáp án” chỉ là phỏng đoán.

## 9. Java 17+ hoàn chỉnh: đếm số phép so sánh và dừng sớm

Chương trình sử dụng `record` (hỗ trợ trong Java 17) để trả cả **chỉ số tìm thấy** và **số lần so sánh phần tử với khóa**. Bộ đếm không tính điều kiện vòng lặp, tạo đối tượng, phép gán hay việc in kết quả.

- `firstAnywhere`: mảng bất kỳ, tìm vị trí đầu tiên.
- `firstSortedAscending`: mảng tăng không nghiêm ngặt, tìm vị trí đầu tiên và dừng nếu giá trị đã lớn hơn target.
- `lastSortedAscending`: mảng tăng không nghiêm ngặt, tìm vị trí cuối bằng quét từ phải.
- Cả ba hàm chấp nhận mảng rỗng và trả `index = -1` nếu không thấy.
- Hai hàm có chữ `Sorted` **yêu cầu dữ liệu đầu vào đã sắp xếp không giảm**; chúng không tự sắp xếp và không tự kiểm tra tính có thứ tự.

Lưu tệp **`LinearSearchEarlyStop.java`**:

~~~java
public final class LinearSearchEarlyStop {
    record Result(int index, int comparisons) {}

    static Result firstAnywhere(int[] a, int target) {
        int comparisons = 0;
        for (int i = 0; i < a.length; i++) {
            comparisons++;
            if (a[i] == target) {
                return new Result(i, comparisons);
            }
        }
        return new Result(-1, comparisons);
    }

    static Result firstSortedAscending(int[] a, int target) {
        int comparisons = 0;
        for (int i = 0; i < a.length; i++) {
            int value = a[i];
            comparisons++;

            if (value == target) {
                return new Result(i, comparisons);
            }
            if (value > target) {
                break;
            }
        }
        return new Result(-1, comparisons);
    }

    static Result lastSortedAscending(int[] a, int target) {
        int comparisons = 0;
        for (int i = a.length - 1; i >= 0; i--) {
            int value = a[i];
            comparisons++;

            if (value == target) {
                return new Result(i, comparisons);
            }
            if (value < target) {
                break;
            }
        }
        return new Result(-1, comparisons);
    }

    private static void show(String label, Result result) {
        System.out.printf(
                "%s: index=%d, comparisons=%d%n",
                label, result.index(), result.comparisons());
    }

    public static void main(String[] args) {
        int[] unsorted = {8, 3, 9, 3, 6};
        int[] sorted = {1, 3, 3, 3, 6, 8};

        show("Unsorted first 3", firstAnywhere(unsorted, 3));
        show("Unsorted missing 7", firstAnywhere(unsorted, 7));
        show("Sorted first 3", firstSortedAscending(sorted, 3));
        show("Sorted missing 4", firstSortedAscending(sorted, 4));
        show("Sorted missing 0", firstSortedAscending(sorted, 0));
        show("Sorted last 3", lastSortedAscending(sorted, 3));
        show("Sorted last missing 4", lastSortedAscending(sorted, 4));
        show("Empty array", firstAnywhere(new int[0], 3));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LinearSearchEarlyStop.java
java LinearSearchEarlyStop
~~~

Kết quả chuẩn:

~~~text
Unsorted first 3: index=1, comparisons=2
Unsorted missing 7: index=-1, comparisons=5
Sorted first 3: index=1, comparisons=2
Sorted missing 4: index=-1, comparisons=5
Sorted missing 0: index=-1, comparisons=1
Sorted last 3: index=3, comparisons=3
Sorted last missing 4: index=-1, comparisons=3
Empty array: index=-1, comparisons=0
~~~

**Kiểm tra bằng tay:**

- `unsorted=[8,3,9,3,6]`: lần đầu gặp 3 ở chỉ số 1 sau 2 lần kiểm tra; 7 vắng mặt nên cần 5 lần.
- `sorted=[1,3,3,3,6,8]`: target 4 khiến quét trái kiểm tra 1, 3, 3, 3, 6 rồi dừng, tức 5 lần; không cần xem 8. Target 0 dừng ngay ở 1 sau 1 lần.
- Tìm lần cuối của 3 bằng quét phải: kiểm tra 8, 6, 3; trả chỉ số 3 sau 3 lần.
- Tìm lần cuối của 4 bằng quét phải: kiểm tra 8, 6, 3; gặp 3 < 4 rồi dừng, trả -1 sau 3 lần.
- Mảng rỗng không thực hiện thân vòng lặp, trả -1 với 0 lần so sánh khóa.

**Phân tích:** mọi phương thức dùng O(1) bộ nhớ phụ và có thời gian O(n) trường hợp xấu, do mỗi phần tử được kiểm tra nhiều nhất một lần. Điều kiện dừng sớm làm giảm số lần so sánh với những đầu vào phù hợp nhưng không làm mất trường hợp xấu tuyến tính.

## 10. Tìm kiếm trên `List`, chuỗi và các phần tử không phải `int`

Mẫu thuật toán tuyến tính áp dụng cho nhiều kiểu dữ liệu, nhưng **chi phí một lần truy cập hoặc so sánh có thể khác**.

### 10.1. Mảng và `ArrayList`

Với `int[]` hoặc `ArrayList<E>`, truy cập theo chỉ số hợp lệ được xem O(1). Vòng lặp `for (int i = 0; i < n; i++)` cùng phép `a[i]`/`list.get(i)` vì vậy có thể cho O(n) thời gian nếu mỗi phép so sánh là O(1).

`ArrayList.contains(x)` hoặc `indexOf(x)` thực hiện tìm kiếm dựa trên so sánh bằng nhau; trường hợp xấu là O(n). `indexOf` trả vị trí đầu tiên hoặc -1. Nếu cần tự định nghĩa điều kiện dừng theo thứ tự và có bảo đảm sorted phù hợp, một vòng quét rõ ràng cho phép chứng minh hành vi hơn.

### 10.2. `LinkedList` và `Iterable`

`LinkedList.get(i)` tìm nút theo vị trí, có thể mất O(n) một lần. Nếu gọi `get(i)` trong vòng lặp từ `i=0` tới `n-1`, tổng chi phí có thể lên tới **Θ(n²)**. Để duyệt tuyến tính, dùng iterator hoặc vòng `for-each`:

~~~java
int index = 0;
for (Integer value : values) {
    if (value != null && value.intValue() == target) {
        return index;
    }
    index++;
}
return -1;
~~~

Đây là đoạn mã minh họa trong **phương thức có tham số `Iterable<Integer> values` và `int target`**, trả kiểu `int`; không phải một lớp độc lập. Với `LinkedList` và phép so sánh hằng số, duyệt bằng iterator tốn O(n) ở trường hợp xấu.

Nếu muốn dừng sớm dựa trên thứ tự cho `LinkedList`, vẫn có thể quét iterator và dừng khi giá trị vượt ngưỡng. Nhưng dữ liệu liên kết không có truy cập ngẫu nhiên O(1), nên ưu thế của tìm kiếm nhị phân theo chỉ số trên mảng không tự chuyển sang nó.

### 10.3. `String` và đối tượng

Với mảng `String[]`, `a[i].equals(target)` có thể phải so sánh nhiều ký tự; nếu độ dài lớn nhất của chuỗi là L, một phép bằng nhau có thể tốn O(L) trong trường hợp xấu, dẫn tới thời gian O(nL) cho quét n chuỗi. Ngoài ra, nếu các phần tử có thể `null`, phải kiểm tra null hoặc dùng cách so sánh an toàn phù hợp.

Với dữ liệu đối tượng có `Comparator`, thứ tự dùng để sắp xếp và thứ tự dùng để dừng sớm phải **phù hợp với cùng một comparator**. Nếu comparator coi hai khóa tương đương nhưng `equals` phân biệt chúng, cần định nghĩa rõ thế nào mới là “tìm thấy”; không mặc định hai quan hệ giống nhau.

Đối với `String`, số “ký tự” có thể đo bằng đơn vị mã UTF-16, code point hay cụm ký tự hiển thị; lựa chọn phép so sánh và chi phí phải phù hợp yêu cầu thực tế.

## 11. Có nên sắp xếp trước để dừng sớm?

Nếu mảng ban đầu chưa sắp xếp, sắp xếp nó có thể giúp loại trừ sớm bằng thứ tự, nhưng phải tính **chi phí và sự thay đổi dữ liệu**:

- Sắp xếp mảng `int[]` bằng một thuật toán thông thường có thể mất O(n log n) thời gian; `Arrays.sort(int[])` cung cấp một cách triển khai sắp xếp chuẩn nhưng chi phí chính xác tùy thuật toán và phân bố dữ liệu. Không nên bỏ qua bước sắp xếp khi so sánh tổng chi phí.
- Sau khi sắp xếp, thứ tự phần tử đã thay đổi, nên **chỉ số tìm được trong mảng đã sắp xếp không còn là chỉ số ban đầu**. Nếu bài yêu cầu chỉ số gốc, phải duy trì ánh xạ hoặc chọn cách khác.
- Với **một lần tìm kiếm**, quét tuyến tính O(n) thường đơn giản hơn sắp xếp rồi tìm.
- Với **nhiều truy vấn trên mảng đã sắp xếp và cho phép truy cập ngẫu nhiên**, tìm kiếm nhị phân có cận trường hợp xấu O(log n) cho việc xác định có/không có khóa. Nếu cần lần đầu/lần cuối khi có trùng, hãy dùng biến thể lower bound/upper bound với chứng minh điều kiện biên.
- Nếu chỉ cần một lần đọc dữ liệu dạng luồng, tìm kiếm tuyến tính có thể xử lý từng phần tử ngay khi xuất hiện, không cần giữ toàn bộ mảng hoặc sắp xếp trước.

Tìm kiếm tuyến tính với dừng sớm do thứ tự vẫn có thể hữu ích cho dãy nhỏ, dữ liệu đang được duyệt tuần tự hoặc khi phần tử phù hợp có khả năng ở gần đầu. Tuy nhiên, **nó không thay thế lợi thế tiệm cận của tìm kiếm nhị phân** khi dữ liệu được lưu để truy cập ngẫu nhiên và đã được sắp xếp.

## 12. Tìm kiếm theo điều kiện và ranh giới của dừng sớm

Trong nhiều bài toán, mục tiêu không phải tìm một số bằng target mà tìm **phần tử đầu tiên thỏa vị từ P(x)**, ví dụ:

- Nhân viên đầu tiên có điểm đánh giá vượt một ngưỡng.
- Giao dịch đầu tiên có trạng thái hợp lệ.
- Phần tử đầu tiên có giá trị chẵn.
- Sự kiện đầu tiên thỏa điều kiện thời gian.

Nếu mục tiêu là **chỉ số đầu tiên**, có thể quét từ trái và trả ngay khi P(a[i]) đúng, **không cần P đơn điệu**.

Nhưng nếu muốn dừng và kết luận “về sau sẽ không có phần tử thỏa P”, phải có chứng minh độc lập. Ví dụ, dãy đã sắp xếp không giảm theo giá trị, vị từ cần tìm là “`a[i] == target`”, khi `a[i] > target` thì không phần tử nào sau đó thỏa. Ngược lại, với vị từ “a[i] là số chẵn”, việc gặp một số lẻ trong mảng tăng dần **không** nói rằng các số sau cũng lẻ. Không được dừng dựa trên dấu hiệu không có tính đơn điệu.

Một cách diễn đạt tổng quát: giả sử tại thời điểm i ta có tập ứng viên còn lại S. Chỉ được loại bỏ toàn bộ S nếu bất biến/cận đảm bảo **mọi phần tử trong S đều không thể thay đổi kết quả yêu cầu**. Điều này là nền tảng của các kỹ thuật cắt tỉa (pruning) phức tạp hơn, nhưng ở tìm kiếm tuyến tính cần ghi cụ thể lý do loại bỏ.

## 13. Kiểm thử biên và phản ví dụ cho điều kiện dừng

| Trường hợp | Mảng và target | Kết quả cần kiểm tra |
|---|---|---|
| Dãy rỗng | `[], target=5` | Trả -1, 0 so sánh |
| Một phần tử khớp | `[5], target=5` | Trả 0 |
| Một phần tử không khớp | `[5], target=3` | Trả -1 |
| Khớp ở đầu | `[3,8,2], target=3` | Lần đầu là chỉ số 0, dừng sau 1 lần |
| Khớp ở cuối | `[8,2,3], target=3` | Lần đầu là chỉ số 2, phải xét cả mảng |
| Nhiều phần tử trùng | `[3,2,3,3], target=3` | Lần đầu 0, lần cuối 3 |
| Không tìm thấy | `[1,4,7], target=5` | Trả -1 |
| Mảng tăng, target nhỏ hơn đầu | `[2,5,8], target=1` | Có thể dừng sau 1 lần |
| Mảng tăng, target giữa hai giá trị | `[2,5,8], target=6` | Có thể dừng ở giá trị 8 |
| Mảng tăng, target lớn hơn tất cả | `[2,5,8], target=10` | Kiểm tra cả 3 phần tử, trả -1 |
| Mảng giảm | `[9,6,4], target=5` | Có thể dừng khi gặp 4 < 5 |
| Phản ví dụ cho giả định sorted | `[10,2,7,3], target=3` | Quét không sắp xếp phải trả 3; cấm dừng ở 10 |
| Số âm và số 0 | `[-7,-2,0,3], target=-2` | Tìm thấy ở chỉ số 1; so sánh bình thường |
| Tìm lần cuối trên mảng tăng | `[1,3,3,3,6], target=3` | Trả chỉ số 3, không trả 1 |

Đối với dãy nhỏ, có thể kiểm thử đối chiếu với lời giải tham chiếu: duyệt hết mảng để lấy chỉ số đầu/ cuối và đếm tất cả giá trị khớp. Với các phép dừng sớm **chỉ hợp lệ trên dãy sắp xếp**, hãy sinh mảng ngẫu nhiên rồi **sắp xếp trước khi kiểm thử**. Đồng thời dùng một phản ví dụ chưa sắp xếp để đảm bảo người đọc hiểu rõ tiền điều kiện.

## 14. Những sai lầm phổ biến

1. **Dừng khi `a[i] > target` trên mảng chưa sắp xếp:** không thể loại trừ phần sau. Chỉ dùng khi có bảo đảm sắp xếp không giảm đúng theo phép so sánh.
2. **Trả ngay lần khớp đầu khi đề yêu cầu “cuối cùng” hoặc “tất cả”:** đáp án có thể còn phần tử khác. Chọn hướng duyệt hoặc tiếp tục cập nhật kết quả.
3. **Thay điều kiện `>` bằng `>=` trước khi kiểm tra bằng:** bỏ lỡ target khi chúng bằng nhau.
4. **Nhầm chỉ số 0-based và 1-based:** nếu dùng Java array, vị trí đầu là 0 và giá trị báo không thấy thường là -1; chuyển đầu ra theo hợp đồng đề bài.
5. **Quên mảng rỗng:** vòng lặp không chạy, phải trả đúng giá trị không tìm thấy mà không đọc `a[0]`.
6. **Cho rằng dừng sớm làm worst-case O(1):** vẫn có thể phải đọc hết n phần tử, nên worst-case Θ(n).
7. **Quên chi phí mỗi lần so sánh:** đối tượng, chuỗi dài hoặc comparator phức tạp có thể khiến một lượt không còn O(1).
8. **Dùng `linkedList.get(i)` trong vòng lặp chỉ số:** chi phí truy cập nút làm tổng tìm kiếm có thể O(n²); dùng iterator cho duyệt tuần tự.
9. **Sắp xếp rồi quên chỉ số gốc:** sau khi sắp, chỉ số của phần tử có thể thay đổi; dùng ánh xạ hoặc tìm trực tiếp nếu yêu cầu vị trí ban đầu.
10. **Dữ liệu thay đổi nhưng vẫn tin vào thứ tự cũ:** nếu cập nhật phá bất biến sắp xếp, điều kiện dừng dựa trên thứ tự không còn hợp lệ.
11. **So sánh bằng và so sánh thứ tự không nhất quán:** `equals` và `Comparator` của đối tượng có thể không tương đương; phải xác định cùng tiêu chí tìm kiếm.
12. **Nhầm “không có phần tử nào đã xem khớp” thành “không có phần tử nào khớp”:** khi chưa đến cuối hoặc chưa loại trừ phần còn lại, kết luận vắng mặt là chưa có chứng minh.

## 15. Checklist trước khi chốt thuật toán

- **Kết quả cần trả là gì?** tồn tại, đầu tiên, cuối cùng, một vị trí bất kỳ, đếm số lần hay liệt kê tất cả?
- **Miền dữ liệu được bảo đảm thế nào?** chưa sắp xếp, tăng không giảm, giảm không tăng, có trùng hay có thể thay đổi?
- **Hướng duyệt có phù hợp mục tiêu không?** quét trái để tìm đầu, quét phải để tìm cuối nếu truy cập được?
- **Tại điểm dừng, đã có đáp án đủ tốt chưa?** hay phần còn lại vẫn có thể thay đổi nó?
- **Nếu dừng vì một giá trị vượt ngưỡng, có bất biến chứng minh tất cả phần còn lại cũng bị loại không?**
- **Phép so sánh có cùng ngữ nghĩa với cách sắp xếp không?** giá trị `null` hoặc kiểu dữ liệu đối tượng xử lý thế nào?
- **Tính chi phí có bao gồm truy cập phần tử và so sánh không?** trường hợp tốt nhất, xấu nhất và giả định trung bình đã phân biệt chưa?
- **Đã thử mảng rỗng, nhiều phần tử trùng, target ở biên, target vắng mặt và một phản ví dụ chưa sắp xếp chưa?**

**Ghi nhớ:** tìm kiếm tuyến tính bảo đảm kết quả nhờ duyệt theo thứ tự và kiểm tra từng ứng viên. **Dừng sớm hợp lệ** khi đã có đáp án đáp ứng đầy đủ mục tiêu **hoặc** có chứng minh chắc chắn phần còn lại không thể chứa đáp án cần tìm. Sự khác biệt giữa hai tình huống này quyết định cả tính đúng đắn lẫn số phép so sánh của thuật toán.