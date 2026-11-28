# Đệ quy, điều kiện dừng và giới hạn ngăn xếp

Đệ quy (recursion) là kỹ thuật trong đó một phương thức gọi lại chính nó, trực tiếp hoặc thông qua một phương thức khác, để giải quyết một bài toán bằng những bài toán con nhỏ hơn. Trong Java 27, mỗi lần gọi phương thức đều cần một ngữ cảnh thực thi riêng trên ngăn xếp của luồng đang chạy. Vì vậy, một lời gọi đệ quy phải có **điều kiện dừng** rõ ràng và phải tiến triển về điều kiện đó; nếu không, chương trình có thể gọi lặp vô hạn cho đến khi phát sinh **StackOverflowError**.

Đệ quy đặc biệt hữu ích với cấu trúc dữ liệu và bài toán có cấu trúc tự nhiên lặp lại như cây, đồ thị, chia để trị và duyệt thư mục. Bài học này tập trung vào cách thiết kế lời gọi đệ quy an toàn, hiểu giới hạn ngăn xếp và biết khi nào nên dùng vòng lặp hoặc kỹ thuật khác.

## 1. Đệ quy hoạt động như thế nào?

Một phương thức đệ quy có thể gọi chính nó để xử lý một phiên bản nhỏ hơn của bài toán ban đầu.

Ví dụ, tổng các số nguyên từ 1 đến n có thể được định nghĩa như sau:

- Nếu n bằng 0, tổng bằng 0.
- Nếu n lớn hơn 0, tổng bằng n cộng với tổng từ 1 đến n - 1.

Ta có công thức:

\[
S(n) =
\begin{cases}
0 & \text{khi } n = 0 \\
n + S(n-1) & \text{khi } n > 0
\end{cases}
\]

Cách viết Java:

~~~java
public class RecursiveSum {
    static int sumTo(int n) {
        if (n == 0) {
            return 0;
        }

        return n + sumTo(n - 1);
    }

    public static void main(String[] args) {
        System.out.println(sumTo(5)); // 15
    }
}
~~~

Khi gọi **sumTo(5)**, các lời gọi tiếp theo lần lượt là **sumTo(4)**, **sumTo(3)**, **sumTo(2)**, **sumTo(1)** và **sumTo(0)**. Khi đến **sumTo(0)**, phương thức trả về 0. Các lời gọi trước đó tiếp tục hoàn thành theo thứ tự ngược lại.

~~~text
sumTo(5)
  = 5 + sumTo(4)
          = 4 + sumTo(3)
                  = 3 + sumTo(2)
                          = 2 + sumTo(1)
                                  = 1 + sumTo(0)
                                          = 0

Khi quay lui:
sumTo(0) = 0
sumTo(1) = 1
sumTo(2) = 3
sumTo(3) = 6
sumTo(4) = 10
sumTo(5) = 15
~~~

Điểm quan trọng là mỗi lời gọi giải quyết một phần của bài toán và kết quả được kết hợp khi các lời gọi trả về.

## 2. Hai thành phần bắt buộc của một lời giải đệ quy

Một lời giải đệ quy đúng thường có hai thành phần:

1. **Điều kiện dừng (base case):** trường hợp đơn giản nhất có thể trả kết quả trực tiếp mà không cần gọi đệ quy thêm.
2. **Bước đệ quy (recursive case):** chia bài toán hiện tại thành một hoặc nhiều bài toán nhỏ hơn, gọi phương thức để giải quyết chúng rồi kết hợp kết quả.

Với ví dụ **sumTo**:

~~~java
static int sumTo(int n) {
    if (n == 0) {       // Điều kiện dừng
        return 0;
    }

    return n + sumTo(n - 1); // Bước đệ quy
}
~~~

### 2.1. Điều kiện dừng phải bao phủ trường hợp hợp lệ

Nếu phương thức chỉ được định nghĩa cho số nguyên không âm, cần quy định rõ cách xử lý số âm. Có thể từ chối đầu vào không hợp lệ:

~~~java
static int sumTo(int n) {
    if (n < 0) {
        throw new IllegalArgumentException("n phải không âm");
    }

    if (n == 0) {
        return 0;
    }

    return n + sumTo(n - 1);
}
~~~

Điều kiện **n == 0** là base case. Điều kiện **n < 0** là kiểm tra đầu vào. Hai điều kiện có vai trò khác nhau: một điều kiện xác định kết quả của bài toán, điều kiện còn lại bảo vệ miền đầu vào mà phương thức hỗ trợ.

Một phương thức có thể có nhiều base case. Ví dụ tính giai thừa có thể dừng ở cả 0 và 1:

