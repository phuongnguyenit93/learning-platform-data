# Đệ quy và giới hạn tối ưu lời gọi đuôi trong Java

## 1. Đệ quy là gì, vì sao cần quan tâm đến ngăn xếp?

**Đệ quy (recursion)** là cách giải một bài toán bằng cách để một phương thức gọi lại chính nó (đệ quy trực tiếp) hoặc gọi qua phương thức khác rồi quay về nó (đệ quy gián tiếp). Cách nghĩ thường là: **giải trường hợp nhỏ nhất**, sau đó **quy bài toán lớn hơn về bài toán cùng dạng nhưng nhỏ hơn**.

Một hàm đệ quy đúng cần ít nhất ba thành phần:

1. **Điểm dừng (base case):** trả về kết quả trực tiếp, không tiếp tục gọi đệ quy.
2. **Bước tiến triển (recursive step):** giảm kích thước hoặc đưa trạng thái đến gần điểm dừng.
3. **Bất biến và hợp đồng đầu vào:** xác định những trạng thái hợp lệ, tránh việc đệ quy mãi với dữ liệu không thể đạt base case.

Trong Java, lời gọi phương thức thông thường tạo một **stack frame** cho lần gọi đó, chứa thông tin thực thi và trạng thái cần thiết để phương thức tiếp tục hoặc trả về. Khi các lời gọi lồng nhau chưa kết thúc, nhiều frame còn nằm trên **call stack** của luồng đang chạy. Kích thước stack là hữu hạn; nếu số frame cần thiết vượt giới hạn, chương trình có thể gặp **StackOverflowError**.

Đệ quy giúp mô tả tự nhiên các cấu trúc như cây thư mục, biểu thức cú pháp, cây nhị phân và bài toán chia để trị. Tuy nhiên, cú pháp đệ quy ngắn gọn không tự bảo đảm sử dụng ít bộ nhớ stack.

## 2. Trường hợp thường và trường hợp đệ quy đuôi

Xét phép tính giai thừa: **0! = 1**, với n dương thì **n! = n × (n - 1)!**.

Cách đệ quy trực tiếp:

~~~java
static long factorial(int n) {
    if (n == 0) {
        return 1L;
    }
    return n * factorial(n - 1);
}
~~~

Đây là **đoạn phương thức minh họa**, cần đặt trong một lớp Java và chỉ dùng với đầu vào hợp lệ. Lời gọi **factorial(n - 1)** chưa phải hành động cuối cùng: khi nó trả về, phương thức hiện tại vẫn phải nhân thêm **n**. Vì vậy, đây **không phải đệ quy đuôi**.

Với **factorial(4)**, cách suy luận kết quả:

~~~text
factorial(4)
  = 4 * factorial(3)
  = 4 * (3 * factorial(2))
  = 4 * (3 * (2 * factorial(1)))
  = 4 * (3 * (2 * (1 * factorial(0))))
  = 4 * 3 * 2 * 1 * 1
  = 24
~~~

Các frame bên ngoài phải chờ giá trị từ lời gọi bên trong để thực hiện phép nhân. Độ sâu lời gọi tăng theo **n**.

**Đệ quy đuôi (tail recursion)** là dạng đệ quy mà lời gọi tiếp theo xuất hiện ở **vị trí đuôi (tail position)**: kết quả của lời gọi được trả trực tiếp, không còn phép tính hoặc công việc nào phải thực hiện sau khi lời gọi đó trả về.

Ta có thể truyền kết quả tích lũy qua tham số:

~~~java
static long factorialTail(int n, long acc) {
    if (n == 0) {
        return acc;
    }
    return factorialTail(n - 1, acc * n);
}
~~~

Ở nhánh đệ quy, phương thức trả về **ngay kết quả factorialTail(...)**. Phép nhân **acc * n** được tính **trước khi gọi** phương thức kế tiếp. Về mặt hình thức, đây là đệ quy đuôi.

Các trạng thái khi tính **factorialTail(4, 1)**:

