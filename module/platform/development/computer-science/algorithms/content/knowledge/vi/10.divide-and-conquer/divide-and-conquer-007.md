# Tìm phần tử chiếm đa số bằng cách kết hợp ứng viên

**Phần tử chiếm đa số (majority element)** của một dãy có `n` phần tử là giá trị xuất hiện **nhiều hơn một nửa** số lần, nghĩa là số lần xuất hiện **`count(x) > n/2`**. Dấu **`>`** là điều kiện nghiêm ngặt: nếu một giá trị xuất hiện đúng `n/2` lần thì **không** phải phần tử đa số.

Ví dụ, `[2,2,1,2,3,2,2]` có 7 phần tử, giá trị `2` xuất hiện 5 lần và `5 > 7/2`, nên `2` là phần tử đa số. Ngược lại, `[1,1,2,2]` không có phần tử đa số: hai giá trị đều xuất hiện 2 lần trên tổng 4, nhưng `2` **không lớn hơn** `4/2`.

Trong nhóm thuật toán **chia để trị (divide and conquer)**, bài toán này có một tính chất đặc biệt: **nếu một giá trị chiếm đa số trong toàn dãy thì nó phải chiếm đa số trong ít nhất một nửa dãy**. Vì vậy, ta có thể giải bài toán cho hai nửa, **kết hợp ứng viên** từ kết quả con, và chỉ kiểm tra những ứng viên có khả năng trở thành phần tử đa số của toàn đoạn.

Bài học trình bày hai cách kết hợp: một cách **xác minh đa số ngay ở mỗi lần hợp nhất** và một cách **kết hợp số dư sau triệt tiêu**, cần xác minh một lần ở cuối. Hai cách có tính đúng đắn liên quan nhưng chi phí thời gian khác nhau. Ví dụ Java 17+ bên dưới cài đặt bản chia để trị trực tiếp và bản bỏ phiếu tuyến tính để đối chiếu.

## 1. Đặc tả bài toán và các khái niệm dễ nhầm

**Đầu vào:** mảng số nguyên `A` có thể rỗng, độ dài `n`. **Đầu ra:** giá trị `v` nếu `count(v) > n/2`; nếu không có giá trị như vậy, trả **`NONE`** (trong Java dùng `OptionalInt.empty()`).

Các điều kiện cần nhớ:

- **Có tối đa một phần tử đa số.** Nếu hai giá trị khác nhau đều xuất hiện hơn `n/2` lần thì tổng số lần xuất hiện của chúng vượt `n`, điều không thể.
- **Đa số không phải phần tử xuất hiện nhiều nhất.** Dãy `[1,1,2,2,3]` có hai giá trị cùng xuất hiện nhiều nhất, nhưng không có giá trị nào vượt `5/2`.
- **Không cần sắp xếp dãy.** Thuật toán chia để trị chỉ đọc và đếm giá trị trên các đoạn; không cần biến đổi thứ tự đầu vào.
- **Mảng rỗng không có phần tử đa số.** Với `n=0`, không tồn tại một giá trị trong mảng đáp ứng bài toán.
- **Giá trị 0, số âm và `Integer.MIN_VALUE` đều hợp lệ.** Vì thế không được dùng một số nguyên đặc biệt làm dấu “không có kết quả” nếu số ấy vẫn có thể xuất hiện trong đầu vào.

Nếu cần tìm **mọi giá trị xuất hiện hơn `n/3` lần**, bài toán khác: có thể có hai ứng viên, không thể trực tiếp dùng lập luận “tối đa một giá trị” của ngưỡng `n/2` mà không điều chỉnh.

## 2. Tính chất nền tảng: ứng viên toàn đoạn nằm trong ít nhất một nửa

Giả sử chia đoạn `A[l..r)` thành hai nửa liên tiếp `A[l..m)` và `A[m..r)`, với số phần tử lần lượt là `L=m-l` và `R=r-m`. Độ dài toàn đoạn `N=L+R`.

Ký hiệu `cL(x)`, `cR(x)` là số lần xuất hiện của giá trị `x` ở mỗi nửa. Giả sử `x` chiếm đa số **toàn đoạn**:

```text
cL(x) + cR(x) > (L + R) / 2
```

Nếu `x` **không** chiếm đa số trong cả hai nửa, ta phải có đồng thời:

```text
cL(x) <= L / 2
cR(x) <= R / 2
Suy ra cL(x) + cR(x) <= (L + R) / 2.
```

Điều này mâu thuẫn với giả thiết `x` đa số toàn đoạn. Vậy **ít nhất một trong hai nửa có `x` là phần tử đa số**.

