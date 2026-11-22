# Chứng minh kết thúc bằng đại lượng giảm

**Chứng minh kết thúc** (*termination proof*) trả lời câu hỏi: với mọi đầu vào thỏa tiền điều kiện, thuật toán có dừng sau hữu hạn bước hay không? Một kỹ thuật nền tảng là tìm **đại lượng giảm** (*decreasing measure*, còn gọi là *ranking function* hoặc *loop variant*): một số hoặc bộ giá trị biểu diễn phần việc còn lại, luôn nằm trong một tập có thứ tự không thể giảm mãi và **giảm nghiêm ngặt mỗi khi thuật toán tiếp tục**.

Trong nhóm kiến thức **tính đúng và chi phí**, cần phân biệt ba việc: chứng minh thuật toán **dừng**, chứng minh **khi dừng thì kết quả đúng**, và phân tích **tốn bao nhiêu thời gian/bộ nhớ**. Chúng liên quan nhau nhưng không thay thế nhau. Một vòng lặp dừng ngay vẫn có thể trả kết quả sai; một vòng lặp trả lời đúng nếu có dừng vẫn có thể chạy mãi.

## 1. Trực giác: không thể đếm ngược mãi trong tập số tự nhiên

Xét đoạn mã minh họa Java:

```java
int remaining = 5;
while (remaining > 0) {
    remaining--;
}
```

Giá trị `remaining` qua các lần kiểm tra điều kiện là `5, 4, 3, 2, 1, 0`. Ta biết vòng lặp dừng vì ba lý do:

1. Khi vòng lặp còn chạy, `remaining` là số nguyên dương.
2. Mỗi lượt, `remaining` giảm đúng một đơn vị.
3. Giá trị này không thể giảm vô hạn mà vẫn là số nguyên không âm.

Điểm mấu chốt **không phải** nhìn thấy một biến mang tên `remaining` hay có toán tử `--`. Cần chứng minh đại lượng giảm **theo đúng mọi nhánh chạy**, có **cận dưới** và thuộc miền **không có chuỗi giảm nghiêm ngặt vô hạn**.

Ví dụ, `while (x != 0) { x -= 2; }` với `int x = 5` không kết thúc: các giá trị luôn lẻ (kể cả sau khi số nguyên Java tràn vòng), nên không bao giờ bằng 0. Dù “trừ 2” có vẻ đang giảm, ta thiếu một đại lượng nguyên không âm luôn giảm trên các trạng thái tiếp tục.

## 2. Phát biểu chính xác: hàm xếp hạng

Gọi `s` là trạng thái ở đầu một vòng lặp, `G(s)` là điều kiện tiếp tục, và `s'` là trạng thái sau khi thân vòng lặp chạy xong. Ta cần chọn một hàm `V(s)` làm **đại lượng giảm**. Trường hợp dễ dùng nhất là `V(s)` nhận giá trị trong tập số nguyên không âm `N = {0, 1, 2, ...}`.

Để chứng minh, cần bảo đảm các điều kiện sau cho mọi trạng thái có thể đạt được theo tiền điều kiện:

- **Tính xác định và cận dưới:** `V(s) >= 0` ở các điểm kiểm tra tương ứng. Nếu dùng biểu thức có phép toán số học trong chương trình, phải xét cả tính tràn số và điều kiện định nghĩa của biểu thức.
- **Giảm nghiêm ngặt:** Khi `G(s)` đúng và thân vòng hoàn thành mà không kết thúc hàm ngay, thì `V(s') < V(s)`. Với số nguyên, điều này đồng nghĩa giảm ít nhất 1, không phải chỉ không tăng.
- **Mỗi bước hữu hạn:** Một lượt thân vòng thực hiện hữu hạn thao tác. Nếu thân chứa vòng lặp, đệ quy hoặc lời gọi con có nguy cơ không kết thúc, cần chứng minh phần đó riêng.
- **Tiền điều kiện đủ mạnh:** Các lập luận trên phải đúng cho tất cả đầu vào hợp lệ. Ví dụ, không được giả định `n >= 0` nếu hàm chấp nhận cả n âm mà không xử lý.