~~~text
factorialTail(4, 1)
→ factorialTail(3, 4)
→ factorialTail(2, 12)
→ factorialTail(1, 24)
→ factorialTail(0, 24)
→ 24
~~~

**Điểm khác biệt quan trọng:** đệ quy đuôi giúp hàm có thể được biến đổi thành vòng lặp trong một số mô hình thực thi. Nó **không đồng nghĩa** Java tự giảm số stack frame khi chạy.

## 3. Nhận biết vị trí đuôi chính xác

Một biểu thức gọi đệ quy được xem là ở vị trí đuôi khi kết quả của lời gọi là kết quả cuối cùng của nhánh hiện tại. Việc phương thức có từ khóa **return** chưa đủ để kết luận đó là tail call.

| Biểu thức trong nhánh đệ quy | Có ở vị trí đuôi? | Giải thích |
| --- | --- | --- |
| **return f(n - 1);** | Có | Trả trực tiếp kết quả của lời gọi |
| **return n * f(n - 1);** | Không | Sau lời gọi còn phép nhân |
| **return f(n - 1) + 1;** | Không | Sau lời gọi còn phép cộng |
| **return Math.max(n, f(n - 1));** | Không | Còn tính **Math.max** sau khi lời gọi trả về |
| **return f(n - 1, acc + n);** | Có | Tính tham số trước, rồi trả trực tiếp kết quả của lời gọi |
| **if (n == 0) return acc; return f(n - 1, acc + n);** | Có ở nhánh đệ quy | Nhánh cơ sở kết thúc trực tiếp; nhánh còn lại là tail call |

Những ví dụ ở bảng là **biểu thức minh họa**, giả định có các phương thức và kiểu dữ liệu tương ứng. Trong một phương thức có **finally**, xử lý tài nguyên hay hành vi phải diễn ra sau lời gọi, việc phân tích tail position phải xét đầy đủ luồng điều khiển. Không nên chỉ tìm chuỗi **return** bằng mắt rồi khẳng định có thể tối ưu.

Có hai khái niệm cần phân biệt:

- **Tail call:** lời gọi một phương thức bất kỳ nằm ở vị trí đuôi, ví dụ **return otherMethod(x);**.
- **Tail recursion:** tail call quay lại chính phương thức đang xét (hoặc diễn ra qua một chu kỳ gọi lẫn nhau).

Tối ưu hóa lời gọi đuôi, thường gọi **tail-call optimization (TCO)**, là kỹ thuật triển khai cho phép không giữ lại frame gọi hiện tại khi không cần quay lại frame đó. **Tail-call elimination** là một tên thường dùng cho trường hợp loại bỏ lời gọi/frame theo dạng này. Đó là đặc tính của cách thực thi hoặc trình biên dịch, **không phải thuộc tính tự động của cú pháp Java**.

## 4. Java có tự tối ưu đệ quy đuôi không?

**Không được dựa vào TCO như một bảo đảm của Java.** Ngôn ngữ Java và JVM tiêu chuẩn không cam kết rằng một phương thức đệ quy đuôi sẽ chạy với stack cố định. Trên các JVM thông dụng như HotSpot, mã đệ quy đuôi vẫn có thể tạo nhiều frame và gây **StackOverflowError** nếu độ sâu quá lớn.

JIT có thể thực hiện nhiều tối ưu hóa như inlining khi phù hợp. Tuy nhiên, **inlining không phải lời hứa về TCO** và không giúp chương trình được quyền giả định rằng mọi lời gọi đệ quy đuôi đều dùng **O(1)** stack. Hành vi cụ thể có thể phụ thuộc JVM, phiên bản, cấu hình và đường thực thi.

Hãy phân biệt:

1. **Về mặt thuật toán:** dùng accumulator đưa phép tính về dạng đệ quy đuôi, khiến phép chuyển sang vòng lặp trở nên đơn giản.
2. **Về mặt đặc tả/runtime Java:** mỗi lời gọi đệ quy có thể tiếp tục chiếm stack; không có cam kết loại frame.
3. **Về mặt thiết kế hệ thống:** khi độ sâu không được chặn chắc chắn, hãy viết vòng lặp, dùng cấu trúc stack tường minh hoặc kỹ thuật trì hoãn lời gọi thích hợp để tránh phụ thuộc vào TCO.

Tham số **-Xss** trên một số JVM cho phép cấu hình stack của luồng, nhưng chỉ thay đổi ngưỡng có thể chịu được; nó **không biến thuật toán đệ quy sâu không giới hạn thành an toàn**. Không có số lần gọi đệ quy tối đa chung cho mọi máy. Ngưỡng còn phụ thuộc kích thước frame, JVM, stack của từng luồng và môi trường chạy.

Không nên cố bắt **StackOverflowError** như một nhánh nghiệp vụ bình thường. Đây là **Error** biểu thị tài nguyên stack đã cạn, có thể khiến việc phục hồi trở nên không đáng tin cậy.

## 5. Ví dụ Java 17 hoàn chỉnh: đệ quy thường, đệ quy đuôi và vòng lặp

Tạo tệp **RecursionBasics.java**:

~~~java
public class RecursionBasics {

    // Đệ quy thường: còn phép nhân sau lời gọi.
    static long factorial(int n) {
        requireValidN(n);
        if (n == 0) {
            return 1L;
        }
        return n * factorial(n - 1);
    }

    // Đệ quy đuôi: kết quả lời gọi được trả trực tiếp.
    static long factorialTail(int n, long acc) {
        requireValidN(n);
        if (n == 0) {
            return acc;
        }
        return factorialTail(n - 1, acc * n);
    }

    // Chuyển cùng phép tính sang vòng lặp.
    static long factorialLoop(int n) {
        requireValidN(n);
        long acc = 1L;
        for (int i = n; i >= 1; i--) {
            acc *= i;
        }
        return acc;
    }

    static void requireValidN(int n) {
        if (n < 0 || n > 20) {
            throw new IllegalArgumentException("n must be 0..20");
        }
    }

    public static void main(String[] args) {
        System.out.println("recursive: " + factorial(5));
        System.out.println("tail: " + factorialTail(5, 1L));
        System.out.println("loop: " + factorialLoop(5));
        System.out.println("zero: " + factorialTail(0, 1L));
    }
}
~~~

Chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac RecursionBasics.java
java RecursionBasics
~~~

Stdout chính xác:

~~~text
recursive: 120
tail: 120
loop: 120
zero: 1
~~~

Cả ba phương thức cùng giải bài toán trong miền đầu vào **0 ≤ n ≤ 20**. Giá trị **20!** còn biểu diễn được bằng **long**, trong khi **21!** vượt giới hạn số nguyên có dấu 64-bit. Kiểm tra đầu vào là cần thiết để tránh kết quả tràn số gây hiểu sai. Trường hợp cần giai thừa lớn hơn, hãy cân nhắc **BigInteger** với thuật toán tương ứng; BigInteger giải quyết giới hạn miền giá trị, không tự giải quyết giới hạn độ sâu stack.

Lưu ý về hiệu năng và stack, xét riêng chi phí điều khiển đối với n trong miền lý thuyết hợp lệ:

| Cách viết | Thời gian cho n bước | Stack lời gọi trong Java | Ý nghĩa |
| --- | --- | --- | --- |
| **factorial(n)** | O(n) | O(n) | Đệ quy thường, chờ nhân khi trả về |
| **factorialTail(n, acc)** | O(n) | Có thể O(n); không được bảo đảm O(1) | Đệ quy đuôi, biểu đạt rõ accumulator |
| **factorialLoop(n)** | O(n) | O(1) bổ sung | Vòng lặp thay thế lời gọi lồng nhau |

Bảng mô tả độ phức tạp thuật toán khi mỗi phép nhân primitive tốn chi phí hằng số; ví dụ giai thừa trong mã được giới hạn **0..20** vì dùng **long**. Nếu chuyển sang số lớn tùy ý, chi phí phép nhân và bộ nhớ lưu số tăng theo kích thước kết quả.