Đây là phần chứng minh cho phép **thu hẹp tập ứng viên**. Nếu mỗi nửa trả về giá trị đa số của chính nửa đó (hoặc `NONE`), thì phần tử đa số của toàn đoạn, **nếu tồn tại**, phải là một trong **tối đa hai ứng viên** được trả về.

**Chiều ngược lại không luôn đúng:** một giá trị đa số trong **một nửa** chưa chắc là đa số của **toàn đoạn**. Ví dụ nửa trái `[1,1]` có đa số 1, nửa phải `[2,2]` có đa số 2, nhưng cả dãy `[1,1,2,2]` không có đa số. Vì thế không được chọn bừa ứng viên bên trái hoặc bên phải mà bỏ bước kiểm tra.

## 3. Chia để trị: trả đa số của từng đoạn rồi kết hợp

Dùng đoạn nửa mở `[lo,hi)`: gồm các chỉ số từ `lo` đến `hi-1`. Khi `hi-lo=1`, phần tử duy nhất **chắc chắn** chiếm đa số đoạn độ dài 1.

**Bước chia:** đặt `mid = lo + floor((hi-lo)/2)`, giải đệ quy hai nửa không rỗng.

**Bước kết hợp:**

1. Nhận `leftCandidate` từ nửa trái và `rightCandidate` từ nửa phải.
2. Nếu cả hai ứng viên **giống nhau**, có thể trả ngay ứng viên ấy. Nếu chúng cùng là `NONE`, trả `NONE`; nếu cùng là một giá trị `v`, giá trị `v` chiếm đa số ở **cả hai nửa**, nên cũng chiếm đa số toàn đoạn.
3. Nếu khác nhau, đếm số lần xuất hiện **trên toàn đoạn** của từng ứng viên khác `NONE`.
4. Chỉ trả ứng viên có số lần xuất hiện **`> (hi-lo)/2`**; nếu không ứng viên nào đạt ngưỡng, trả `NONE`.

Giả mã hoàn chỉnh:

```text
ALGORITHM MAJORITY(A)
    IF LENGTH(A) = 0 THEN
        RETURN NONE
    END IF
    RETURN SOLVE(A, 0, LENGTH(A))
END ALGORITHM

ALGORITHM SOLVE(A, lo, hi)
    REQUIRE 0 <= lo < hi <= LENGTH(A)

    IF hi - lo = 1 THEN
        RETURN A[lo]
    END IF

    mid <- lo + FLOOR((hi - lo) / 2)
    left <- SOLVE(A, lo, mid)
    right <- SOLVE(A, mid, hi)

    IF left = right THEN
        RETURN left
    END IF

    threshold <- FLOOR((hi - lo) / 2)

    IF left != NONE AND COUNT(A, lo, hi, left) > threshold THEN
        RETURN left
    END IF

    IF right != NONE AND COUNT(A, lo, hi, right) > threshold THEN
        RETURN right
    END IF

    RETURN NONE
END ALGORITHM
```

Trong giả mã, `COUNT(A,lo,hi,v)` quét các vị trí `lo,lo+1,...,hi-1` và đếm chính xác số phần tử bằng `v`. `NONE` là trạng thái **không có ứng viên**, không phải một số nguyên. Với phép phân chia nói trên, chỉ hàm bọc `MAJORITY` cần xử lý mảng rỗng: mọi lần gọi `SOLVE` đều có đoạn **không rỗng**.

### Vì sao phải kiểm tra lại trên toàn đoạn?

Xét `A=[1,1,2,2,2]`:

```text
Đoạn trái [1,1]       -> đa số 1
Đoạn phải [2,2,2]    -> đa số 2
Toàn đoạn            -> count(1)=2, count(2)=3
Ngưỡng nghiêm ngặt   -> N/2 = 5/2 = 2.5
Kết quả              -> 2, vì 3 > 2.5
```

Nếu khi hai ứng viên khác nhau mà luôn ưu tiên ứng viên trái, thuật toán sẽ trả **1 sai**. Việc kiểm tra trên toàn đoạn là bắt buộc. Với `[1,1,2,2]`, hai ứng viên có tần suất cùng bằng 2 và không ai vượt `4/2`, nên kết quả là `NONE`.

Nếu ứng viên một nửa là `NONE`, nửa kia có thể chứa ứng viên toàn đoạn nhưng vẫn phải **đếm lại toàn đoạn**. Ví dụ `[3,4,3,3,3]` có nửa trái `[3,4]` không có đa số, nửa phải `[3,3,3]` đa số 3; trên toàn đoạn 3 xuất hiện 4/5 nên là đáp án.

## 4. Chứng minh tính đúng đắn bằng quy nạp