~~~java
static long factorial(int n) {
    if (n < 0) {
        throw new IllegalArgumentException("n phải không âm");
    }

    if (n == 0 || n == 1) {
        return 1L;
    }

    return n * factorial(n - 1);
}
~~~

### 2.2. Mỗi bước phải tiến gần đến điều kiện dừng

Có base case vẫn chưa đủ. Bước đệ quy phải làm thay đổi dữ liệu theo hướng cuối cùng đạt đến base case.

Trong **sumTo(n)**, tham số giảm một đơn vị sau mỗi lần gọi:

~~~text
n = 5 -> 4 -> 3 -> 2 -> 1 -> 0
~~~

Một cách kiểm tra hữu ích là xác định một đại lượng đo mức độ còn lại của bài toán, thường gọi là *measure* hoặc *variant*. Đại lượng này cần:

- Có giới hạn phù hợp, thường là số nguyên không âm.
- Giảm sau mỗi bước đệ quy.
- Khi đạt giá trị biên, phương thức đi vào base case.

Ví dụ, với **sumTo(n)**, đại lượng đo là n. Với việc duyệt mảng, đại lượng có thể là số phần tử còn lại. Với tìm kiếm nhị phân, đại lượng là độ dài đoạn tìm kiếm.

Nếu lời gọi đệ quy không làm đại lượng này giảm, phương thức có thể lặp vô hạn.

## 3. Ngăn xếp lời gọi phương thức (call stack)

Mỗi khi một phương thức được gọi, JVM tạo một **stack frame** (khung ngăn xếp) cho lần gọi đó trong ngăn xếp của luồng đang thực thi. Khung này chứa ngữ cảnh cần thiết để phương thức chạy và trả về, bao gồm vùng biến cục bộ, ngăn xếp toán hạng và thông tin phục vụ việc trả về.

Khi một phương thức gọi một phương thức khác, khung của lời gọi mới được đặt lên trên khung đang chờ. Khi phương thức được gọi kết thúc, khung tương ứng được loại khỏi ngăn xếp và luồng tiếp tục tại vị trí gọi.

Đệ quy cũng hoạt động theo quy tắc này. Mỗi lần phương thức gọi lại chính nó là một lần gọi mới, có tham số và biến cục bộ riêng.

### 3.1. Minh họa các stack frame

Với lời gọi **sumTo(3)**, ngăn xếp phát triển theo trình tự:

~~~text
Bắt đầu:
┌────────────────────┐
│ sumTo(3)            │
└────────────────────┘

Sau lời gọi sumTo(2):
┌────────────────────┐
│ sumTo(2)            │
├────────────────────┤
│ sumTo(3) đang chờ   │
└────────────────────┘

Sau lời gọi sumTo(1):
┌────────────────────┐
│ sumTo(1)            │
├────────────────────┤
│ sumTo(2) đang chờ   │
├────────────────────┤
│ sumTo(3) đang chờ   │
└────────────────────┘

Sau lời gọi sumTo(0):
┌────────────────────┐
│ sumTo(0)            │
├────────────────────┤
│ sumTo(1) đang chờ   │
├────────────────────┤
│ sumTo(2) đang chờ   │
├────────────────────┤
│ sumTo(3) đang chờ   │
└────────────────────┘
~~~

Khi **sumTo(0)** trả về, frame của nó được gỡ bỏ. Sau đó **sumTo(1)** tiếp tục tính, trả về, rồi đến **sumTo(2)** và cuối cùng là **sumTo(3)**.

Mỗi frame giữ trạng thái của một lần gọi. Vì vậy, các biến cục bộ cùng tên trong những lần gọi khác nhau không ghi đè lên nhau.

### 3.2. Ngăn xếp thuộc về luồng

Mỗi luồng Java có ngăn xếp JVM riêng. Khi một luồng chạy đệ quy, các frame của những lần gọi đó được tích lũy trong ngăn xếp của chính luồng ấy.

Điều này có nghĩa:

- Độ sâu đệ quy của một luồng không trực tiếp làm tăng số frame trong ngăn xếp của luồng khác.
- Nhiều luồng có thể cùng chạy đệ quy, mỗi luồng chịu giới hạn ngăn xếp của nó.
- Tạo thêm luồng không phải là cách khắc phục một thuật toán đệ quy có độ sâu không kiểm soát.

Không nên nhầm stack frame với đối tượng Java. Một frame lưu ngữ cảnh thực thi của một lần gọi; các đối tượng được tạo bởi mã Java được quản lý theo mô hình bộ nhớ của JVM. Việc một biến cục bộ chứa tham chiếu không có nghĩa toàn bộ đối tượng mà nó tham chiếu nằm trong frame đó.

