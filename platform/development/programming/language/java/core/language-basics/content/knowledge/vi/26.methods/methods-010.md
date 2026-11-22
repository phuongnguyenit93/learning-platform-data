# Đệ quy, trường hợp dừng và nguy cơ `StackOverflowError` — Java 17+

## 1. Đệ quy là gì?

**Đệ quy (recursion)** là kỹ thuật một phương thức gọi lại **chính nó** (trực tiếp), hoặc gọi một phương thức khác dẫn tới lời gọi ban đầu (gián tiếp), nhằm giải một bài toán qua các bài toán con nhỏ hơn.

Ví dụ: tính giai thừa số nguyên không âm `n`:

~~~java
static long factorial(int n) {
    if (n == 0) {
        return 1L;                  // Trường hợp dừng (base case).
    }
    return n * factorial(n - 1);    // Bước đệ quy (recursive case).
}
~~~

Với `n = 4`, ta có `4! = 4 × 3 × 2 × 1 = 24`. Trình tự phép gọi có thể hình dung:

~~~text
factorial(4)
  4 * factorial(3)
        3 * factorial(2)
              2 * factorial(1)
                    1 * factorial(0)
                          return 1
                    return 1
              return 2
        return 6
  return 24
~~~

Phương thức trên **chỉ là minh họa** cho đầu vào `n >= 0`. Nếu gọi với số âm, `n - 1` sẽ không tiến tới `0` theo mục đích. Chương trình hoàn chỉnh bên dưới thêm kiểm tra miền đầu vào và giới hạn an toàn của kiểu `long`.

Đệ quy không phải là một kiểu vòng lặp đặc biệt: mỗi lời gọi thực sự là **một lần gọi phương thức** với tham số và trạng thái thực thi riêng.

## 2. Hai điều kiện quan trọng để đệ quy kết thúc

Một thuật toán đệ quy đúng thường cần cả hai yếu tố:

1. **Trường hợp dừng (base case):** điều kiện mà phương thức trả kết quả hoặc kết thúc mà **không gọi đệ quy thêm**. Ví dụ `n == 0` khi tính giai thừa.
2. **Bước tiến (progress toward base case):** mỗi lần gọi đệ quy phải làm bài toán **gần trường hợp dừng hơn**. Ví dụ `n - 1` khi `n > 0`.

~~~java
static int sumToZero(int n) {
    if (n < 0) {
        throw new IllegalArgumentException("n must be non-negative");
    }
    if (n == 0) {
        return 0;
    }
    return n + sumToZero(n - 1);
}
~~~

~~~text
sumToZero(3)
= 3 + sumToZero(2)
= 3 + 2 + sumToZero(1)
= 3 + 2 + 1 + sumToZero(0)
= 3 + 2 + 1 + 0
= 6
~~~

Có trường hợp dừng nhưng **không tiến tới nó** cũng là lỗi:

~~~java
// KHÔNG CHẠY: minh họa lỗi.
// static int wrong(int n) {
//     if (n == 0) return 0;
//     return n + wrong(n); // n không thay đổi.
// }
~~~

Tương tự, lời gọi `wrong(-1)` trong phiên bản chỉ giảm `n - 1` nhưng dừng ở `n == 0` cũng không tiến đúng miền đầu vào. Hãy xác định **miền hợp lệ**, **trường hợp dừng** và **đại lượng giảm dần** trước khi viết phương thức.

## 3. Stack frame và hai pha gọi — quay về

JVM quản lý quá trình gọi phương thức bằng **ngăn xếp lời gọi** (*call stack*). Mỗi lần gọi đệ quy có một **stack frame** chứa thông tin thực thi như biến cục bộ, tham số và vị trí tiếp tục sau lời gọi.

Khi gọi `factorial(3)`:

~~~text
Đang đi sâu xuống (call):
factorial(3) -> factorial(2) -> factorial(1) -> factorial(0)

Ở độ sâu lớn nhất:
+--------------------+
| factorial(0)       | <- lời gọi hiện tại; gặp base case
+--------------------+
| factorial(1)       |
+--------------------+
| factorial(2)       |
+--------------------+
| factorial(3)       |
+--------------------+

Đang quay về (return):
factorial(0) -> factorial(1) -> factorial(2) -> factorial(3)
~~~

`factorial(3)` phải đợi kết quả của `factorial(2)`, phương thức đó lại đợi `factorial(1)`, v.v. Sau trường hợp dừng, kết quả được trả về **ngược thứ tự gọi**, và các frame hoàn thành lần lượt được loại khỏi stack.