**Cách chuyển đổi cơ học:** đưa kết quả tích lũy vào **acc**, thay lời gọi **factorialTail(n - 1, acc * n)** bằng việc cập nhật **acc *= n; n--;** trong vòng lặp. Điều kiện dừng **n == 0** tương ứng với thoát vòng lặp. Chuyển đổi chỉ đúng nếu thứ tự các phép tính và quy tắc xử lý lỗi được bảo toàn.

## 6. Vì sao accumulator không loại được stack frame trong Java?

Với phép tính bình thường **n * factorial(n - 1)**, frame hiện tại còn phải ghi nhớ **n** để nhân sau khi lời gọi con hoàn tất. Với **factorialTail(n - 1, acc * n)**, phép nhân đã hoàn tất trước lời gọi con và trạng thái cần thiết được truyền sang **acc**.

Nếu runtime hỗ trợ loại bỏ tail call, frame cũ *có thể* được tái sử dụng mà không cần chờ lời gọi con. Nhưng trong Java thông dụng, việc lập trình viên chuyển phép toán vào accumulator chỉ đảm bảo **cấu trúc logic** phù hợp với phép biến đổi đó; nó không ép JVM áp dụng tối ưu hóa.

Để chứng minh giới hạn stack được khắc phục, hãy dùng mã mà **luồng điều khiển của chính chương trình** không giữ các lời gọi Java lồng nhau, chẳng hạn vòng lặp. Đừng dùng việc “chạy thử n lớn mà chưa lỗi” làm bằng chứng thuật toán đệ quy an toàn với mọi độ sâu.

Có thể mô tả quá trình bằng hai mô hình:

~~~text
Đệ quy đuôi chạy như các lời gọi Java thông thường:
frame(n=4, acc=1)
  frame(n=3, acc=4)
    frame(n=2, acc=12)
      frame(n=1, acc=24)
        frame(n=0, acc=24)

Vòng lặp:
một frame của phương thức
  (n=4, acc=1) → (n=3, acc=4)
  → (n=2, acc=12) → (n=1, acc=24)
  → (n=0, acc=24) → trả 24
~~~

Sơ đồ thể hiện **khác biệt cấu trúc lời gọi**, không phải mô tả chính xác cách trình bày frame nội bộ của một JVM cụ thể.

## 7. Khi độ sâu lớn: chuyển đệ quy đuôi thành vòng lặp

Một ví dụ rõ hơn là tính tổng số nguyên từ 1 đến n với **long**.

Đệ quy đuôi mang trạng thái:

~~~java
static long sumTail(int n, long acc) {
    if (n == 0) {
        return acc;
    }
    return sumTail(n - 1, acc + n);
}
~~~

Đây là **đoạn mã minh họa**, giả định n không âm; bản đệ quy ở đây vẫn có nguy cơ tràn stack khi n lớn.

Phiên bản vòng lặp tương đương về ý tưởng:

~~~java
static long sumLoop(int n) {
    if (n < 0) {
        throw new IllegalArgumentException("n must be non-negative");
    }

    long acc = 0L;
    while (n > 0) {
        acc += n;
        n--;
    }
    return acc;
}
~~~

Đây cũng là **đoạn phương thức minh họa**, có thể đặt trong một lớp Java. Trong từng vòng, các biến **n** và **acc** đóng vai trò giống hệt tham số của lời gọi đệ quy đuôi kế tiếp, nhưng toàn bộ quá trình nằm trong **một lần gọi phương thức**.

Với **n = 100_000**, tổng là **5_000_050_000**, vượt phạm vi **int** nhưng nằm trong phạm vi **long**. Bài toán tính tổng này còn có công thức **n × (n + 1) / 2**; khi viết công thức trong Java vẫn phải xét kiểu số và tràn số trong các phép toán trung gian. Vòng lặp được trình bày để minh họa phép biến đổi từ đệ quy đuôi, không phải vì nó là thuật toán nhanh nhất cho tổng cấp số cộng.