**Chứng minh phản chứng:** Giả sử tồn tại một đường chạy vô hạn. Vì mỗi vòng giảm nghiêm ngặt, ta thu được `V(s₀) > V(s₁) > V(s₂) > ... >= 0`. Không có chuỗi số nguyên không âm giảm nghiêm ngặt vô hạn. Vậy giả sử chạy vô hạn là sai, nên vòng lặp kết thúc.

Vòng lặp có thể **trả về sớm** khi tìm được kết quả. Nhánh `return` đã kết thúc hàm; chỉ những nhánh **tiếp tục chạy vòng sau** mới cần chứng minh giảm đại lượng. Nhánh `throw` cũng chấm dứt đường chạy đang xét, nhưng có đáp ứng đặc tả hàm hay không lại là câu hỏi tính đúng riêng biệt.

### Cách viết một chứng minh hoàn chỉnh

Một bài giải rõ ràng nên ghi:

1. **Tiền điều kiện**: ví dụ `n >= 0`, mảng đã sắp xếp, số chia khác 0.
2. **Chọn đại lượng**: `V = ...`; mô tả nó đại diện cho phần việc còn lại.
3. **Chứng minh không âm**: vì sao `V >= 0` trước và sau các lượt hợp lệ.
4. **Chứng minh giảm nghiêm ngặt**: xét mọi nhánh điều khiển mà sau đó vòng lặp có thể tiếp tục.
5. **Kết luận**: tập giá trị của V không có dãy giảm vô hạn, nên vòng lặp phải dừng.
6. **Sau đó mới chứng minh kết quả và chi phí**: dùng bất biến/hậu điều kiện để kiểm tra tính đúng; đếm số vòng và chi phí mỗi vòng để đánh giá hiệu năng.

**Lưu ý:** Nếu V là số nguyên không âm, giảm ít nhất 1 ở mỗi vòng, thì số vòng có thể bị chặn bởi V ban đầu (khi các điều kiện trên giữ ở mỗi lần kiểm tra). Đó là **cận số vòng**, chưa chắc là cận thời gian O(V ban đầu) nếu thân mỗi vòng có chi phí thay đổi. Đặc biệt, một cận đúng có thể lỏng hơn độ phức tạp thực tế.

## 3. Ví dụ cơ bản: tổng từ 1 đến n

Bài toán: với `n >= 0`, tính `1 + 2 + ... + n`.

```java
static long sumToN(int n) {
    if (n < 0) {
        throw new IllegalArgumentException("n must be nonnegative");
    }

    long sum = 0;
    int remaining = n;
    while (remaining > 0) {
        sum += remaining;
        remaining--;
    }
    return sum;
}
```

Đây là **đoạn phương thức minh họa**, chưa phải tệp độc lập; chương trình hoàn chỉnh có trong phần 7.

**Chứng minh kết thúc:**

- Tiền điều kiện sau khi kiểm tra `n`: `n >= 0`.
- Chọn `V = remaining`. Ban đầu `V = n >= 0`.
- Mỗi vòng chỉ chạy nếu `remaining > 0`. Sau đó `remaining` giảm một và vẫn không âm.
- Vì `V_mới = V_cũ - 1 < V_cũ`, vòng lặp dừng sau n lượt; nếu `n = 0`, vòng lặp không chạy.

**Chứng minh tính đúng:** Trước mỗi vòng, `sum` là tổng các giá trị đã duyệt từ n xuống `remaining + 1`. Sau câu lệnh cộng rồi giảm `remaining`, tính chất này còn đúng. Khi `remaining = 0`, toàn bộ các số 1..n đã được cộng, nên hàm trả `n(n + 1)/2`.