Mỗi lời gọi có bản riêng của tham số `n`. Việc thay đổi `n` ở một lần gọi không tự thay biến `n` của frame khác.

## 4. Truy vết thứ tự thực thi

Để quan sát các lời gọi, in thông tin **trước** và **sau** bước đệ quy:

~~~java
static void trace(int n) {
    System.out.println("enter " + n);
    if (n == 0) {
        System.out.println("base " + n);
        return;
    }
    trace(n - 1);
    System.out.println("leave " + n);
}
~~~

Khi `trace(3)` chạy với đầu vào không âm:

~~~text
enter 3
enter 2
enter 1
enter 0
base 0
leave 1
leave 2
leave 3
~~~

- Các dòng `enter` xuất hiện khi **đi xuống** chuỗi gọi.
- `base 0` là điểm dừng, không gọi thêm.
- Các dòng `leave` xuất hiện khi các lời gọi **quay về**.
- Nhánh `n == 0` dùng `return;` để kết thúc phương thức `void`, nên không in `leave 0`.

Khi đọc một phương thức đệ quy, cần theo dõi đồng thời **điều kiện dừng**, **tham số của lời gọi tiếp theo** và **công việc xảy ra sau khi lời gọi trả về**.

## 5. `StackOverflowError` là gì?

Mỗi lời gọi đệ quy bổ sung thêm một stack frame, tiêu thụ tài nguyên của ngăn xếp luồng. Nếu chương trình tiếp tục gọi sâu tới mức không thể tạo thêm frame, JVM có thể ném **`java.lang.StackOverflowError`**.

Các nguyên nhân điển hình:

- **Không có trường hợp dừng**, ví dụ phương thức tự gọi chính mình không điều kiện.
- Có base case nhưng **tham số không tiến gần nó**, ví dụ `f(n)` gọi `f(n)`.
- Điều kiện dừng không bao phủ **miền đầu vào**: đếm xuống `0` nhưng bắt đầu từ số âm.
- Thuật toán **đúng** nhưng cần quá nhiều lời gọi lồng nhau, ví dụ xử lý một cấu trúc dữ liệu quá sâu hoặc đệ quy tuyến tính với đầu vào rất lớn.
- Các phương thức **đệ quy gián tiếp** gọi qua lại mà không có điều kiện kết thúc.

~~~java
// KHÔNG CHẠY đoạn mã này:
// static void endless() {
//     endless(); // Không có base case.
// }
~~~

**Đừng chạy đoạn ví dụ lỗi chỉ để xem stack tràn.** `StackOverflowError` là một `Error`, không phải `Exception`. Bắt nó bằng `catch (StackOverflowError e)` không phải cách bình thường để kiểm soát luồng nghiệp vụ: stack có thể đang ở trạng thái thiếu tài nguyên, và việc xử lý có thể không an toàn.

Không có một **số lần gọi tối đa cố định** áp dụng cho mọi JVM. Độ sâu chịu ảnh hưởng bởi giới hạn stack của luồng, JVM, hệ điều hành, biên dịch JIT và kích thước frame; không nên dựa vào một ngưỡng đo thử trên máy cụ thể.

## 6. Đệ quy đúng vẫn có nguy cơ tràn stack

Xét:

~~~java
static long sumRecursively(int n) {
    if (n == 0) return 0;
    return n + sumRecursively(n - 1);
}
~~~

Về logic với `n >= 0`, `n` giảm đều và cuối cùng đạt `0`. Tuy nhiên với `n` rất lớn, phương thức cần xấp xỉ `n + 1` lời gọi lồng nhau, có thể tràn stack **trước khi tới base case**.

Phiên bản lặp:

~~~java
static long sumIteratively(int n) {
    if (n < 0) throw new IllegalArgumentException("negative n");
    long total = 0;
    for (long i = 1; i <= n; i++) {
        total += i;
    }
    return total;
}
~~~

Dùng biến đếm `long` để `i++` không tràn khi `n == Integer.MAX_VALUE`; với bộ đếm `int`, điều kiện `i <= n` có thể tiếp tục đúng sau khi `i` tràn sang số âm. Vòng lặp cũng tránh **tăng độ sâu call stack theo `n`**. Với `n` thuộc miền `int` không âm, tổng từ 1 đến `n` luôn nằm trong miền `long`; nếu mở rộng đầu vào hoặc thay phép tính, cần kiểm tra tràn số riêng. Công thức `n(n+1)/2` cũng cần tránh tràn ở các phép nhân trung gian.

## 7. Độ phức tạp: thời gian và bộ nhớ stack