**Mệnh đề:** với mọi đoạn không rỗng `[lo,hi)`, `SOLVE` trả về đúng phần tử chiếm đa số của đoạn nếu có, hoặc `NONE` nếu không có.

**Cơ sở:** đoạn có một phần tử `x`. Số lần xuất hiện của `x` bằng 1, lớn hơn `1/2`; hàm trả `x` nên đúng.

**Giả thuyết quy nạp:** hai lời gọi trên nửa trái và nửa phải đều trả đúng kết quả đa số tương ứng, hoặc `NONE`.

**Bước quy nạp:** theo tính chất ở mục 2, nếu toàn đoạn có phần tử đa số `x`, `x` phải là ứng viên của ít nhất một nửa. Vì vậy tập `{left,right}` **không bỏ sót** đáp án thật.

- Nếu hai ứng viên bằng nhau và đều là `x`, thì `x` đa số ở mỗi nửa, suy ra `cL(x)>L/2` và `cR(x)>R/2`; cộng lại được `c(x)>N/2`, nên trả `x` là đúng.
- Nếu cả hai cùng là `NONE`, theo bổ đề không thể có phần tử đa số toàn đoạn; trả `NONE` là đúng.
- Nếu khác nhau, việc đếm chính xác trên toàn đoạn và so với ngưỡng `N/2` chỉ trả phần tử thực sự chiếm đa số. Nếu không ứng viên nào vượt ngưỡng, do không thể có đáp án nằm ngoài tập ứng viên, trả `NONE` là đúng.

Vì thế hàm đúng cho mọi đoạn không rỗng; hàm bọc xử lý mảng rỗng đúng theo đặc tả.

**Kết thúc:** mỗi lời gọi trên đoạn dài `n>1` chia thành hai đoạn không rỗng có độ dài nhỏ hơn `n`. Độ dài giảm dần đến 1, nên đệ quy luôn kết thúc.

**Bảo toàn dữ liệu:** thuật toán chỉ đọc mảng và đếm; nó không hoán đổi, xóa hoặc bổ sung phần tử. Trật tự mảng đầu vào giữ nguyên.

## 5. Phân tích thời gian và bộ nhớ

Gọi `T(n)` là thời gian xử lý một đoạn `n` phần tử. Hai lời gọi đệ quy giải hai nửa và, khi ứng viên khác nhau, mỗi ứng viên được đếm trên đoạn độ dài `n`. Tối đa hai lần quét là **O(n)**:

```text
T(n) = T(floor(n/2)) + T(ceil(n/2)) + O(n)
T(1) = O(1)
```

Tại một mức đệ quy, các đoạn không chồng nhau và tổng độ dài là `n`, nên tổng chi phí đếm của cả mức là O(n). Có **O(log n)** mức; suy ra **O(n log n) thời gian trong trường hợp xấu nhất**.

Khi mọi phần tử giống nhau, hai ứng viên ở mỗi nút đều bằng nhau; không cần quét đếm thêm ở bước kết hợp, và thời gian có thể giảm còn **Θ(n)** cho biến thể có nhánh trả sớm như trên. Tuy nhiên, không dùng trường hợp thuận lợi này để thay thế bảo đảm worst-case O(n log n).

**Bộ nhớ phụ:** mảng không được sao chép. Mỗi lời gọi giữ một số cố định biến (`lo,hi,mid,left,right` và vài biến đếm). Độ sâu đệ quy O(log n), nên **O(log n) không gian ngăn xếp**, ngoài dữ liệu đầu vào. Ứng viên được thể hiện bằng một giá trị hoặc `NONE`; không cần thêm mảng phụ O(n).

Độ phức tạp này tốt hơn cách **duyệt mọi giá trị rồi đếm trên toàn mảng** O(n²), nhưng chưa nhanh bằng các cách bỏ phiếu hoặc đếm hash trong các điều kiện thích hợp. Ưu điểm riêng của chia để trị là tính chất **ứng viên có thể được kết hợp từ kết quả của những đoạn con**, dễ chứng minh bằng quy nạp và có thể mở rộng ý tưởng sang các phép tổng hợp dữ liệu.

## 6. Kết hợp ứng viên bằng triệt tiêu: bản tóm tắt mạnh hơn

Có một cách nhìn khác: khi gặp hai giá trị **khác nhau**, ta có thể **triệt tiêu một cặp** mà không làm mất một phần tử đa số thực sự. Vì nếu `x` xuất hiện nhiều hơn tất cả giá trị khác cộng lại, việc loại một `x` và một phần tử khác vẫn giữ lợi thế của `x`; loại một cặp không chứa `x` càng không thể làm nó mất lợi thế.