## 4. StackOverflowError và nguyên nhân

**StackOverflowError** là một lỗi thuộc nhóm **Error**, được JVM ném ra khi một luồng cần nhiều ngăn xếp hơn mức JVM có thể cung cấp cho luồng đó.

Trường hợp thường gặp là đệ quy quá sâu hoặc không có điều kiện dừng. Ví dụ sau không bao giờ tiến đến base case:

~~~java
static void repeat() {
    repeat();
}
~~~

Mỗi lần gọi **repeat()** lại tạo một lần gọi mới trước khi lời gọi hiện tại có thể kết thúc. Ngăn xếp tăng liên tục và cuối cùng có thể vượt quá giới hạn.

Một lỗi khác là có base case nhưng bước đệ quy không tiến triển:

~~~java
static int countDown(int n) {
    if (n == 0) {
        return 0;
    }

    return countDown(n); // Sai: n không thay đổi
}
~~~

Với n khác 0, lời gọi luôn giữ nguyên tham số và không bao giờ chạm đến base case.

Một ví dụ khác có thể kết thúc với đầu vào nhỏ nhưng vẫn nguy hiểm với đầu vào lớn:

~~~java
static long factorial(int n) {
    if (n <= 1) {
        return 1L;
    }

    return n * factorial(n - 1);
}
~~~

Với n rất lớn, số lời gọi lồng nhau cũng rất lớn. Ngay cả khi kết quả toán học không tràn số, độ sâu đệ quy vẫn có thể vượt giới hạn ngăn xếp.

### 4.1. Phân biệt lỗi logic và giới hạn tài nguyên

Khi gặp **StackOverflowError**, hãy kiểm tra:

1. Có base case không?
2. Tất cả đường đi có thể đạt đến base case không?
3. Tham số hoặc đoạn dữ liệu có thực sự tiến triển không?
4. Có nhánh nào gọi đệ quy lặp lại cùng dữ liệu không?
5. Độ sâu tối đa có phù hợp với kích thước đầu vào thực tế không?
6. Có thể thay thuật toán bằng vòng lặp hoặc cấu trúc dữ liệu tường minh không?

Nếu phương thức không có điều kiện dừng, đó là lỗi logic. Nếu phương thức có thể dừng nhưng cần hàng trăm nghìn hoặc hàng triệu frame, thiết kế vẫn có thể không phù hợp với giới hạn tài nguyên của runtime.

### 4.2. Không dựa vào một độ sâu ngăn xếp cố định

Java không quy định một con số độ sâu đệ quy an toàn áp dụng cho mọi chương trình. Độ sâu có thể thay đổi tùy JVM, hệ điều hành, cấu hình luồng, dữ liệu cục bộ và cách trình biên dịch/JIT triển khai mã.

Vì vậy, không nên viết logic kiểu "đệ quy an toàn đến đúng N lần" dựa trên một con số quan sát được trên máy phát triển. Hãy phân tích độ sâu tối đa theo kích thước dữ liệu, thử nghiệm trong môi trường triển khai và chọn thuật toán có giới hạn bộ nhớ phù hợp.

Tăng kích thước stack của luồng bằng tùy chọn cấu hình JVM có thể làm thay đổi ngưỡng gặp lỗi trên một môi trường cụ thể. Đây không phải là bằng chứng rằng thuật toán đã an toàn, cũng không thay thế việc sửa đệ quy không kết thúc hoặc độ sâu tăng không giới hạn.

## 5. Thiết kế đệ quy đúng: ví dụ tính giai thừa

Giai thừa của số nguyên không âm được định nghĩa:

\[
n! =
\begin{cases}
1 & \text{khi } n = 0 \\
n \times (n-1)! & \text{khi } n > 0
\end{cases}
\]

Một triển khai có kiểm tra miền đầu vào và phát hiện tràn số:

~~~java
public class FactorialExample {
    static long factorial(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("n phải không âm");
        }

        if (n == 0 || n == 1) {
            return 1L;
        }

        return Math.multiplyExact((long) n, factorial(n - 1));
    }

    public static void main(String[] args) {
        System.out.println(factorial(5)); // 120
        System.out.println(factorial(20));
        // factorial(21) ném ArithmeticException do long bị tràn
    }
}
~~~

Có ba điểm cần chú ý:

- Base case trả về 1 cho 0 và 1.
- Mỗi lần gọi giảm n đi một, nên đầu vào hợp lệ cuối cùng đạt base case.
- **Math.multiplyExact** phát hiện phép nhân vượt phạm vi long và ném **ArithmeticException**.