**Chi phí:** Mỗi vòng O(1), số vòng n, tổng thời gian O(n), bộ nhớ phụ O(1). Giá trị kết quả tối đa với n thuộc kiểu `int` không âm vẫn nằm trong phạm vi `long`.

## 4. Ví dụ quan trọng: tìm kiếm nhị phân dùng đại lượng biểu thức

Tìm kiếm nhị phân duy trì một khoảng vị trí `[left, right]` trên mảng **đã sắp xếp tăng dần**:

```java
static int binarySearch(int[] sorted, int target) {
    int left = 0;
    int right = sorted.length - 1;

    while (left <= right) {
        int mid = left + (right - left) / 2;
        if (sorted[mid] == target) {
            return mid;
        }
        if (sorted[mid] < target) {
            left = mid + 1;
        } else {
            right = mid - 1;
        }
    }
    return -1;
}
```

Chọn **đại lượng `V = right - left + 1`** — số phần tử còn có thể chứa `target`. Ta không cần có một biến đếm `remaining` trong chương trình.

- **Khởi đầu:** `left = 0`, `right = sorted.length - 1`; do đó `V = sorted.length >= 0`, kể cả mảng rỗng.
- **Trước lượt lặp:** Điều kiện `left <= right` cho biết `V >= 1`.
- **Tìm thấy:** `return mid` làm hàm kết thúc ngay.
- **Giá trị giữa nhỏ hơn target:** `left` trở thành `mid + 1`. Vì `mid >= left_cũ`, cận trái tăng ít nhất 1; V giảm nghiêm ngặt.
- **Giá trị giữa lớn hơn target:** `right` trở thành `mid - 1`. Vì `mid <= right_cũ`, cận phải giảm ít nhất 1; V giảm nghiêm ngặt.
- **Khi không còn ứng viên:** `left = right + 1`, V bằng 0, điều kiện sai và hàm trả -1.

Mọi nhánh còn tiếp tục đều giảm V. V không âm, vậy vòng lặp kết thúc.

**Bất biến tính đúng:** Nếu `target` còn tồn tại mà chưa được tìm thấy thì phải còn một vị trí chứa nó trong khoảng `[left, right]`. Do mảng đã sắp xếp, loại bỏ nửa khoảng theo so sánh với `sorted[mid]` là an toàn. Khi khoảng rỗng, trả -1 là đúng. **Chứng minh kết thúc không tự chứng minh điều này:** nếu mảng không sắp xếp, khoảng vẫn thu hẹp và thuật toán vẫn dừng, nhưng có thể trả lời sai.

**Cận thời gian:** Việc giảm ít nhất 1 chỉ đủ chứng minh kết thúc và cho một cận số vòng lỏng. Mỗi lượt thực tế loại bỏ khoảng một nửa ứng viên, nên số lượt là O(log n) với n > 0; bộ nhớ phụ của phiên bản lặp là O(1). Công thức tính `mid` tránh tràn ở phép cộng `left + right`.

## 5. Ví dụ đại lượng giảm không đều: thuật toán Euclid

Thuật toán Euclid tính ƯCLN của hai số nguyên không âm, không đồng thời bằng 0:

```java
static int gcd(int a, int b) {
    if (a < 0 || b < 0 || (a == 0 && b == 0)) {
        throw new IllegalArgumentException(
                "a, b must be nonnegative and not both zero");
    }
    while (b != 0) {
        int remainder = a % b;
        a = b;
        b = remainder;
    }
    return a;
}
```

Chọn **V = b**. Khi vào thân vòng, `b > 0`. Với `a >= 0` và `b > 0`, phép chia lấy dư thỏa `0 <= a % b < b`. Sau cập nhật, `b_mới = a_cũ % b_cũ`; do đó `0 <= V_mới < V_cũ`. Thuật toán dừng vì b không thể giảm nghiêm ngặt mãi trong số nguyên không âm.