Ta có thể tóm tắt một đoạn bằng cặp:

`Summary = (candidate, balance)`

- `candidate` là giá trị còn lại sau một chuỗi phép triệt tiêu cặp khác nhau.
- `balance` là **số phần tử còn dư chưa bị triệt tiêu**, **không phải** tổng số lần xuất hiện của `candidate` trong đoạn gốc.
- `balance=0` tương ứng với tóm tắt rỗng, không có ứng viên.

### Quy tắc kết hợp hai tóm tắt

Cho `L=(candidateL,balanceL)` và `R=(candidateR,balanceR)`:

1. Nếu một bên có `balance=0`, kết quả là bên còn lại.
2. Nếu hai ứng viên bằng nhau, kết quả giữ ứng viên ấy, có `balance=balanceL+balanceR`.
3. Nếu ứng viên khác nhau, triệt tiêu `min(balanceL,balanceR)` cặp; ứng viên bên có balance lớn hơn còn dư với balance bằng hiệu.
4. Nếu cả hai hết cùng lúc, kết quả `EMPTY`.

```text
ALGORITHM COMBINE(L, R)
    IF L.balance = 0 THEN RETURN R END IF
    IF R.balance = 0 THEN RETURN L END IF

    IF L.candidate = R.candidate THEN
        RETURN (L.candidate, L.balance + R.balance)
    END IF

    IF L.balance > R.balance THEN
        RETURN (L.candidate, L.balance - R.balance)
    ELSE IF R.balance > L.balance THEN
        RETURN (R.candidate, R.balance - L.balance)
    ELSE
        RETURN (NONE, 0)
    END IF
END ALGORITHM
```

Mỗi phần tử ban đầu tương ứng với một tóm tắt lá `(A[i],1)`. Có thể chia dãy thành hai nửa, kết hợp các tóm tắt con ở mỗi nút. Nếu **có đa số thực sự**, giá trị ấy không thể bị triệt tiêu hết bởi các cặp khác nhau, nên cuối cùng **phải là ứng viên**.

**Nhưng ứng viên chưa chắc là đa số.** Ví dụ `[1,2,3]` có thể để lại một ứng viên với `balance=1` sau triệt tiêu, song mọi giá trị chỉ xuất hiện 1/3. Vì vậy cần **quét toàn mảng một lần nữa**, đếm ứng viên cuối cùng và chỉ chấp nhận nếu `count(candidate)>n/2`.

Ở cách này, mỗi nút chỉ dùng **O(1)** thao tác để kết hợp hai tóm tắt, không quét lại cả đoạn. Cây chia cân đối có O(n) lá và nút, nên toàn bộ pha thu ứng viên mất **O(n) thời gian**; quét xác minh thêm O(n), tổng vẫn **O(n)**. Nếu viết đệ quy cân đối, stack có độ sâu O(log n), cộng trạng thái tóm tắt đang hoạt động; một cài đặt Java tạo đối tượng tóm tắt ở từng nút có thể phát sinh nhiều cấp phát tạm thời nên cần phân biệt phân tích không gian thuật toán với hành vi cấp phát thực tế của runtime.

### Liên hệ với Boyer–Moore majority vote

Thuật toán **Boyer–Moore majority vote** kết hợp lần lượt tóm tắt đang có với từng phần tử đơn lẻ `(x,1)`. Khi gặp giá trị bằng ứng viên thì tăng balance; khi gặp giá trị khác thì giảm balance; khi balance về 0 thì có thể bắt đầu với ứng viên mới.

Một lượt bỏ phiếu chỉ **tìm ứng viên**. Nếu đề bài **không bảo đảm** luôn có đa số, phải duyệt **lượt thứ hai để xác minh**. Nhờ xử lý tuần tự, Boyer–Moore có **O(n) thời gian và O(1) bộ nhớ phụ**. Đó là cải tiến hiệu quả hơn về bộ nhớ so với cây đệ quy, nhưng cùng dựa vào ý tưởng kết hợp/triệt tiêu ứng viên.

**Điểm khác biệt giữa hai kiểu kết hợp:**

| Đặc điểm | Hợp nhất đa số của hai nửa | Hợp nhất tóm tắt triệt tiêu |
| --- | --- | --- |
| Đầu ra của mỗi đoạn | Đa số **đã xác minh** hoặc `NONE`. | Ứng viên kèm balance, **chưa chắc** đa số. |
| Công việc tại nút kết hợp | Có thể quét O(k) phần tử của đoạn dài k. | O(1) thao tác với hai tóm tắt. |
| Có cần xác minh cuối? | Không, vì mỗi nút đã xác minh kết quả. | **Có**, trừ khi đặc tả bảo đảm tồn tại đa số. |
| Thời gian | O(n log n) worst-case. | O(n) kể cả bước xác minh. |
| Bộ nhớ bổ sung | O(log n) stack trong cách chia cân đối. | O(log n) stack chia để trị; bỏ phiếu tuần tự dùng O(1). |