Ví dụ này cho thấy hai giới hạn khác nhau: giới hạn độ sâu ngăn xếp và giới hạn miền giá trị của kiểu số. Khắc phục một giới hạn không tự khắc phục giới hạn còn lại.

## 6. Đệ quy trực tiếp và đệ quy gián tiếp

### 6.1. Đệ quy trực tiếp

Đệ quy trực tiếp (direct recursion) xảy ra khi một phương thức gọi lại chính nó:

~~~java
static int sumTo(int n) {
    if (n == 0) {
        return 0;
    }

    return n + sumTo(n - 1);
}
~~~

Đây là hình thức dễ nhận biết nhất.

### 6.2. Đệ quy gián tiếp hoặc tương hỗ

Đệ quy gián tiếp (indirect recursion), còn gọi là đệ quy tương hỗ (mutual recursion), xảy ra khi một phương thức gọi phương thức thứ hai, rồi phương thức thứ hai gọi lại phương thức đầu tiên, có thể qua nhiều phương thức trung gian.

Ví dụ kiểm tra một số nguyên không âm là chẵn hay lẻ:

~~~java
public class MutualRecursion {
    static boolean isEven(int n) {
        if (n == 0) {
            return true;
        }

        return isOdd(n - 1);
    }

    static boolean isOdd(int n) {
        if (n == 0) {
            return false;
        }

        return isEven(n - 1);
    }

    public static void main(String[] args) {
        System.out.println(isEven(8)); // true
        System.out.println(isOdd(8));  // false
    }
}
~~~

Hai phương thức có base case riêng và mỗi lần gọi đều giảm n. Nếu bỏ base case hoặc không giảm tham số, chuỗi gọi qua lại cũng có thể dẫn đến **StackOverflowError**.

Khi đọc mã nguồn lớn, cần theo dõi cả chuỗi gọi giữa các phương thức, không chỉ tìm một phương thức có gọi chính nó hay không.

## 7. Đệ quy với cấu trúc dữ liệu

Đệ quy thường phù hợp với cấu trúc có tính chất tự lặp, chẳng hạn cây, danh sách liên kết, biểu thức lồng nhau hoặc thư mục con.

### 7.1. Duyệt cây nhị phân

Mỗi nút của cây nhị phân có thể có cây con trái và cây con phải. Ta có thể định nghĩa một nút bằng record:

~~~java
record Node(int value, Node left, Node right) {
}
~~~

Một cây ví dụ:

~~~text
          10
         /  \
        5    15
       / \     \
      3   7     20
~~~

Duyệt inorder (trái, nút, phải) có thể viết đệ quy:

~~~java
static void inorder(Node node) {
    if (node == null) {
        return;
    }

    inorder(node.left());
    System.out.print(node.value() + " ");
    inorder(node.right());
}
~~~

**null** là base case vì cây con không tồn tại thì không còn nút để duyệt. Mỗi lời gọi chuyển sang một cây con nhỏ hơn.

Với cây có n nút, việc duyệt inorder thăm mỗi nút một lần nên có độ phức tạp thời gian O(n). Độ sâu ngăn xếp phụ thuộc chiều cao cây h, tức O(h). Cây cân bằng thường có chiều cao cỡ O(log n), trong khi cây lệch có thể có chiều cao O(n).

### 7.2. Tìm kiếm nhị phân bằng đệ quy

Tìm kiếm nhị phân chỉ áp dụng trực tiếp khi mảng đã được sắp xếp theo thứ tự phù hợp. Mỗi bước so sánh phần tử giữa và loại bỏ một nửa đoạn tìm kiếm.

~~~java
static int binarySearch(int[] values, int target, int left, int right) {
    if (left > right) {
        return -1;
    }

    int middle = left + (right - left) / 2;

    if (values[middle] == target) {
        return middle;
    }

    if (values[middle] < target) {
        return binarySearch(values, target, middle + 1, right);
    }

    return binarySearch(values, target, left, middle - 1);
}
~~~

Cách gọi:

~~~java
int[] values = {2, 5, 8, 12, 16, 23, 38};
int index = binarySearch(values, 16, 0, values.length - 1);

System.out.println(index); // 4
~~~

Base case **left > right** biểu thị đoạn tìm kiếm đã rỗng và không tìm thấy phần tử. Mỗi bước thu hẹp khoảng tìm kiếm khoảng một nửa.

Độ phức tạp thời gian là O(log n), độ sâu ngăn xếp cũng là O(log n). Đây là ví dụ đệ quy có độ sâu tăng chậm theo kích thước dữ liệu.