Với `gcd(48, 18)`, dãy giá trị đại lượng là `18 → 12 → 6 → 0`. Điều kiện vòng lặp không còn đúng ở giá trị 0.

**Chứng minh kết quả đúng:** Tính chất toán học `gcd(a, b) = gcd(b, a mod b)` khi b > 0 bảo đảm ƯCLN không đổi qua mỗi lượt. Khi b = 0, kết quả là a. Với `gcd(0, 7)`, một lượt cho cặp (7, 0), nên trả 7. Cặp (0, 0) bị loại khỏi đặc tả.

**Chi phí:** Đại lượng b giảm cho thấy kết thúc, nhưng số bước thực tế được chặn chặt hơn bởi O(log max(a, b)) trong mô hình phép số học có chi phí hằng số đối với các số nguyên độ dài từ cố định.

## 6. Đệ quy: mỗi lời gọi con phải tiến gần trường hợp cơ sở

Với đệ quy, đại lượng giảm có thể là kích thước tham số bài toán con. Xét tính `n!` khi `n >= 0`:

```java
static java.math.BigInteger factorial(int n) {
    if (n < 0) {
        throw new IllegalArgumentException("n must be nonnegative");
    }
    if (n == 0) {
        return java.math.BigInteger.ONE;
    }
    return java.math.BigInteger.valueOf(n).multiply(factorial(n - 1));
}
```

Chọn **V(n) = n**. Với `n = 0`, hàm kết thúc ngay. Với `n > 0`, chỉ có lời gọi `factorial(n - 1)` và `0 <= n - 1 < n`. Do mỗi lời gọi con giảm đại lượng trong số nguyên không âm, chuỗi gọi đệ quy hữu hạn.

Với một hàm có nhiều lời gọi đệ quy, phải chứng minh **từng lời gọi con** giảm đại lượng tương ứng. Một cây gọi có thể chứa rất nhiều nhánh, nhưng nếu mỗi nút sinh hữu hạn lời gọi con và độ sâu bị chặn bởi đại lượng giảm thì toàn bộ cây vẫn hữu hạn.

**Phân biệt chứng minh toán học và giới hạn JVM:** Hàm đệ quy về mặt thuật toán có chiều sâu hữu hạn; với n đủ lớn, Java có thể ném `StackOverflowError` trước khi trả kết quả bình thường do giới hạn stack. `BigInteger` giúp tránh tràn số của kết quả giai thừa nhưng không loại bỏ giới hạn stack, RAM và thời gian. Khi cần xử lý n rất lớn, phiên bản lặp có thể phù hợp hơn.

## 7. Chương trình Java 17+ hoàn chỉnh

Lưu tệp **`TerminationWithVariant.java`**. Ví dụ bao gồm đếm ngược, thuật toán Euclid, tìm kiếm nhị phân và đệ quy. Có thể biên dịch/chạy trên JDK 17 trở lên.

```java
import java.math.BigInteger;

public class TerminationWithVariant {
    static long sumToN(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("n must be nonnegative");
        }
        long sum = 0;
        int remaining = n;
        while (remaining > 0) {
            sum += remaining;
            remaining--;
        }
        return sum;
    }

    static int gcd(int a, int b) {
        if (a < 0 || b < 0 || (a == 0 && b == 0)) {
            throw new IllegalArgumentException(
                    "a, b must be nonnegative and not both zero");
        }
        while (b != 0) {
            int remainder = a % b;
            a = b;
            b = remainder;
        }
        return a;
    }

    static int binarySearch(int[] sorted, int target) {
        int left = 0;
        int right = sorted.length - 1;
        while (left <= right) {
            int mid = left + (right - left) / 2;
            if (sorted[mid] == target) {
                return mid;
            }
            if (sorted[mid] < target) {
                left = mid + 1;
            } else {
                right = mid - 1;
            }
        }
        return -1;
    }

    static BigInteger factorial(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("n must be nonnegative");
        }
        if (n == 0) {
            return BigInteger.ONE;
        }
        return BigInteger.valueOf(n).multiply(factorial(n - 1));
    }

    public static void main(String[] args) {
        int[] sorted = {2, 4, 6, 8, 10};

        System.out.println("sumToN(5) = " + sumToN(5));
        System.out.println("sumToN(0) = " + sumToN(0));
        System.out.println("gcd(48, 18) = " + gcd(48, 18));
        System.out.println("gcd(0, 7) = " + gcd(0, 7));
        System.out.println("binarySearch(8) = " + binarySearch(sorted, 8));
        System.out.println("binarySearch(7) = " + binarySearch(sorted, 7));
        System.out.println("binarySearch(empty, 1) = "
                + binarySearch(new int[0], 1));
        System.out.println("factorial(5) = " + factorial(5));
    }
}
```