## 8. Trampoline: trì hoãn lời gọi đệ quy rồi chạy bằng vòng lặp

Trong phong cách lập trình hàm, đôi khi ta muốn giữ cách diễn đạt theo các **bước tính** mà vẫn tránh một chuỗi lời gọi đệ quy lồng nhau. **Trampoline** là kỹ thuật biểu diễn mỗi bước dưới dạng “đã có kết quả” hoặc “cần tính bước kế tiếp”, rồi để một vòng lặp ngoài thực hiện lần lượt các bước.

Điều kiện mấu chốt: bước kế tiếp phải được **trì hoãn**, không gọi sâu ngay khi tạo ra bước hiện tại. Trong Java có thể dùng **Supplier** để bọc thao tác đó.

Ví dụ Java 17 độc lập, tạo tệp **TrampolineSum.java**:

~~~java
import java.util.function.Supplier;

public class TrampolineSum {
    sealed interface Bounce permits Call, Done {}

    record Call(Supplier<Bounce> next) implements Bounce {}
    record Done(long value) implements Bounce {}

    static Bounce sum(int n, long acc) {
        if (n == 0) {
            return new Done(acc);
        }
        return new Call(() -> sum(n - 1, acc + n));
    }

    static long run(Bounce start) {
        Bounce current = start;
        while (current instanceof Call call) {
            current = call.next().get();
        }
        return ((Done) current).value();
    }