### 7.3. Duyệt đồ thị và phát hiện chu trình

Đồ thị có thể chứa chu trình. Nếu một phương thức DFS gọi đệ quy đến các đỉnh kề mà không ghi nhận đỉnh đã thăm, hai đỉnh có cạnh nối qua lại có thể gọi nhau vô hạn.

Dùng một tập **visited** dùng chung cho toàn bộ quá trình duyệt:

~~~java
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

static void depthFirstSearch(
        int current,
        Map<Integer, List<Integer>> graph,
        Set<Integer> visited) {

    if (!visited.add(current)) {
        return;
    }

    System.out.println(current);

    for (int neighbor : graph.getOrDefault(current, List.of())) {
        depthFirstSearch(neighbor, graph, visited);
    }
}
~~~

Ví dụ gọi:

~~~java
Map<Integer, List<Integer>> graph = Map.of(
        1, List.of(2, 3),
        2, List.of(1, 4),
        3, List.of(1, 4),
        4, List.of(2, 3)
);

Set<Integer> visited = new HashSet<>();
depthFirstSearch(1, graph, visited);
~~~

Phương thức **visited.add(current)** trả về false nếu đỉnh đã có trong tập. Khi đó, phương thức dừng nhánh hiện tại. Tập visited là trạng thái dùng chung giữa các lời gọi; không tạo một tập mới ở mỗi lần gọi vì sẽ làm mất khả năng phát hiện đỉnh đã thăm ở nhánh khác.

Với biểu diễn danh sách kề, DFS có thời gian O(V + E), trong đó V là số đỉnh và E là số cạnh. Độ sâu đệ quy trong trường hợp xấu nhất có thể là O(V). Với đồ thị rất sâu hoặc lớn, cân nhắc DFS lặp với stack tường minh.

## 8. Độ sâu đệ quy, thời gian và bộ nhớ

Khi phân tích một phương thức đệ quy, cần xem xét ít nhất ba yếu tố:

- **Số lời gọi:** tổng số lần phương thức được thực thi.
- **Độ sâu tối đa:** số lời gọi lồng nhau đồng thời tại thời điểm sâu nhất.
- **Công việc mỗi lời gọi:** phép tính hoặc thao tác được thực hiện trong một frame.

Hai thuật toán có thể có cùng số lời gọi nhưng độ sâu tối đa và bộ nhớ khác nhau.

| Bài toán | Số lời gọi hoặc thời gian điển hình | Độ sâu ngăn xếp |
|---|---:|---:|
| Tính tổng từ 1 đến n theo cách đệ quy tuyến tính | O(n) | O(n) |
| Tính giai thừa đệ quy | O(n) | O(n) |
| Tìm kiếm nhị phân | O(log n) | O(log n) |
| Duyệt cây có n nút | O(n) | O(h), h là chiều cao cây |
| Fibonacci đệ quy không ghi nhớ | O(2^n) là cận trên thường dùng | O(n) |
| DFS trên đồ thị | O(V + E) | O(V) trong trường hợp xấu nhất |

Độ phức tạp không chỉ cho biết thời gian chạy. Độ sâu ngăn xếp giúp dự đoán nguy cơ dùng quá nhiều stack frame. Một thuật toán có thời gian O(n) vẫn có thể không phù hợp nếu độ sâu đệ quy cũng là O(n) và n có thể rất lớn.

### 8.1. Fibonacci và lời gọi lặp lại

Định nghĩa Fibonacci:

\[
F(n) =
\begin{cases}
0 & n = 0 \\
1 & n = 1 \\
F(n-1) + F(n-2) & n > 1
\end{cases}
\]

Một triển khai trực tiếp:

~~~java
static long fibonacci(int n) {
    if (n < 0) {
        throw new IllegalArgumentException("n phải không âm");
    }

    if (n <= 1) {
        return n;
    }

    return fibonacci(n - 1) + fibonacci(n - 2);
}
~~~

Cách viết này dễ hiểu nhưng tính lại nhiều giá trị. Ví dụ, **fibonacci(5)** gọi **fibonacci(4)** và **fibonacci(3)**. Cả hai nhánh lại tiếp tục gọi **fibonacci(3)** hoặc **fibonacci(2)**, khiến cùng một bài toán con được giải nhiều lần.

Cận trên thời gian thường được mô tả là O(2^n), trong khi độ sâu ngăn xếp là O(n). Ngoài ra, kiểu **long** có giới hạn biểu diễn nên kết quả sẽ tràn nếu tính các chỉ số đủ lớn.

### 8.2. Memoization: lưu kết quả bài toán con