Hai thuật toán đều có thể gọi là “kết hợp ứng viên”, nhưng **không được dùng kết quả của tóm tắt triệt tiêu như một đa số đã được xác minh**. Sự khác biệt ở ý nghĩa của kết quả trung gian là điều cần ghi rõ khi chứng minh.

## 7. Java 17+: hai cách tìm đa số có thể chạy

Chương trình sau cài đặt:

- `majorityDivideConquer`: chia đoạn, tìm đa số **đã xác minh** của mỗi nửa, kết hợp bằng đếm lại ở đoạn cha khi hai ứng viên khác nhau.
- `majorityVoting`: Boyer–Moore kết hợp ứng viên theo kiểu triệt tiêu tuyến tính, sau đó xác minh một lượt.
- `OptionalInt` biểu diễn kết quả có/không một cách an toàn ngay cả khi giá trị đa số là **0, âm hoặc `Integer.MIN_VALUE`**.

Tạo tệp **`MajorityCandidateDemo.java`**:

```java
import java.util.Objects;
import java.util.OptionalInt;

public class MajorityCandidateDemo {
    public static OptionalInt majorityDivideConquer(int[] a) {
        Objects.requireNonNull(a, "array");
        if (a.length == 0) {
            return OptionalInt.empty();
        }

        Integer result = solve(a, 0, a.length);
        return result == null
                ? OptionalInt.empty()
                : OptionalInt.of(result);
    }

    private static Integer solve(int[] a, int lo, int hi) {
        // Tiền điều kiện: lo < hi.
        if (hi - lo == 1) {
            return a[lo];
        }

        int mid = lo + (hi - lo) / 2;
        Integer left = solve(a, lo, mid);
        Integer right = solve(a, mid, hi);

        // Hai ứng viên đã xác minh giống nhau, kể cả cả hai null.
        if (Objects.equals(left, right)) {
            return left;
        }

        int threshold = (hi - lo) / 2;

        if (left != null &&
                countRange(a, lo, hi, left) > threshold) {
            return left;
        }

        if (right != null &&
                countRange(a, lo, hi, right) > threshold) {
            return right;
        }

        return null; // Đoạn này không có phần tử đa số.
    }

    private static int countRange(
            int[] a, int lo, int hi, int candidate) {
        int count = 0;
        for (int i = lo; i < hi; i++) {
            if (a[i] == candidate) {
                count++;
            }
        }
        return count;
    }

    public static OptionalInt majorityVoting(int[] a) {
        Objects.requireNonNull(a, "array");

        int candidate = 0;
        int balance = 0;

        for (int x : a) {
            if (balance == 0) {
                candidate = x;
                balance = 1;
            } else if (candidate == x) {
                balance++;
            } else {
                balance--;
            }
        }

        if (balance == 0) {
            return OptionalInt.empty();
        }

        // Phải xác minh vì đầu vào có thể không có đa số.
        int occurrences = countRange(a, 0, a.length, candidate);
        return occurrences > a.length / 2
                ? OptionalInt.of(candidate)
                : OptionalInt.empty();
    }

    private static String show(OptionalInt result) {
        return result.isPresent()
                ? Integer.toString(result.getAsInt())
                : "none";
    }

    public static void main(String[] args) {
        String[] names = {
            "mixed", "tie", "repeated", "uniform",
            "empty", "negative", "single", "minValue"
        };

        int[][] samples = {
            {1, 1, 2, 2, 2},
            {1, 1, 2, 2},
            {2, 2, 1, 2, 3, 2, 2},
            {7, 7, 7, 7},
            {},
            {-1, -1, 0, 0, -1},
            {0},
            {Integer.MIN_VALUE, 2, Integer.MIN_VALUE}
        };

        for (int i = 0; i < samples.length; i++) {
            OptionalInt dc = majorityDivideConquer(samples[i]);
            OptionalInt vote = majorityVoting(samples[i]);
            System.out.println(names[i] + ": dc=" + show(dc)
                    + ", vote=" + show(vote));
        }
    }
}
```

Dùng JDK 17 trở lên, trong thư mục chứa tệp:

```bash
javac MajorityCandidateDemo.java
java MajorityCandidateDemo
```

**Đầu ra chính xác:**