    public static void main(String[] args) {
        int n = 100_000;
        System.out.println(run(sum(n, 0L)));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac TrampolineSum.java
java TrampolineSum
~~~

Stdout:

~~~text
5000050000
~~~

Diễn giải luồng thực thi:

1. **sum(n, acc)** chỉ tạo một đối tượng **Call** chứa lambda biểu diễn bước kế, hoặc **Done** khi đạt điểm dừng.
2. Lambda **() -> sum(n - 1, acc + n)** chưa chạy khi đối tượng Call được tạo; vì vậy các bước không lồng sâu ngay lúc này.
3. **run(...)** gọi **get()** để lấy *một* bước kế, nhận kết quả rồi lặp tiếp. Mỗi lần gọi **get()** hoàn tất trước lần lặp tiếp theo.
4. Khi gặp **Done**, vòng lặp trả về giá trị cuối.

Do các bước được xử lý tuần tự trong vòng lặp, mã không tạo chuỗi sâu gồm n lời gọi **sum(...)** đồng thời. Đây là bảo đảm từ **cấu trúc chương trình**, không phụ thuộc vào việc JVM có TCO.

**Đánh đổi:** trampoline có thể tạo nhiều lambda/đối tượng Call ngắn hạn, tăng cấp phát và chi phí điều phối so với vòng lặp trực tiếp. Nó hữu ích khi cần giữ lối mô hình hóa bước tính bằng hàm hoặc có nhiều nhánh logic cần trampoline; đối với phép cộng đơn giản, vòng lặp thường dễ hiểu và tiết kiệm hơn.

Ví dụ này giả định **n ≥ 0**; trong mã sản xuất hãy kiểm tra đầu vào trước khi gọi. **long** vẫn có giới hạn: với n quá lớn, phép cộng cũng có thể tràn. Cách tránh tràn số phải được quyết định riêng với cách tránh tràn stack.

## 9. Đệ quy không đuôi: dùng cấu trúc stack tường minh khi cần

Không phải mọi bài toán đệ quy đều dễ chuyển thành accumulator. Ví dụ **duyệt cây** có thể gọi hai nhánh con, thao tác với trạng thái theo nhiều bước, hoặc cần xử lý kết quả sau khi quay lại. Một phép đổi thành tail recursion đơn giản có thể làm sai trình tự tính toán.

Khi dữ liệu có thể sâu bất thường, có thể mô phỏng call stack bằng **Deque** (thường hiện thực bởi **ArrayDeque**) và vòng lặp:

~~~java
Deque<Node> pending = new ArrayDeque<>();
pending.push(root);

while (!pending.isEmpty()) {
    Node current = pending.pop();
    // Xử lý current, rồi push các nút con theo thứ tự mong muốn.
}
~~~

Đây là **pseudocode Java minh họa**, giả định **Node**, **root** và quy tắc chọn nút con đã được định nghĩa. **ArrayDeque không cho phép phần tử null**; cần kiểm tra root và các nút con trước khi đẩy vào. Nếu cần thứ tự duyệt cụ thể (preorder, inorder, postorder), thuật toán đẩy/lấy phần tử phải được thiết kế tương ứng, không thể dùng cùng một đoạn khung cho mọi thứ tự.

Sử dụng Deque không làm biến mất nhu cầu lưu trạng thái: với thuật toán DFS, bộ nhớ thường chuyển từ **call stack** sang **cấu trúc dữ liệu trên heap**. Điều này giúp kiểm soát độ sâu lời gọi Java và cách xử lý dữ liệu lớn, nhưng vẫn tiêu tốn bộ nhớ theo quy mô của tập trạng thái cần giữ.

Với đệ quy có nhiều nhánh, một số phương án khác gồm chia nhỏ công việc, memoization cho phép tính lặp lại, dynamic programming hoặc một thuật toán lặp chuyên biệt. **Memoization giảm việc tính trùng**, nhưng tự nó **không bảo đảm loại bỏ độ sâu stack** của những chuỗi lời gọi vẫn còn.

## 10. Khi nào đệ quy vẫn là lựa chọn tốt?

Đệ quy vẫn hữu ích khi cấu trúc bài toán tự nhiên và **độ sâu tối đa đã biết hoặc được giới hạn hợp lý**: đọc biểu thức lồng nhau có giới hạn, duyệt cây có độ sâu được khống chế, thuật toán chia để trị với độ sâu logarithmic.

Lựa chọn nên dựa trên:

- **Độ sâu tối đa có thể xảy ra**, không chỉ độ sâu của bộ dữ liệu thử nhỏ.
- **Cấu trúc bài toán:** một nhánh tuyến tính, nhiều nhánh, hay trạng thái cần xử lý sau khi quay lại.
- **Khả năng đọc hiểu và kiểm chứng:** một hàm đệ quy nhỏ có base case rõ đôi khi dễ bảo trì hơn vòng lặp phức tạp.
- **Yêu cầu tài nguyên:** giới hạn stack, heap, độ lớn dữ liệu và chi phí cấp phát.
- **Rủi ro dữ liệu đối kháng:** cây hoặc danh sách liên kết suy biến do đầu vào bên ngoài có thể tạo độ sâu lớn hơn dự kiến.

Trong thiết kế API, nên ghi rõ hợp đồng như **“độ sâu cấu trúc tối đa được hỗ trợ”**, hoặc triển khai dạng lặp khi không thể bảo đảm giới hạn. Một cây nhị phân cân bằng có chiều cao **O(log n)**, nhưng một cây rất lệch có thể có chiều cao **O(n)**; cùng một hàm duyệt đệ quy có thể an toàn với cây trước mà gặp giới hạn stack với cây sau.

## 11. Những ngộ nhận và lỗi phổ biến

| Ngộ nhận/lỗi | Thực tế và cách xử lý |
| --- | --- |
| “Có **return** phía trước lời gọi thì chắc chắn là tail recursion” | **return n * f(n - 1)** vẫn phải nhân sau lời gọi, không ở tail position |
| “Dùng accumulator sẽ tự giảm stack xuống O(1) trong Java” | Accumulator làm cấu trúc trở thành tail-recursive, nhưng JVM không cam kết TCO |
| “Chạy thành công 100.000 lần trên máy tôi nghĩa là an toàn mọi nơi” | Giới hạn stack phụ thuộc JVM, cấu hình và frame; thiết kế theo giới hạn thực |
| “Tăng **-Xss** là sửa được đệ quy vô hạn” | Chỉ tăng/ngảm ngưỡng tài nguyên, không sửa điều kiện dừng hay độ phức tạp stack |
| Quên base case hoặc không tiến gần base case | Đệ quy có thể không kết thúc, dẫn tới StackOverflowError |
| Dùng **int** cho tổng lớn/giai thừa | Có thể tràn số trước cả khi đụng giới hạn stack; chọn kiểu và miền dữ liệu rõ ràng |
| Cho rằng trampoline miễn phí | Bớt phụ thuộc vào call stack nhưng có chi phí đối tượng/lambda và điều phối |
| Thay mọi lời gọi đệ quy bằng một **while** bất kể cấu trúc | Đệ quy nhiều nhánh có thể cần stack/queue tường minh để giữ đúng thứ tự và trạng thái |
| Dùng memoization rồi mặc định hết StackOverflowError | Memoization giảm phép tính trùng, không tự rút ngắn chuỗi gọi sâu |
| Bắt StackOverflowError như cách kiểm tra điểm dừng | Đây là lỗi cạn tài nguyên; nên chặn đầu vào, kiểm soát độ sâu hoặc dùng thuật toán lặp |

Một lỗi riêng của bài toán đệ quy đuôi là **không truyền đủ trạng thái qua accumulator**. Chẳng hạn, nếu phép tính phụ thuộc hai giá trị trước đó, một biến tích lũy đơn lẻ có thể không đủ. Điều cần giữ là bất biến: ở mỗi bước, cặp trạng thái mới phải chứa toàn bộ thông tin cần thiết cho kết quả cuối.

## 12. Kiểm thử và tự đánh giá

Khi viết một thuật toán đệ quy, hãy kiểm tra ít nhất:

1. **Base case:** n = 0, dữ liệu rỗng hoặc nút lá có kết quả đúng không?
2. **Bước tiến triển:** mỗi lần gọi có thật sự đến gần điểm dừng không?
3. **Đầu vào ngoài hợp đồng:** n âm, tham chiếu null hoặc cấu trúc vòng lặp dữ liệu xử lý ra sao?
4. **Tính tương đương:** cùng bộ dữ liệu, bản đệ quy, accumulator và vòng lặp trả kết quả bằng nhau chứ?
5. **Biên tài nguyên:** với độ sâu lớn nhất được hỗ trợ, runtime có đáp ứng yêu cầu stack và heap không?
6. **Số học:** có thể overflow, mất chính xác hoặc thay đổi thứ tự phép toán không?

Bài tập:

- Viết **sumTail(n, acc)** với base case n = 0, rồi chuyển nó thành một vòng **while** giữ hai biến n, acc. Giải thích vì sao bản **while** dùng độ sâu stack cố định.
- Phân loại các biểu thức **return f(n - 1)**, **return 1 + f(n - 1)** và **return f(n - 1, acc + n)** theo tail position.
- Nếu một cây có thể chứa một triệu nút nối thành một nhánh, hãy giải thích rủi ro của thuật toán DFS đệ quy trực tiếp và đề xuất cách dùng **Deque**.
- So sánh vòng lặp và trampoline theo tiêu chí stack, heap, độ đơn giản và số lần tạo đối tượng.
- Giải thích vì sao dùng **BigInteger** để tính n! lớn hơn 20 không đồng nghĩa với việc đệ quy n lời gọi trở nên an toàn.

**Điểm cần ghi nhớ:** đệ quy là một kỹ thuật mô tả thuật toán; **đệ quy đuôi** là một thuộc tính của vị trí lời gọi; **TCO** là một tối ưu hóa ở tầng thực thi. Java không cung cấp bảo đảm TCO cho mã đệ quy đuôi. Khi cần an toàn với độ sâu lớn, dùng **vòng lặp**, **trampoline** được triển khai đúng cách, hoặc **cấu trúc stack tường minh** tùy dạng bài toán.