Lệnh chạy:

```bash
javac TerminationWithVariant.java
java TerminationWithVariant
```

Stdout:

```text
sumToN(5) = 15
sumToN(0) = 0
gcd(48, 18) = 6
gcd(0, 7) = 7
binarySearch(8) = 3
binarySearch(7) = -1
binarySearch(empty, 1) = -1
factorial(5) = 120
```

Giải thích: Tổng từ 1 đến 5 bằng 15; ƯCLN của 48 và 18 bằng 6; mảng tăng dần có giá trị 8 ở chỉ số 3 (đếm từ 0), còn 7 không có; mảng rỗng cũng không có phần tử cần tìm; 5! bằng 120.

## 8. Vòng lặp lồng nhau và đại lượng nhiều thành phần

Một biến không nhất thiết giảm trong **mọi thao tác** nếu xét toàn bộ chương trình phức tạp. Khi đó có thể chứng minh từng vòng lặp riêng hoặc dùng đại lượng dạng bộ.

Ví dụ:

```java
for (int i = 0; i < n; i++) {
    for (int j = i + 1; j < n; j++) {
        // Xử lý hữu hạn bước với cặp (i, j)
    }
}
```

Giả sử `n >= 0`. Với **i cố định**, đại lượng của vòng trong là `n - j`, không âm và giảm 1 sau mỗi lần j tăng. Vòng trong kết thúc. Với vòng ngoài, đại lượng là `n - i`; sau mỗi lượt vòng ngoài hoàn tất, i tăng 1, nên đại lượng giảm. Vậy vòng ngoài có hữu hạn lượt và mỗi lượt có hữu hạn bước, nên chương trình kết thúc.

Việc j được khởi tạo lại ở vòng ngoài tiếp theo không mâu thuẫn: chứng minh hai mức độc lập đã đủ. Nếu cần mô hình thứ tự toàn cục, dùng **thứ tự từ điển** trên bộ số nguyên không âm như `(n - i, n - j)` ở các điểm điều khiển thích hợp: thành phần đầu giảm khi i tăng; nếu thành phần đầu không đổi, thành phần thứ hai giảm khi j tăng. Thứ tự từ điển trên `N × N` cũng không có dãy giảm nghiêm ngặt vô hạn.

Các trường hợp khác có thể cần **đại lượng nhiều pha**, chẳng hạn cặp `(số pha còn lại, số bước còn lại của pha hiện tại)`. Một thành phần có thể tăng lại khi chuyển pha nhưng thành phần đứng trước giảm. Phải chứng minh thứ tự trên toàn bộ bộ thực sự có cơ sở tốt (*well-founded*) và mọi bước có thể tiếp tục đều làm bộ giảm theo thứ tự đó.

**Chi phí khác kết thúc:** Với vòng lặp cặp chỉ số ở trên, tổng số lượt thân trong là `n(n - 1)/2`, tức O(n²) nếu mỗi thao tác xử lý cặp là O(1). Chứng minh “mỗi vòng trong dừng và vòng ngoài dừng” chỉ kết luận hữu hạn; để ra O(n²), cần đếm số lần thực hiện.