```text
mixed: dc=2, vote=2
tie: dc=none, vote=none
repeated: dc=2, vote=2
uniform: dc=7, vote=7
empty: dc=none, vote=none
negative: dc=-1, vote=-1
single: dc=0, vote=0
minValue: dc=-2147483648, vote=-2147483648
```

**Cách đọc mã và kết quả:**

1. `mixed` có các ứng viên con trái và phải khác nhau, nhưng đếm toàn đoạn cho thấy `2` xuất hiện 3/5, nên hai thuật toán đều trả 2.
2. `tie` có hai giá trị xuất hiện đúng nửa dãy; cả hai trả `none`, không chọn bừa ứng viên đầu.
3. `repeated` chứa nhiều bản sao của 2, minh họa việc phần tử đa số không cần nằm liên tiếp.
4. `uniform` có mọi phần tử bằng nhau. Trong chia để trị, các ứng viên hai nửa thường giống nhau và được trả trực tiếp, không cần đếm lại.
5. `empty` trả `none`; `single` trả 0 vì 1 lần xuất hiện trên 1 phần tử là đa số.
6. `negative` và `minValue` chứng minh không thể dùng số âm hay `Integer.MIN_VALUE` làm ký hiệu “không có đa số”. `OptionalInt.empty()` và `Integer` bằng `null` **chỉ trong hàm nội bộ** giúp phân biệt chính xác.
7. Cả hai thuật toán đều **không sửa mảng** đầu vào. `Objects.equals(left,right)` so sánh giá trị hai đối tượng `Integer` hoặc trạng thái `null` đúng cách; không dùng `==` giữa hai đối tượng `Integer` vốn có thể bị ảnh hưởng bởi cơ chế boxing/cache.

### Vì sao hai cách cho cùng đáp án?

Bản chia để trị chỉ trả một giá trị khi giá trị ấy đã được xác minh là đa số của đoạn hiện tại. Bản bỏ phiếu có thể giữ một ứng viên không đa số sau lượt đầu, nhưng **lượt xác minh cuối** bảo đảm chỉ giá trị có `occurrences > n/2` được trả. Cả hai vì thế có cùng đặc tả đầu ra, mặc dù chiến lược và chi phí khác nhau.

**Lưu ý về kiểu dữ liệu:** mã dùng mảng `int[]`, so sánh bằng `==` là phù hợp. Nếu bài toán là mảng đối tượng, cần xác định rõ **quan hệ bằng nhau** (`equals`, comparator hoặc định danh) và dùng cùng một quy tắc ở mọi bước đếm/kết hợp. Không đánh đồng bằng nhau theo nội dung với cùng tham chiếu đối tượng.

## 8. Những cách giải khác và khi nào nên chọn

| Cách giải | Ý tưởng | Thời gian | Bộ nhớ phụ | Ghi chú |
| --- | --- | --- | --- | --- |
| Duyệt từng giá trị rồi đếm toàn dãy | Thử mọi ứng viên từ đầu vào | O(n²) | O(1) | Dễ viết, lặp đếm nhiều. |
| Sắp xếp rồi xét giá trị giữa và xác minh | Nếu tồn tại đa số, giá trị giữa mảng đã sắp là ứng viên | O(n log n) với sort phù hợp | Tùy thuật toán sắp xếp | Có thể thay đổi thứ tự dữ liệu. |
| `HashMap` đếm tần suất | Tăng bộ đếm cho từng khóa, tìm ai vượt n/2 | O(n) kỳ vọng | O(u) | `u` là số giá trị phân biệt; phụ thuộc đặc tính băm. |
| **Chia để trị, xác minh khi hợp nhất** | Chọn tối đa hai ứng viên từ hai nửa, đếm ở đoạn cha | O(n log n) worst-case | O(log n) stack | Dễ chứng minh bằng bổ đề ứng viên. |
| **Chia để trị, hợp nhất số dư triệt tiêu** | Mỗi nút gộp ứng viên và balance trong O(1) | O(n), gồm xác minh cuối | O(log n) stack về cấu trúc thuật toán | Không được quên lượt đếm cuối. |
| **Boyer–Moore majority vote** | Gộp ứng viên với từng phần tử, rồi xác minh | O(n) | O(1) | Phù hợp khi muốn ít bộ nhớ và có thể duyệt hai lượt. |

Cách sắp xếp có một hệ quả đơn giản: nếu phần tử đa số tồn tại, nó nhất thiết chiếm vị trí **giữa** của dãy đã sắp (chỉ số `floor(n/2)`). Nhưng **phần tử ở giữa không chắc là đa số** nếu đầu vào không có đa số; vẫn phải đếm xác minh.