| Bài toán / cách làm | Thời gian gần đúng | Stack bổ sung | Nhận xét |
|---|---|---|---|
| Giai thừa đệ quy `factorial(n)` | `O(n)` | `O(n)` | Mỗi lần giảm `n` một đơn vị |
| Giai thừa với vòng `for` | `O(n)` | `O(1)` | Dễ tránh stack sâu |
| Tìm kiếm nhị phân đệ quy trong mảng đã sắp xếp | `O(log n)` | `O(log n)` | Mỗi lần loại khoảng một nửa |
| Tìm kiếm nhị phân với `while` | `O(log n)` | `O(1)` | Cũng cần dữ liệu đã sắp xếp |
| Fibonacci đệ quy ngây thơ `fib(n-1)+fib(n-2)` | `O(2^n)` (chặn trên) | `O(n)` | Tính lặp lại nhiều bài toán con |

**Lưu ý:** “Đệ quy” không tự động đồng nghĩa với chậm. Chi phí phụ thuộc số bài toán con và độ sâu. Với bài toán chia để trị, đệ quy thường diễn đạt cấu trúc bài toán dễ đọc. Với một chuỗi tuyến tính dài, vòng lặp có thể thực tế hơn.

Fibonacci đệ quy ngây thơ có base case ở `0` và `1` nhưng vẫn có thể chạy chậm vì lặp lại các phép tính. Dùng **memoization** hoặc vòng lặp để tránh tính trùng, chứ chỉ sửa điều kiện dừng là chưa đủ.

## 8. Đệ quy trên khoảng chỉ số: tìm kiếm nhị phân

Không phải lúc nào base case cũng là `n == 0`. Với tìm kiếm nhị phân trên một mảng **đã sắp xếp tăng dần**, bài toán con là một **khoảng chỉ số** `low..high`.

~~~java
static int search(int[] a, int target, int low, int high) {
    if (low > high) return -1;                 // Khoảng rỗng.
    int mid = low + (high - low) / 2;
    if (a[mid] == target) return mid;          // Tìm thấy.
    if (target < a[mid]) {
        return search(a, target, low, mid - 1);
    }
    return search(a, target, mid + 1, high);
}
~~~

Ở mỗi bước, khoảng mới **nhỏ hơn** khoảng cũ; độ sâu tăng theo `O(log n)`. Base case `low > high` diễn tả “không còn vị trí để kiểm tra”; trường hợp `a[mid] == target` diễn tả “đã tìm thấy”.

Ví dụ `a = {1,3,5,7,9}`:

~~~text
search target=7 trong [0..4], mid=2 -> a[2]=5
search tiếp [3..4], mid=3 -> a[3]=7
return 3
~~~

**Tiền điều kiện:** mảng phải được sắp xếp đúng thứ tự mà thuật toán dùng để so sánh. Nếu đầu vào chưa sắp xếp, kết quả không còn được bảo đảm.

## 9. Khi nào nên dùng đệ quy, khi nào dùng vòng lặp?

Chọn **đệ quy** khi mô tả bài toán tự nhiên bằng các bài toán con, ví dụ:

- Duyệt cây thư mục, cây biểu thức, cấu trúc lồng nhau.
- Tìm kiếm nhị phân, chia để trị trên khoảng dữ liệu.
- Thuật toán quay lui (*backtracking*) có trạng thái, điểm dừng và hoàn tác rõ ràng.

Cân nhắc **vòng lặp** khi:

- Các bước lặp đơn giản và tuyến tính.
- Đầu vào có thể gây độ sâu hàng trăm nghìn/hàng triệu lời gọi.
- Cần kiểm soát tài nguyên stack hoặc hiệu năng thực tế.
- Có thể tính kết quả bằng bộ nhớ `O(1)` mà không làm code khó hiểu hơn.

Java **không bảo đảm tối ưu hóa đệ quy đuôi** (*tail-call optimization*). Một lời gọi đệ quy đặt ở cuối phương thức **không có nghĩa** stack frame chắc chắn được tái sử dụng trên JVM. Với bài toán cần xử lý độ sâu rất lớn, dùng vòng lặp hoặc một cấu trúc stack tường minh khi thích hợp.

Tham số `-Xss` có thể điều chỉnh kích thước stack trên một số cấu hình JVM, nhưng **không sửa lỗi logic thiếu base case** và không phải giải pháp đầu tiên cho thuật toán có độ sâu tăng không kiểm soát.

## 10. Chương trình Java 17+ chạy độc lập

Tạo file đúng tên **`RecursionBaseCaseDemo.java`**:

~~~java
import java.util.Arrays;

public final class RecursionBaseCaseDemo {
    private RecursionBaseCaseDemo() {}

    // Validate tại ranh giới gọi; 20! còn nằm trong long.
    static long factorial(int n) {
        if (n < 0 || n > 20) {
            throw new IllegalArgumentException("factorial n must be 0..20");
        }
        return factorialRecursive(n);
    }

    private static long factorialRecursive(int n) {
        if (n == 0) return 1L;             // Base case: 0! = 1.
        return n * factorialRecursive(n - 1);
    }

    static long factorialIterative(int n) {
        if (n < 0 || n > 20) {
            throw new IllegalArgumentException("factorial n must be 0..20");
        }
        long value = 1L;
        for (int i = 2; i <= n; i++) {
            value *= i;
        }
        return value;
    }

    static void trace(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("trace n must be >= 0");
        }
        System.out.println("enter " + n);
        if (n == 0) {
            System.out.println("base " + n);
            return;
        }
        trace(n - 1);
        System.out.println("leave " + n);
    }

    static int digitSum(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("digits n must be >= 0");
        }
        if (n < 10) return n;
        return (n % 10) + digitSum(n / 10);
    }

    // Chỉ dùng với mảng int[] sắp xếp tăng dần.
    static int binarySearch(int[] sorted, int target) {
        if (sorted == null) {
            throw new IllegalArgumentException("array must not be null");
        }
        return search(sorted, target, 0, sorted.length - 1);
    }

    private static int search(int[] a, int target, int low, int high) {
        if (low > high) return -1;
        int mid = low + (high - low) / 2;
        if (a[mid] == target) return mid;
        if (target < a[mid]) {
            return search(a, target, low, mid - 1);
        }
        return search(a, target, mid + 1, high);
    }

    public static void main(String[] args) {
        System.out.println("factorial 0=" + factorial(0));
        System.out.println("factorial 5=" + factorial(5));
        System.out.println("factorial 10=" + factorial(10));
        System.out.println("factorial 20=" + factorial(20));
        System.out.println("factorial loop 5=" + factorialIterative(5));
        System.out.println("digit sum 405=" + digitSum(405));
        System.out.println("digit sum 0=" + digitSum(0));

        trace(3);

        int[] sorted = {1, 3, 5, 7, 9};
        System.out.println("sorted=" + Arrays.toString(sorted));
        System.out.println("search 7=" + binarySearch(sorted, 7));
        System.out.println("search 2=" + binarySearch(sorted, 2));
        System.out.println("search empty="
                + binarySearch(new int[0], 7));

        try {
            factorial(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid factorial=" + ex.getMessage());
        }
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên, chỉ dùng Java chuẩn; không cần thư viện ngoài hay preview features. Mã ví dụ **không cố ý gây `StackOverflowError`**.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 RecursionBaseCaseDemo.java
java -cp . RecursionBaseCaseDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\RecursionBaseCaseDemo.java
java -cp . RecursionBaseCaseDemo
~~~

### Exact expected stdout

~~~text
factorial 0=1
factorial 5=120
factorial 10=3628800
factorial 20=2432902008176640000
factorial loop 5=120
digit sum 405=9
digit sum 0=0
enter 3
enter 2
enter 1
enter 0
base 0
leave 1
leave 2
leave 3
sorted=[1, 3, 5, 7, 9]
search 7=3
search 2=-1
search empty=-1
invalid factorial=factorial n must be 0..20
~~~

**Đối chiếu:** `factorial(0)` kết thúc ngay; `factorial(5)` đi sâu rồi nhân kết quả khi quay về. `digitSum(405)` tính `5 + 0 + 4 = 9` qua `n % 10` và `n / 10`. `trace(3)` cho thấy thứ tự vào/ra frame. Tìm kiếm nhị phân có hai kiểu dừng: tìm thấy mục tiêu hoặc hết khoảng tìm kiếm. Đầu vào âm của `factorial` bị từ chối trước khi bắt đầu chuỗi đệ quy.

## 11. Những lỗi thường gặp và cách khắc phục

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Không viết trường hợp dừng | Lời gọi có thể tăng không giới hạn | Viết `if (base) return ...;` |
| Có base case nhưng không thay tham số | Không tiến tới base case | Chứng minh mỗi lời gọi làm bài toán nhỏ đi |
| Chỉ xét `n == 0`, bỏ qua `n < 0` | Đầu vào âm có thể không dừng đúng | Kiểm tra miền đầu vào |
| Dùng `return n * factorial(n)` | Tự gọi lại với cùng bài toán | Thường cần `factorial(n - 1)` |
| Gọi `factorial(21)` bằng `long` không kiểm soát | **Tràn số học**, không nhất thiết tràn stack | Giới hạn 0..20 hoặc dùng `BigInteger` |
| Đệ quy tuyến tính với đầu vào cực lớn | Stack frame tăng tuyến tính | Chuyển vòng lặp/stack tường minh |
| Tin Java luôn tối ưu tail recursion | JVM không bảo đảm | Thiết kế độc lập tối ưu hóa này |
| Bắt `StackOverflowError` để sửa lỗi đệ quy | Có thể thiếu tài nguyên, che bug | Sửa logic và giới hạn độ sâu |
| Tìm kiếm nhị phân khi mảng chưa sắp xếp | Kết quả tìm kiếm có thể sai | Đảm bảo tiền điều kiện sorted |
| Chỉ quan tâm thời gian `O(n)` | Bỏ qua stack space `O(n)` | Xem cả bộ nhớ stack |

**Phân biệt hai nguy cơ:** `StackOverflowError` liên quan đến ngăn xếp lời gọi; **tràn số nguyên** xảy ra khi kết quả vượt phạm vi kiểu số, thường không tự ném `StackOverflowError`. Đệ quy giai thừa của `long` phải kiểm soát cả độ sâu lẫn miền giá trị kết quả.

## 12. Bài tập và đáp án

**A — Base case ở đâu?**

~~~java
static int countDown(int n) {
    if (n == 0) return 0;
    return 1 + countDown(n - 1);
}
~~~

**Đáp án:** base case `n == 0`. Với `n = 3`, kết quả là `3`, nhưng chưa an toàn với `n < 0`. Thêm guard cho số âm.

**B — Vì sao đoạn sau có thể không dừng?**

~~~java
// Không chạy:
static void loopForever(int n) {
    if (n == 0) return;
    loopForever(n);
}
~~~

**Đáp án:** tham số `n` không đổi; với `n != 0`, không thể tiến tới base case.

**C — `trace(2)` in gì?**

~~~text
enter 2
enter 1
enter 0
base 0
leave 1
leave 2
~~~

**D — Khi nào stack tăng theo `O(n)`?**  
**Đáp án:** khi các lời gọi lồng nhau giảm `n` từng đơn vị đến base case, ví dụ `factorial(n)`, cần khoảng `n + 1` frame ở độ sâu lớn nhất.

**E — `binarySearch(new int[]{1,3,5,7,9}, 7)` cho gì?**  
**Đáp án:** `3` (chỉ số tính từ 0); với mục tiêu 2 trả `-1`.

**F — Có thể thay giai thừa đệ quy bằng vòng lặp để tránh stack sâu không?**  
**Đáp án:** có; vòng lặp dùng stack bổ sung `O(1)` cho cách cài đặt thông thường. Nhưng vẫn phải chú ý giai thừa lớn tràn giới hạn `long`.

## 13. Checklist và kết luận

- [ ] Hiểu đệ quy là lời gọi phương thức lặp lại trên bài toán con.
- [ ] Xác định được **base case** không gọi đệ quy.
- [ ] Chứng minh các lời gọi tiến tới base case trên miền đầu vào hợp lệ.
- [ ] Hiểu trình tự “gọi sâu xuống” và “trả kết quả ngược lên” trên call stack.
- [ ] Nhận diện `StackOverflowError` do thiếu dừng hoặc do độ sâu quá lớn.
- [ ] Không cố ý chạy đệ quy vô hạn hoặc dựa vào `catch StackOverflowError`.
- [ ] Phân biệt lỗi tràn stack và lỗi tràn số học.
- [ ] Biết so sánh chi phí thời gian, bộ nhớ của đệ quy và vòng lặp.
- [ ] Không mặc định Java có tối ưu hóa tail call.
- [ ] Đọc được base case theo khoảng `low > high` ở tìm kiếm nhị phân.
- [ ] Chạy `RecursionBaseCaseDemo.java` trên JDK 17+ và đối chiếu exact stdout.

**Kết luận:** Một thuật toán đệ quy an toàn cần **trường hợp dừng đúng**, **bước tiến làm nhỏ bài toán** và **độ sâu thực thi phù hợp với stack**. Base case đúng về logic chưa bảo đảm an toàn khi đầu vào quá lớn. Hãy kiểm tra miền đầu vào, dự tính cả stack space, và chọn vòng lặp khi độ sâu có nguy cơ vượt khả năng của JVM.