## 9. Phản ví dụ và lỗi lập luận thường gặp

| Phát biểu/đoạn mã | Vì sao chưa đủ hoặc sai? | Cách khắc phục |
| --- | --- | --- |
| “Biến thay đổi ở mỗi vòng” | Có thể dao động giữa hai giá trị hoặc thay đổi mà không tiến đến điều kiện dừng | Tìm đại lượng có thứ tự giảm nghiêm ngặt |
| “Giá trị không tăng” | `V_mới = V_cũ` có thể xảy ra mãi | Chứng minh `V_mới < V_cũ` mỗi khi vòng lặp có thể tiếp tục |
| `while (x > 0) { if (x % 2 == 0) x--; }` | Với x lẻ dương, không có bước tiến | Bổ sung xử lý mọi nhánh hoặc thay đổi thuật toán |
| `while (x != 0) { x -= 2; }`, x khởi đầu bằng 5 | Giá trị luôn lẻ và không thể bằng 0, kể cả khi tràn vòng trong `int` Java | Với mục tiêu đếm xuống từ x không âm: `while (x > 0) x = Math.max(0, x - 2);` |
| “V giảm và có cận dưới nên chắc dừng” với V là số thực | Dãy toán học `1, 1/2, 1/4, ...` dương và giảm mãi nhưng không chạm 0 | Dùng tập giá trị well-founded hoặc chứng minh có bước giảm tối thiểu dương phù hợp |
| “Đã chứng minh nhánh A làm V giảm” | Nhánh B có thể tăng hoặc giữ V không đổi | Kiểm tra **mọi** nhánh còn tiếp tục |
| “Kích thước đầu vào hữu hạn” | Một chương trình vẫn có thể lặp vô hạn trên một đầu vào hữu hạn | Chứng minh tiến triển và điều kiện dừng |
| “Có hàm giảm nghĩa là kết quả đúng” | Chỉ biết thuật toán dừng, chưa biết trả về giá trị theo đặc tả | Cần thêm bất biến vòng lặp và hậu điều kiện |

**Chú ý số thực và số dấu phẩy động:** Về mặt toán học, dãy liên tục chia đôi một số thực dương không bao giờ bằng 0, nên “dương và giảm” không đủ. Với `double` Java, phép chia đôi có thể làm tròn/underflow về 0, nhưng còn xuất hiện giá trị đặc biệt như NaN, vô cực hoặc các phép toán không tạo tiến triển như mong muốn. Không thể áp dụng nguyên xi chứng minh với số thực lý tưởng cho số dấu phẩy động; phải kiểm tra ngữ nghĩa thực tế.

**Tràn số nguyên:** Khi biểu thức đại lượng tính bằng `int`, phép toán có thể tràn và phá vỡ chứng minh không âm hoặc giảm. Ví dụ `x -= 2` với x lẻ âm mãi sẽ tràn; việc biểu diễn lại một giá trị không làm nó trở thành hàm xếp hạng hợp lệ. Nếu định nghĩa bằng số tự nhiên trong chứng minh, cần giải thích vì sao toán học và phép tính Java tương ứng trên mọi trạng thái hợp lệ.

## 10. Tính đúng toàn phần, tính kết thúc và phân tích chi phí

Bảng sau giúp tách ba loại lập luận:

| Câu hỏi | Công cụ chính | Kết luận |
| --- | --- | --- |
| Nếu hàm dừng, kết quả có đúng không? | Tiền điều kiện, bất biến, hậu điều kiện, chứng minh toán học | Tính đúng một phần |
| Có chắc dừng với mọi đầu vào hợp lệ không? | Đại lượng giảm, cận dưới, thứ tự well-founded, trường hợp cơ sở | Kết thúc |
| Tổng công việc tốn bao nhiêu? | Đếm lượt lặp/lời gọi, chi phí mỗi lượt, bộ nhớ và tiền xử lý | Độ phức tạp thời gian, không gian |