Với mảng nhỏ, mọi cách đều có thể đủ nhanh. Với dữ liệu lớn, cần hỏi **có được sửa input không**, **bộ nhớ phụ bị giới hạn tới đâu**, **có thể duyệt hai lượt hay không** và **đề bài có bảo đảm tồn tại đa số không**. Nếu không chắc tồn tại, một ứng viên chưa xác minh không đủ.

## 9. Biên, phản ví dụ và lỗi phổ biến

**Biên cần xử lý:** mảng rỗng, một phần tử, tất cả bằng nhau, hai giá trị chia đều số lần, nhiều giá trị với tần suất nhỏ, số âm/0/`Integer.MIN_VALUE`, chiều dài lẻ/chẵn, và một ứng viên chỉ xuất hiện phần lớn trong một nửa nhưng không chiếm đa số toàn đoạn.

Những lỗi đặc biệt hay gặp:

1. **Dùng `>= n/2` thay vì `> n/2`.** Với `[1,1,2,2]`, điều kiện sai này trả một phần tử “đa số” không tồn tại.
2. **Không xử lý dãy rỗng.** Không thể gọi đệ quy lá độ dài 1 nếu mảng dài 0; hàm bọc nên trả `NONE`.
3. **Khi hai ứng viên khác nhau, chọn một bên mà không đếm.** Đa số của nửa trái chưa chắc đa số toàn đoạn.
4. **Chỉ đếm ứng viên trong nửa đã sinh ra nó.** Khi quyết định đa số toàn đoạn, phải đếm **toàn đoạn** hoặc dùng một phép tổng hợp có chứng minh tương đương.
5. **Cho rằng nếu hai nửa khác ứng viên thì toàn đoạn không có đa số.** `[1,1,2,2,2]` phản bác: ứng viên hai nửa là 1 và 2, nhưng toàn đoạn có đa số 2.
6. **Nhầm candidate với verified majority.** Tóm tắt triệt tiêu/Boyer–Moore có thể còn ứng viên khi không có đa số; phải xác minh.
7. **Dùng một giá trị số nguyên làm `NONE`.** Nếu giá trị ấy có mặt trong dãy, kết quả sẽ nhập nhằng.
8. **Sai cận phân đoạn.** Với khoảng nửa mở `[lo,hi)`, nửa trái là `[lo,mid)`, nửa phải là `[mid,hi)`; không bỏ hoặc đếm trùng phần tử tại `mid`.
9. **Nhầm `Integer == Integer` với so sánh giá trị.** Dùng `Objects.equals` cho ứng viên đóng hộp; chỉ dùng `==` khi đã so sánh các giá trị nguyên thủy `int`.
10. **Báo O(n) cho phiên bản quét lại từng nút chia để trị.** Tổng chi phí theo các mức là O(n log n), trừ khi bước kết hợp được thiết kế O(1) như dạng số dư triệt tiêu.
11. **Cho rằng bỏ phiếu đảm bảo có đa số.** Nó đảm bảo ứng viên nếu đa số tồn tại; không tự đảm bảo một đáp án hợp lệ khi đa số không tồn tại.
12. **Không chứng minh bất biến hoặc tính kết thúc.** Đệ quy phải rút ngắn đoạn, phép hợp nhất phải giữ được tính đầy đủ của tập ứng viên.

## 10. Bài tập tự luyện có lời giải

**Bài 1.** Với `A=[1,1,2,2,2]`, mỗi nửa của phép chia đầu có ứng viên nào và toàn mảng trả gì? **Đáp án:** nửa trái `[1,1]` trả 1; nửa phải `[2,2,2]` trả 2. Đếm trên toàn mảng: `count(1)=2`, `count(2)=3`, nên trả 2.

**Bài 2.** Với `A=[1,1,2,2]`, vì sao trả `NONE`? **Đáp án:** mỗi giá trị có tần suất 2, bằng `n/2` chứ không lớn hơn. Kết hợp hai ứng viên không cho phần tử đa số.

**Bài 3.** Vì sao nếu `x` chiếm đa số toàn đoạn thì `x` phải đa số ở ít nhất một nửa? **Đáp án:** nếu ở cả hai nửa `count(x) ≤ length/2` thì cộng lại được `count(x) ≤ n/2`, trái với định nghĩa đa số.

**Bài 4.** Một giá trị xuất hiện 6 lần trong mảng 12 phần tử có phải chiếm đa số không? **Đáp án:** không, vì `6` chỉ bằng `12/2`. Nếu xuất hiện 7 lần mới đạt đa số.

**Bài 5.** Mảng `[0,0,0,1,2]` có đa số không? **Đáp án:** có, giá trị 0 xuất hiện 3/5. Không được dùng 0 làm dấu “không có ứng viên”.