Memoization lưu kết quả đã tính để tái sử dụng thay vì giải lại cùng một bài toán con.

~~~java
import java.math.BigInteger;

public class FibonacciMemo {
    static BigInteger fibonacci(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("n phải không âm");
        }

        BigInteger[] memo = new BigInteger[n + 1];
        return fibonacci(n, memo);
    }

    private static BigInteger fibonacci(int n, BigInteger[] memo) {
        if (n <= 1) {
            return BigInteger.valueOf(n);
        }

        if (memo[n] != null) {
            return memo[n];
        }

        memo[n] = fibonacci(n - 1, memo)
                .add(fibonacci(n - 2, memo));

        return memo[n];
    }

    public static void main(String[] args) {
        System.out.println(fibonacci(100));
    }
}
~~~

Với mỗi chỉ số, kết quả chỉ được tính một lần. Số trạng thái là O(n), nên số lời gọi và thời gian tính toán cộng dồn là O(n) phép toán BigInteger; chi phí số học thực tế còn phụ thuộc kích thước các số. Độ sâu ngăn xếp vẫn là O(n), và mảng memo dùng O(n) tham chiếu.

Memoization giảm công việc lặp lại nhưng không tự giảm độ sâu đệ quy. Nếu n có thể rất lớn, phiên bản vòng lặp thường an toàn hơn về ngăn xếp.

## 9. Đệ quy đuôi và giới hạn trong Java

Một lời gọi đệ quy được gọi là **đệ quy đuôi (tail recursion)** khi lời gọi đệ quy là thao tác cuối cùng của phương thức trước khi trả kết quả. Ví dụ:

~~~java
static long sumTail(int n, long accumulator) {
    if (n < 0) {
        throw new IllegalArgumentException("n phải không âm");
    }

    if (n == 0) {
        return accumulator;
    }

    return sumTail(n - 1, accumulator + n);
}
~~~

Lời gọi **sumTail** nằm ở vị trí cuối cùng. Không còn phép tính nào cần thực hiện sau khi lời gọi trả về.

Trong một số ngôn ngữ hoặc runtime, trình biên dịch có thể biến đổi đệ quy đuôi thành vòng lặp để giảm số stack frame. Tuy nhiên, **Java không bảo đảm tail-call elimination** trong đặc tả ngôn ngữ hoặc JVM. Không được giả định rằng đệ quy đuôi sẽ tự động có bộ nhớ ngăn xếp O(1).

Với Java, nếu cần xử lý số lần lặp rất lớn, hãy viết vòng lặp tường minh hoặc dùng cấu trúc dữ liệu tường minh để quản lý trạng thái.

## 10. Chuyển đệ quy thành vòng lặp

Nhiều thuật toán đệ quy tuyến tính có thể được viết lại bằng vòng lặp. Ví dụ tính tổng từ 1 đến n:

~~~java
static long sumToIterative(int n) {
    if (n < 0) {
        throw new IllegalArgumentException("n phải không âm");
    }

    long sum = 0;

    for (long current = 1; current <= n; current++) {
        sum += current;
    }

    return sum;
}
~~~

So sánh với phiên bản đệ quy:

~~~java
static long sumToRecursive(int n) {
    if (n < 0) {
        throw new IllegalArgumentException("n phải không âm");
    }

    if (n == 0) {
        return 0;
    }

    return n + sumToRecursive(n - 1);
}
~~~

| Tiêu chí | Đệ quy | Vòng lặp |
|---|---|---|
| Cách biểu diễn | Một lời gọi xử lý bài toán nhỏ hơn | Cập nhật trạng thái trong cùng một phương thức |
| Điều kiện kết thúc | Base case | Điều kiện của vòng lặp |
| Trạng thái chờ | Được lưu trong các stack frame | Thường lưu trong biến cục bộ hoặc cấu trúc dữ liệu |
| Độ sâu ngăn xếp | Có thể tăng theo số bước đệ quy | Thường không tăng theo số vòng lặp |
| Phù hợp | Cây, cấu trúc lồng nhau, chia để trị | Lặp tuyến tính dài, xử lý tuần tự, giới hạn stack cần thấp |

Với ví dụ tổng tuyến tính, vòng lặp dùng O(1) bộ nhớ phụ trợ theo mô hình thuật toán, trong khi đệ quy dùng O(n) stack frame. Với cây hoặc thuật toán chia để trị, đệ quy có thể mô tả cấu trúc bài toán tự nhiên hơn. Khi cần tránh stack overflow, có thể dùng một **Deque** làm ngăn xếp tường minh và tự quản lý các nút cần xử lý.