**Tính đúng toàn phần** yêu cầu cả tính đúng một phần và kết thúc trên cùng miền đầu vào hợp lệ. Một đại lượng giảm là phương tiện chứng minh kết thúc hữu ích nhưng không thay thế phần chứng minh bất biến hoặc phân tích chi phí.

Trong triển khai, còn cần cân nhắc giới hạn RAM/stack, thời gian chạy thực tế, thao tác I/O hoặc chờ tài nguyên ngoài. Chứng minh lý thuyết về một vòng lặp không tự bảo đảm toàn bộ hệ thống bên ngoài sẽ đáp ứng trong thời gian hữu hạn nếu có lời gọi chờ vô hạn.

## 11. Bài tập có đáp án

**Bài 1.** Với tìm kiếm nhị phân, vì sao dùng `V = left` không phù hợp, còn `V = right - left + 1` phù hợp?

**Đáp án:** `left` có thể tăng hoặc đứng yên, không phải đại lượng giảm. Độ dài đoạn còn lại luôn không âm và giảm trong mọi nhánh chưa trả kết quả.

**Bài 2.** Vòng lặp có đại lượng nguyên không âm V, giảm ít nhất 1 mỗi lượt, và V ban đầu bằng n. Có thể suy ra thời gian O(n) ngay không?

**Đáp án:** Chỉ suy ra số lượt không quá n theo các giả định đã nêu. Nếu thân mỗi lượt tốn O(n), tổng có thể O(n²). Muốn chứng minh cận thời gian phải phân tích chi phí mỗi lượt.

**Bài 3.** Xét `int x = 7; while (x > 0) { if (x % 2 == 0) x--; }`. V = x có chứng minh kết thúc được không?

**Đáp án:** Không. x lẻ ngay từ đầu nên thân không thay đổi x, điều kiện vẫn đúng và V không giảm.

**Bài 4.** Chọn đại lượng cho hàm đệ quy tính giai thừa và chỉ ra tiền điều kiện.

**Đáp án:** V(n) = n; tiền điều kiện n là số nguyên không âm. Khi n = 0, trả về; khi n > 0, lời gọi con có đối số n − 1, vẫn không âm và giảm nghiêm ngặt. Cần phân biệt kết thúc toán học với nguy cơ hết stack nếu n rất lớn trên JVM.

**Bài 5.** Với Euclid bắt đầu `a=48, b=18`, hãy liệt kê giá trị V và giải thích phần nào chứng minh đúng kết quả.

**Đáp án:** V=b lần lượt là 18, 12, 6, 0. Bất đẳng thức `0 <= a % b < b` chứng minh kết thúc. Đẳng thức `gcd(a,b)=gcd(b,a mod b)` chứng minh ƯCLN được bảo toàn, giúp kết luận kết quả cuối đúng.

**Bài 6.** Trong vòng lặp lồng nhau, vòng trong được khởi tạo lại mỗi khi vòng ngoài tăng. Điều này có phá chứng minh kết thúc không?

**Đáp án:** Không, nếu chứng minh mỗi vòng trong dừng với i cố định và vòng ngoài có hữu hạn lượt. Có thể dùng thứ tự từ điển để tổng quát: thành phần thứ nhất giảm khi chuyển vòng ngoài; thành phần thứ hai giảm trong vòng trong.

## Ghi nhớ

Chứng minh kết thúc bằng đại lượng giảm gồm ba điều cốt lõi: **đại lượng có cận dưới trên một thứ tự không thể giảm vô hạn**, **giảm nghiêm ngặt ở mọi bước có thể tiếp tục**, và **các điều kiện đầu vào/thân bước làm lập luận hợp lệ**. Đại lượng có thể là một biến, một biểu thức như độ dài khoảng tìm kiếm, hoặc một bộ nhiều thành phần. Sau đó vẫn phải chứng minh tính đúng của kết quả và đánh giá chi phí nếu bài toán yêu cầu.