**Bài 6.** Nếu sau khi triệt tiêu từng cặp khác nhau vẫn còn ứng viên `v`, có thể kết luận ngay `v` là đa số? **Đáp án:** không. Ví dụ `[1,2,3]` có thể còn một ứng viên nhưng mỗi giá trị chỉ xuất hiện 1/3; phải đếm lại.

**Bài 7.** Với phiên bản chia để trị quét mỗi đoạn trong bước hợp nhất, vì sao độ phức tạp worst-case là O(n log n)? **Đáp án:** mỗi tầng có tổng độ dài các đoạn O(n), có O(log n) tầng, nên tổng O(n log n).

**Bài 8.** Nếu đề bài bảo đảm phần tử đa số **luôn tồn tại**, có thể làm gì ở Boyer–Moore? **Đáp án:** sau một lượt triệt tiêu, ứng viên cuối chắc chắn là phần tử đa số nên có thể bỏ lượt xác minh. Khi không có bảo đảm ấy, phải đếm lại.

**Bài 9.** Khi hai nửa trả cùng ứng viên `x` đã xác minh, vì sao không cần đếm lại toàn đoạn? **Đáp án:** `x` nhiều hơn nửa kích thước của từng nửa; cộng bất đẳng thức suy ra `x` nhiều hơn nửa kích thước toàn đoạn.

**Bài 10.** Một thuật toán trả giá trị xuất hiện nhiều nhất dù chỉ chiếm 40% dữ liệu. Nó đã giải đúng bài “majority element” chưa? **Đáp án:** chưa. Nó tìm **mode**, không chứng minh `count(x)>n/2`; bài majority phải trả `NONE` trong trường hợp đó.

**Bài 11.** Nếu cần dùng phép kết hợp ứng viên trên dữ liệu chia thành nhiều khối, cách nào thích hợp khi muốn giảm số lần quét mỗi khối? **Đáp án:** có thể tổng hợp mỗi khối thành cặp `(candidate,balance)`, hợp nhất các tóm tắt theo phép triệt tiêu O(1), rồi thực hiện một lượt xác minh ứng viên trên dữ liệu đầy đủ. Không được coi balance là tần suất chính xác.

## 11. Checklist khi giải bài majority bằng ứng viên

1. **Xác định ngưỡng:** có cần **`> n/2`** hay một ngưỡng khác? Có được bảo đảm tồn tại đa số không?
2. **Xác định dạng kết quả:** trả giá trị hoặc `NONE`, tuyệt đối không đánh đồng `NONE` với một giá trị hợp lệ.
3. **Chia nửa đúng cận:** đoạn nửa mở và điểm giữa phải phủ kín dữ liệu, không trùng hoặc bỏ phần tử.
4. **Hiểu ý nghĩa kết quả con:** đa số đã xác minh của đoạn hay chỉ ứng viên từ triệt tiêu? Hai kiểu không thể thay thế nhau mà bỏ bước xác minh.
5. **Chứng minh tập ứng viên đầy đủ:** phần tử đa số toàn đoạn phải là đa số của ít nhất một nửa; hoặc không thể bị triệt tiêu hết nếu dùng số dư.
6. **Kiểm tra nghiêm ngặt:** chỉ trả giá trị khi có hơn `n/2` lần xuất hiện; đếm đúng miền cần xác minh.
7. **Phân tích chi phí thật:** hợp nhất bằng đếm lại mỗi nút là O(n log n); tóm tắt O(1) mỗi nút rồi xác minh là O(n).
8. **Thử biên:** rỗng, chỉ một phần tử, tất cả trùng, chia đều, không có đa số, nhiều số âm và `Integer.MIN_VALUE`.
9. **Kiểm tra sự thay đổi dữ liệu:** với phiên bản chỉ đếm/đệ quy, mảng gốc không được sửa nếu đặc tả yêu cầu bảo toàn.
10. **So sánh phương pháp:** chia để trị làm sáng tỏ phép kết hợp kết quả con; Boyer–Moore hữu ích khi cần O(1) bộ nhớ và có thể duyệt hai lượt.

**Ghi nhớ:** kết hợp ứng viên chỉ đúng khi hiểu rõ **ứng viên được xác minh ở từng đoạn hay còn là số dư chưa xác minh**. Tính chất “đa số của toàn đoạn phải là đa số của ít nhất một nửa” tạo nền tảng chia để trị; phép triệt tiêu cặp khác nhau mở đường cho thuật toán tuyến tính. Trong cả hai trường hợp, dấu **`>`** trong điều kiện `count(x)>n/2` quyết định đáp án có thực sự là phần tử chiếm đa số hay không.