### 10.1. Dùng stack tường minh để duyệt cây

Duyệt preorder (nút, trái, phải) có thể viết bằng vòng lặp và **Deque**:

~~~java
import java.util.ArrayDeque;
import java.util.Deque;

static void preorderIterative(Node root) {
    if (root == null) {
        return;
    }

    Deque<Node> stack = new ArrayDeque<>();
    stack.push(root);

    while (!stack.isEmpty()) {
        Node node = stack.pop();
        System.out.print(node.value() + " ");

        if (node.right() != null) {
            stack.push(node.right());
        }

        if (node.left() != null) {
            stack.push(node.left());
        }
    }
}
~~~

Đẩy nút phải trước nút trái để nút trái được lấy ra trước, đúng thứ tự preorder. Cách này vẫn cần bộ nhớ O(h) trong trường hợp cây thông thường, nhưng trạng thái được lưu trong collection thay vì stack frame của lời gọi đệ quy. Chương trình có thể chủ động kiểm soát cấu trúc và cách sử dụng bộ nhớ.

## 11. Những lỗi thiết kế đệ quy thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Thiếu base case | Lời gọi tiếp tục cho đến khi hết stack | Xác định trường hợp đơn giản nhất và trả về trực tiếp |
| Base case không thể đạt tới | Đệ quy không kết thúc với đầu vào đó | Kiểm tra hướng thay đổi tham số ở mọi nhánh |
| Tham số không thay đổi | Lặp lại cùng bài toán | Giảm kích thước bài toán hoặc cập nhật chỉ số/ranh giới |
| Bỏ sót một nhánh trong cây | Không duyệt hết dữ liệu | Kiểm tra tất cả nhánh con theo yêu cầu thuật toán |
| Tính lại cùng bài toán con | Tốn thời gian tăng nhanh | Dùng memoization hoặc dynamic programming |
| Đệ quy quá sâu | Có thể phát sinh StackOverflowError | Dùng vòng lặp hoặc stack tường minh khi độ sâu lớn |
| Không kiểm tra dữ liệu đầu vào | Kết quả sai hoặc lỗi không rõ nguyên nhân | Xác định miền đầu vào và kiểm tra tại ranh giới phương thức |
| Dùng kiểu số không đủ lớn | Kết quả tràn số dù đệ quy kết thúc | Chọn kiểu phù hợp, dùng Math.addExact, Math.multiplyExact hoặc BigInteger khi cần |

### 11.1. Đừng dùng try-catch để che lỗi đệ quy không kết thúc

**StackOverflowError** thuộc nhóm **Error**, không phải lỗi nghiệp vụ thông thường mà thuật toán nên bắt để tiếp tục. Bắt lỗi này rồi tiếp tục xử lý thường không khôi phục được trạng thái hợp lệ của chương trình.

Hãy sửa nguyên nhân: base case, tiến triển của tham số, độ sâu tối đa hoặc lựa chọn thuật toán. Có thể ghi nhận lỗi ở tầng phù hợp để chẩn đoán, nhưng không nên xem bắt **StackOverflowError** là chiến lược kiểm soát đệ quy.

### 11.2. Cẩn thận với lời gọi đệ quy trong nhiều nhánh

Một phương thức có thể gọi đệ quy nhiều lần trong cùng một lần thực thi:

~~~java
static int countPaths(int steps) {
    if (steps < 0) {
        return 0;
    }

    if (steps == 0) {
        return 1;
    }

    return countPaths(steps - 1) + countPaths(steps - 2);
}
~~~

Phương thức này minh họa cách chia bài toán thành hai nhánh. Mỗi nhánh tạo lời gọi mới và có thể lặp lại nhiều trạng thái. Nếu không lưu kết quả, số lời gọi tăng nhanh.

Khi thiết kế đệ quy phân nhánh, hãy phân tích cả số nhánh, độ sâu và số trạng thái trùng lặp; chỉ kiểm tra việc tham số có giảm là chưa đủ để đánh giá hiệu quả.

## 12. Quy trình thiết kế và kiểm tra một phương thức đệ quy

Khi giải một bài toán bằng đệ quy, hãy đi theo trình tự:

1. **Xác định bài toán và miền đầu vào.** Ví dụ, đầu vào có thể âm không? Mảng có thể null không? Cây rỗng được biểu diễn ra sao?
2. **Viết định nghĩa toán học hoặc quy tắc chia bài toán.** Xác định kết quả cần trả về và cách kết quả của bài toán lớn phụ thuộc vào bài toán nhỏ.
3. **Xác định base case.** Bao phủ các trường hợp nhỏ nhất và mọi trạng thái kết thúc hợp lệ.
4. **Viết recursive case.** Mỗi lời gọi phải giải một bài toán nhỏ hơn hoặc gần điều kiện dừng hơn.
5. **Chứng minh tiến triển.** Xác định đại lượng giảm sau mỗi bước và bảo đảm không có nhánh nào giữ nguyên hoặc đi ngược vô hạn.
6. **Phân tích độ phức tạp.** Ước lượng số lời gọi, độ sâu tối đa và bộ nhớ phụ trợ.
7. **Kiểm tra biên.** Thử trường hợp rỗng, kích thước nhỏ nhất, một phần tử, dữ liệu lớn và dữ liệu không hợp lệ.
8. **Chọn cấu trúc thực thi phù hợp.** Nếu độ sâu có thể lớn, cân nhắc vòng lặp hoặc stack tường minh.

Một bộ trường hợp kiểm thử cơ bản cho **sumTo** có thể gồm:

| Đầu vào | Kết quả mong đợi |
|---:|---:|
| 0 | 0 |
| 1 | 1 |
| 5 | 15 |
| 10 | 55 |
| -1 | Ném IllegalArgumentException |

Với bài toán có cấu trúc dữ liệu, bổ sung trường hợp cấu trúc rỗng, một nút, cây lệch và cây có nhiều nhánh. Những trường hợp này giúp phát hiện base case bị thiếu và lỗi bỏ sót nhánh.

## 13. Ví dụ tổng hợp: tính tổng các nút của cây

Ví dụ hoàn chỉnh sử dụng record cho nút cây, phương thức đệ quy tính tổng và phương thức main kiểm tra:

~~~java
public class TreeSumExample {
    record Node(int value, Node left, Node right) {
    }

    static long sum(Node node) {
        if (node == null) {
            return 0L;
        }

        return node.value()
                + sum(node.left())
                + sum(node.right());
    }

    public static void main(String[] args) {
        Node root = new Node(
                10,
                new Node(5,
                        new Node(3, null, null),
                        new Node(7, null, null)),
                new Node(15,
                        null,
                        new Node(20, null, null))
        );

        System.out.println(sum(root)); // 60
        System.out.println(sum(null)); // 0
    }
}
~~~

Phân tích:

- **Node** là record biểu diễn một nút và hai cây con.
- **sum(null)** là base case, trả về 0 vì cây rỗng không có giá trị.
- Với nút khác null, phương thức cộng giá trị nút hiện tại với tổng cây con trái và cây con phải.
- Mỗi nhánh đi xuống một cây con, nên bài toán nhỏ hơn.
- Mỗi nút được xử lý một lần, do đó thời gian O(n).
- Độ sâu ngăn xếp phụ thuộc chiều cao cây h, do đó bộ nhớ stack O(h).

Nếu cây có thể rất lệch và chứa số lượng nút lớn, cần cân nhắc phiên bản lặp với **Deque** để kiểm soát stack tường minh.

## 14. Những điều cần ghi nhớ

- Đệ quy là phương thức giải bài toán bằng cách gọi lại chính nó trực tiếp hoặc gián tiếp.
- Một lời giải cần base case và recursive case rõ ràng.
- Mỗi bước phải làm bài toán tiến gần đến điều kiện dừng.
- Mỗi lời gọi lồng nhau cần một stack frame trong ngăn xếp của luồng đang chạy.
- **StackOverflowError** có thể xảy ra khi độ sâu đệ quy vượt giới hạn ngăn xếp.
- Java không bảo đảm tối ưu hóa đệ quy đuôi; không dựa vào tail-call elimination để xử lý độ sâu lớn.
- Phân tích cả số lời gọi, độ sâu tối đa và công việc mỗi lời gọi.
- Memoization giảm việc tính lặp lại nhưng không tự loại bỏ độ sâu đệ quy.
- Vòng lặp hoặc **Deque** là lựa chọn phù hợp khi cần kiểm soát số stack frame hoặc độ sâu có thể rất lớn.
- Chọn đệ quy khi nó làm rõ cấu trúc bài toán và độ sâu có thể kiểm soát được.

## Tài liệu tham khảo chính thức

- [Java Virtual Machine Specification, Java SE 27 — Java Virtual Machine Stacks](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-2.html#jvms-2.5.2)
- [Java Virtual Machine Specification, Java SE 27 — Errors](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-2.html#jvms-2.10)
- [StackOverflowError API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/StackOverflowError.html)
- [Deque API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Deque.html)
- [ArrayDeque API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/ArrayDeque.html)
- [Math API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Math.html)
- [BigInteger API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/math/BigInteger.html)
