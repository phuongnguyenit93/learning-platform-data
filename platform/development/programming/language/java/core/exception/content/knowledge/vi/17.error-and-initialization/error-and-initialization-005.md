# StackOverflowError và đệ quy không kiểm soát trong Java

> **Phạm vi:** Java Core → Exception → Error và khởi tạo. `StackOverflowError` là một loại `Error` mà JVM thường phát sinh khi quá trình thực thi của **một thread** cần thêm không gian *call stack* nhưng không thể đáp ứng. Nguồn gây ra rất hay gặp là **đệ quy không có điểm dừng, không tiến gần điểm dừng, gọi qua lại vô hạn, hoặc đệ quy hữu hạn nhưng quá sâu**. Điều quan trọng không phải “bắt lỗi để tiếp tục” mà là thiết kế **điều kiện dừng, bước tiến, giới hạn độ sâu và thuật toán duyệt dữ liệu phù hợp**.

## 1. Nhận diện đúng `StackOverflowError`

Cây kế thừa rút gọn:

```text
java.lang.Throwable
├── java.lang.Exception
│   └── java.lang.RuntimeException
└── java.lang.Error
    └── java.lang.VirtualMachineError
        └── java.lang.StackOverflowError
```

`StackOverflowError` nằm **trong nhánh `Error`**, không phải `Exception`. Vì vậy:

- Nó là **unchecked throwable**: compiler không yêu cầu `catch` hoặc `throws`.
- `catch (Exception e)` **không bắt được** nó. `catch (Error e)` hay `catch (Throwable t)` có thể bắt theo hệ kế thừa, nhưng không nên biến việc bắt này thành cách vận hành bình thường.
- Nó mô tả thiếu khả năng mở rộng stack cho lời gọi/hoạt động tiếp theo, thường từ một đường gọi sâu, không phải một exception nghiệp vụ dự kiến.
- `VirtualMachineError` là nhánh cho các thất bại liên quan tới giới hạn hoặc điều kiện nghiêm trọng của máy ảo; các Error dạng này không nên xem tương đương lỗi dữ liệu đầu vào thông thường.
- Một exception lớp `IOException` hay `IllegalArgumentException` không “chuyển thành” `StackOverflowError` chỉ vì xuất hiện trong phương thức đệ quy. Đây là các loại failure khác nhau.

**Chốt ý:** `StackOverflowError` thường là **triệu chứng của một đường gọi vượt giới hạn stack**, chứ không tự cho biết điều kiện dừng nào sai. Phải lần theo code và dữ liệu đã tạo ra độ sâu ấy.

### 1.1. Vì sao từ “Overflow” dễ gây hiểu nhầm?

Đây là **stack overflow**, không phải **tràn số nguyên**:

```java
int x = Integer.MAX_VALUE;
int y = x + 1; // int overflow: số đổi dấu, thường không ném Error.
```

Và cũng không phải **heap memory đầy**: `OutOfMemoryError` là một nhánh khác của `VirtualMachineError`. Chúng có thể liên quan khi chương trình có lượng dữ liệu/lời gọi lớn, nhưng có cơ chế và chiến lược chẩn đoán khác nhau.

| Lỗi/hiện tượng | Điểm chính | Ví dụ |
| --- | --- | --- |
| `StackOverflowError` | Không đáp ứng thêm nhu cầu stack của thread | Đệ quy vô hạn hoặc quá sâu |
| `OutOfMemoryError` | Không đủ nguồn lực bộ nhớ cho yêu cầu cấp phát hoặc điều kiện VM tương ứng | Giữ một lượng lớn object trên heap |
| Tràn số `int` | Tính toán vượt miền biểu diễn số nguyên | `Integer.MAX_VALUE + 1` |
| `IllegalArgumentException` | Tham số vi phạm hợp đồng do API kiểm tra | Độ sâu âm bị từ chối |
| `NullPointerException` | Dereference `null` | `node.next.value` khi `next == null` |

Không khắc phục `StackOverflowError` bằng `Math.addExact`, và không kết luận “heap rất lớn thì đệ quy sâu bao nhiêu cũng được”.

## 2. Call stack là gì?

Mỗi thread Java có một **stack thực thi** phục vụ các lời gọi phương thức. Khi gọi method, JVM có thể tạo một **frame** chứa trạng thái cần thiết cho lần gọi ấy, chẳng hạn tham số, local variables, toán hạng trung gian và thông tin điều khiển theo mô hình JVM. Khi method trả về, frame của lần gọi có thể được loại khỏi stack.

Minh họa:

```text
main()
└── calculate(3)
    └── calculate(2)
        └── calculate(1)
            └── calculate(0)
                return
            return
        return
    return
main() tiếp tục
```

Các frame tồn tại đồng thời khi lời gọi con chưa kết thúc. Số frame được giữ phụ thuộc vào độ sâu chuỗi gọi.

**Không phải mọi lần gọi đều có kích thước frame như nhau.** Nhu cầu stack có thể phụ thuộc vào bytecode, dữ liệu local, trình biên dịch JIT, cơ chế tối ưu, kiến trúc CPU và cấu hình VM. Do đó không thể nói “một thread Java luôn gọi đệ quy tối đa đúng 10.000 lần”.

### 2.1. Stack khác heap

Khái quát:

- **Stack** gắn với luồng thực thi/phạm vi lời gọi; mỗi thread có stack riêng.
- **Heap** chứa phần lớn đối tượng và mảng do chương trình cấp phát; nhiều thread có thể tham chiếu tới object trên heap.
- Tham chiếu tới một object có thể nằm trong local variable của frame; **object được tham chiếu** không vì thế mà “nằm trên stack” theo quy tắc tổng quát.
- Cấp phát thêm object trên heap không trực tiếp kéo dài stack của một lời gọi, nhưng các thao tác tạo/duyệt object vẫn có thể dùng stack.
- JVM có thể tối ưu một số chi tiết vật lý; suy luận ở đây tập trung vào semantics của lời gọi và giới hạn tài nguyên.

**Hệ quả:** bạn có thể giữ một cây dữ liệu rất lớn trên heap nhưng duyệt bằng thuật toán lặp với stack chủ động, tránh phụ thuộc vào chuỗi lời gọi JVM quá sâu.

## 3. Những nguyên nhân phổ biến của đệ quy không kiểm soát

### 3.1. Không có *base case* (điều kiện dừng)

```java
// CỐ Ý SAI: minh họa phương thức gây đệ quy vô hạn.
static void repeat() {
    repeat();
}
```

Không có đường nào trả về. Một JVM Java thông thường sẽ tiếp tục mở rộng chuỗi lời gọi đến khi không còn đáp ứng được stack và ném `StackOverflowError`.

### 3.2. Có base case nhưng không tiến tới nó

```java
// CỐ Ý SAI: n không giảm nên n > 0 mãi đúng nếu khởi đầu n > 0.
static int countdown(int n) {
    if (n == 0) {
        return 0;
    }
    return countdown(n);
}
```

Điểm dừng có mặt nhưng **tham số của lần gọi sau không đổi**. Với n khởi đầu bằng 5, luồng không tiến gần `n == 0`.

### 3.3. Tiến sai chiều

```java
// CỐ Ý SAI: n bắt đầu dương lại tăng mãi.
static int countdown(int n) {
    if (n == 0) {
        return 0;
    }
    return countdown(n + 1);
}
```

Nếu n tăng, nó không tiến về 0. Với `int`, tràn số có thể khiến n đổi dấu, nhưng không biến thuật toán này thành đúng; đừng dựa vào overflow để tình cờ chạm điều kiện dừng.

### 3.4. Đệ quy hai chiều (*mutual recursion*)

```java
// CỐ Ý SAI khi không có điều kiện dừng thích hợp.
static void first() {
    second();
}

static void second() {
    first();
}
```

Một method nhìn riêng có thể chỉ gọi “method khác”, nhưng chuỗi `first → second → first → ...` là đệ quy vô hạn. Mô hình gọi qua nhiều service, callback, serializer, getter và `toString()` cũng có thể tạo chu trình tương tự.

### 3.5. Dữ liệu có chu trình

Duyệt linked structure hoặc graph theo lời gọi đệ quy mà không đánh dấu đã thăm có thể đi mãi theo:

```text
A.next → B
B.next → C
C.next → A
```

Ở đây điều kiện `node != null` **không đủ**: các liên kết không bao giờ tới `null`. Thuật toán cần nhận diện các node đã gặp hoặc có hợp đồng đầu vào bảo đảm cấu trúc không có chu trình.

### 3.6. Đệ quy kết thúc được nhưng sâu bất thường

Một danh sách liên kết dài hàng trăm nghìn phần tử có thể hoàn toàn **không có chu trình**. Duyệt bằng:

```java
static int size(Node node) {
    return node == null ? 0 : 1 + size(node.next);
}
```

có thể vẫn làm tràn stack khi số lời gọi lồng nhau quá lớn. **Đúng điều kiện dừng chưa đủ**; phải đánh giá **giới hạn độ sâu thực tế**.

## 4. Ba điều kiện của một đệ quy được thiết kế tốt

Hãy kiểm tra đủ ba điều:

1. **Base case:** có trạng thái mà ở đó method trả kết quả, không gọi tiếp?
2. **Progress:** ở mỗi lời gọi tiếp theo có một đại lượng đo tiến triển hướng tới base case (ví dụ n giảm về 0, số phần tử chưa duyệt giảm)?
3. **Depth bound:** có thể chứng minh/giới hạn độ sâu tối đa đủ nhỏ cho môi trường chạy?

Với đệ quy trên số nguyên n không âm:

```java
static int sumUpTo(int n) {
    if (n == 0) {
        return 0;
    }
    return n + sumUpTo(n - 1);
}
```

Đây là method **minh họa**, giả định n không âm và tổng không tràn `int`. Base case `n == 0` và progress `n - 1` giúp method dừng với n hợp lệ, nhưng depth khoảng n+1 nên vẫn không thích hợp cho n tùy ý cực lớn.

### 4.1. Java 17 — ví dụ an toàn: đệ quy có base case và bước tiến

Tạo **`BoundedRecursionDemo.java`**:

```java
public class BoundedRecursionDemo {
    static long factorial(int n) {
        if (n < 0 || n > 20) {
            throw new IllegalArgumentException(
                    "n phải thuộc [0, 20]");
        }
        if (n <= 1) {
            return 1L;
        }
        return Math.multiplyExact(n, factorial(n - 1));
    }

    public static void main(String[] args) {
        System.out.println("0! = " + factorial(0));
        System.out.println("5! = " + factorial(5));
        System.out.println("10! = " + factorial(10));

        try {
            factorial(-1);
        } catch (IllegalArgumentException e) {
            System.out.println("Invalid: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Biên dịch/chạy JDK 17+:

```bash
javac -encoding UTF-8 BoundedRecursionDemo.java
java BoundedRecursionDemo
```

Stdout:

```text
0! = 1
5! = 120
10! = 3628800
Invalid: IllegalArgumentException
```

Giải thích:

- `factorial(0)` và `factorial(1)` trả `1`: **base case**.
- Mỗi bước dùng `n - 1`, nên `n` tiến về base case.
- Giới hạn `n <= 20` bảo đảm kết quả factorial vừa trong phạm vi `long`; `20!` phù hợp, còn `21!` vượt `long`.
- `Math.multiplyExact` kiểm tra tràn số, **không** phải cơ chế chống stack overflow. Giới hạn n mới đảm bảo số lời gọi nhỏ.
- Với n âm, method chủ động ném `IllegalArgumentException` thay vì cho phép đệ quy sai.
- Đây là ví dụ an toàn để học: không cố tạo `StackOverflowError` trên đường chạy bình thường.

## 5. Một ví dụ cố ý gây `StackOverflowError` — chỉ dùng để nhận diện

Nếu muốn quan sát đúng loại lỗi, có thể chạy trong tiến trình thử nghiệm độc lập với đoạn sau. **Không sử dụng đây làm cách tính toán hay cơ chế dừng vòng lặp trong ứng dụng thật.** Đừng phụ thuộc vào số lần gọi/độ dài stack trace.

Tạo **`IntentionalStackOverflowDemo.java`**:

```java
public class IntentionalStackOverflowDemo {
    static void infinite() {
        infinite(); // Cố ý không có base case.
    }

    public static void main(String[] args) {
        try {
            infinite();
        } catch (StackOverflowError error) {
            System.out.println("Caught: "
                    + error.getClass().getSimpleName());
        }
    }
}
```

Chạy trên JDK 17 tiêu chuẩn trong một tiến trình thí nghiệm:

```bash
javac -encoding UTF-8 IntentionalStackOverflowDemo.java
java IntentionalStackOverflowDemo
```

Thông thường stdout là:

```text
Caught: StackOverflowError
```

**Các giới hạn cần đọc trước khi thử:**

- Đây là ví dụ **cố ý dùng hết stack của thread**; không chạy trong server production, request handler hoặc môi trường có tài nguyên rất hạn chế.
- Việc VM xử lý yêu cầu stack lớn có phụ thuộc implementation và tài nguyên; trong thực tế `StackOverflowError` là kết quả điển hình, nhưng không nên lấy số depth, thời gian hay độ dài trace làm chuẩn portable.
- Trong một trạng thái thiếu stack nghiêm trọng, hoạt động logging/formatting/cleanup phức tạp sau khi bắt có thể gặp khó khăn hoặc phát sinh thêm lỗi. Đoạn này cố giữ handler rất đơn giản và không thử gọi lại `infinite()`.
- `catch(StackOverflowError)` chỉ phục vụ **giáo dục/chẩn đoán**. Sản phẩm thật phải sửa base case, progress hoặc giới hạn độ sâu thay vì dựa vào catch như một “lối thoát an toàn”.
- Trong một số môi trường, cấu hình thread stack/VM khiến biểu hiện khác hoặc tiến trình bị hệ điều hành/VM kết thúc trước khi người học xem được output; đừng kết luận chương trình đúng chỉ vì không in được dòng mẫu.

### 5.1. Tại sao lỗi có thể xuất hiện trước khi ghi log cuối?

Lời gọi `infinite` tiếp tục được lồng vào nhau. Ở thời điểm cần một frame/nguồn stack mà thread không thể cung cấp, VM phát sinh error. Chỉ khi control được unwind đủ để tới handler và handler có thể chạy, dòng `Caught` mới xuất hiện.

Nếu log một stack trace rất dài, lượng text và chi phí output có thể lớn. Không cần in toàn bộ trace chỉ để chứng minh class của error trong bài tập.

### 5.2. Vì sao không viết `catch(Exception)`?

Vì `StackOverflowError` không nằm dưới `Exception`; nó thuộc `Error`. Nếu thay handler bằng:

```java
// KHÔNG bắt được StackOverflowError:
catch (Exception e) {
    System.out.println("Handled");
}
```

đây chỉ là **mảnh code minh họa**, không phải một chương trình hoàn chỉnh. Handler sẽ không nhận `StackOverflowError` theo quan hệ kế thừa Java.

## 6. Tràn stack không đồng nghĩa với hết heap

Java sử dụng những vùng nhớ với vai trò khác nhau. Đệ quy thường làm tăng nhu cầu stack, còn một thuật toán lưu quá nhiều object vào collection có thể làm tăng áp lực heap.

Ví dụ:

```java
static void recurse() {
    recurse();
}
```

Method này tạo chuỗi lời gọi sâu, **không bắt buộc** giữ hàng triệu object trên heap.

Ngược lại:

```java
List<byte[]> all = new ArrayList<>();
while (true) {
    all.add(new byte[1024 * 1024]);
}
```

Đây là **phản ví dụ nguy hiểm, không chạy**. Nó liên tục giữ các mảng lớn trên heap và có thể gây `OutOfMemoryError`, không phải đệ quy.

Một chương trình có thể đồng thời gây áp lực lên cả stack lẫn heap (ví dụ mỗi lời gọi tạo object lớn), nhưng để chẩn đoán cần xem **loại Throwable**, stack trace, pattern cấp phát và nguyên nhân cụ thể.

## 7. Thông điệp và stack trace: đọc ra sao?

Khi gặp lỗi:

```text
Exception in thread "main" java.lang.StackOverflowError
    at example.Parser.read(Parser.java:41)
    at example.Parser.read(Parser.java:41)
    at example.Parser.read(Parser.java:41)
    ...
```

Đây là **sơ đồ trace minh họa**, không phải stderr cố định. Dòng lặp lại cùng method và số dòng thường gợi ý đệ quy trực tiếp. Nếu có các frame lặp kiểu:

```text
A.convert(...)
B.map(...)
A.convert(...)
B.map(...)
...
```

hãy nghi ngờ **đệ quy gián tiếp** hoặc chu trình gọi.

### 7.1. Các bước đọc trace có ý nghĩa

1. Xác nhận **loại Throwable là `StackOverflowError`**, không nhầm với OOME hay recursion-specific domain exception.
2. Tìm **khối frame lặp lại** gần phần sâu của trace. Có thể chỉ một method hoặc chuỗi nhiều method.
3. Tìm vị trí **base case** và điều kiện khiến input không bao giờ đạt tới nó.
4. Kiểm tra tham số qua các lần gọi: số có giảm đúng? offset có tiến? node đã được đánh dấu visited chưa?
5. Với dữ liệu có chu trình, tái hiện từ một graph nhỏ nhất.
6. Với đầu vào hợp lệ nhưng quá sâu, đo độ sâu của dữ liệu và lựa chọn thuật toán lặp.
7. Nếu tái hiện chỉ trong môi trường triển khai, xem cấu hình stack và khác biệt ở thread pool, JDK, architecture, tối ưu hóa.
8. Nếu code đã có ràng buộc input, xác minh nó được áp dụng **trước** khi recursion chạy.

### 7.2. Vì sao trace có thể không hiển thị toàn bộ depth?

Cách in `Throwable#printStackTrace()` và dữ liệu stack trace khả dụng có thể bị ảnh hưởng bởi VM và cấu hình. HotSpot có tùy chọn như `-XX:MaxJavaStackTraceDepth` ảnh hưởng độ dài trace lưu/hiển thị; công cụ logging hoặc APM cũng có thể rút gọn.

**Không dùng số frame in ra bằng `printStackTrace` như thước đo chính xác, portable của độ sâu đệ quy.** Trace được dùng trước hết để tìm **đường gọi** và vùng code có lỗi.

## 8. `-Xss`: kích thước stack thread và những điều không được suy diễn

Nhiều JVM cho phép điều chỉnh kích thước stack cho Java thread qua tùy chọn:

```bash
java -Xss512k MyProgram
java -Xss1m MyProgram
```

Đây là các **lệnh minh họa tùy cấu hình**, giả định `MyProgram.class` đã biên dịch. JVM có thể áp giới hạn tối thiểu/tối đa; tên tùy chọn và cách hiệu lực phụ thuộc VM. Kiểm tra tài liệu và phản hồi của chính JVM đang dùng.

### 8.1. Tăng `-Xss` có giải quyết lỗi không?

**Không phải giải pháp tổng quát.** Nếu recursion **vô hạn**, tăng stack chỉ hoãn thời điểm tràn. Nếu recursion **hữu hạn, có giới hạn đã biết**, điều chỉnh kích thước stack đôi khi cho phép workload hợp lệ chạy — nhưng cần xem chi phí tài nguyên, số thread và rủi ro ở môi trường khác.

Một stack lớn hơn trên mỗi thread có thể làm tăng tổng nhu cầu memory/virtual address space của ứng dụng có hàng nghìn thread. Không tự nâng lên giá trị rất lớn khi chưa phân tích thuật toán.

### 8.2. Số lần gọi tối đa có cố định không?

Không. Ngay cả với cùng `-Xss`:

- Method nhiều biến local, biểu thức và khung lớn có thể dùng stack khác method nhỏ.
- Biên dịch JIT, inline và cách VM tổ chức frame thay đổi theo implementation và trạng thái warm-up.
- Các phiên bản JDK, hệ điều hành và CPU architecture có thể khác.
- Độ sâu hiện có tại lúc recursion bắt đầu (ví dụ từ framework) cũng khác nhau.
- Các handler/loggers có thể cần stack để hoạt động.

Vì vậy không nên ghi “JDK 17 cho đúng 1.024 lần đệ quy” như một quy tắc.

### 8.3. Thread khác nhau có stack riêng

`main` chạy trên một Java thread; request worker thread, scheduled thread hoặc những thread tự tạo có stack riêng. Một quy trình chạy được trong `main` không tự bảo đảm cùng depth sẽ chạy trong một thread có cấu hình stack nhỏ hơn. Ngược lại, một `StackOverflowError` của một thread cũng không tự là bằng chứng heap toàn JVM đã hết.

## 9. Tail recursion có tránh được `StackOverflowError` trong Java không?

*Tail recursion* là trường hợp recursive call nằm ở vị trí cuối theo logic của method.

Ví dụ:

```java
static long sumTail(long n, long acc) {
    if (n == 0) {
        return acc;
    }
    return sumTail(n - 1, acc + n);
}
```

Đây là method minh họa cho n không âm và không tràn `long`. Nó có dạng tail-recursive, nhưng **Java không bảo đảm tail-call optimization (TCO)** theo hợp đồng ngôn ngữ/JVM thông thường. Không được giả định JVM sẽ luôn tái sử dụng frame và cho phép depth vô hạn.

So sánh:

```java
static long sumNonTail(long n) {
    if (n == 0) {
        return 0L;
    }
    return n + sumNonTail(n - 1);
}
```

Đây là non-tail recursion vì sau lời gọi con còn phép cộng. Cả hai cách đều cần base case và progress; cả hai có thể dùng nhiều stack nếu depth lớn.

**Quy tắc thực hành:** Nếu cần độ sâu rất lớn và ổn định trên các JVM Java thông dụng, chuyển thành **vòng lặp** hoặc **stack/queue do chương trình quản lý** thay vì trông chờ tối ưu tail recursion.

## 10. Java 17 — ví dụ đệ quy và vòng lặp tương đương

Tạo **`RecursiveVsIterativeDemo.java`**:

```java
public class RecursiveVsIterativeDemo {
    static int sumRecursive(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("n âm");
        }
        if (n == 0) {
            return 0;
        }
        return Math.addExact(n, sumRecursive(n - 1));
    }

    static int sumIterative(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("n âm");
        }
        int sum = 0;
        for (int i = 1; i <= n; i++) {
            sum = Math.addExact(sum, i);
        }
        return sum;
    }

    public static void main(String[] args) {
        int n = 5;
        System.out.println("Recursive: " + sumRecursive(n));
        System.out.println("Iterative: " + sumIterative(n));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 RecursiveVsIterativeDemo.java
java RecursiveVsIterativeDemo
```

Stdout:

```text
Recursive: 15
Iterative: 15
```

Giải thích:

- Hai method cùng cho kết quả `1+2+3+4+5 = 15`.
- Recursion giữ các lời gọi chờ nhau, nên stack depth tăng theo n trong mô hình đánh giá thông thường.
- Vòng lặp giữ trạng thái `sum` và `i` trong **một lần gọi method**, không tạo một lời gọi mới cho mỗi số.
- `Math.addExact` xử lý overflow số nguyên bằng `ArithmeticException`, không phải StackOverflowError.
- Khi n đủ lớn, tổng có thể tràn int; ví dụ cố chọn n nhỏ để đầu ra luôn xác định. Nếu muốn hỗ trợ số lớn, có thể dùng công thức với kiểm tra overflow hoặc `BigInteger`.
- Không có nghĩa vòng lặp luôn tối ưu nhất cho mọi recursion: duyệt cây/graph đôi khi diễn đạt tự nhiên bằng recursion nếu depth nhỏ và được kiểm soát.

## 11. Đệ quy gián tiếp trong các getter, listener và `toString()`

Một vài lỗi thực tế không có phương thức tên “recurse”:

```java
class A {
    B other;
    @Override public String toString() {
        return "A(" + other + ")";
    }
}

class B {
    A other;
    @Override public String toString() {
        return "B(" + other + ")";
    }
}
```

Đây là **khai báo minh họa**, không phải chương trình runnable độc lập. Nếu `a.other=b` và `b.other=a`, gọi `a.toString()` có thể lặp qua `A.toString → B.toString → A.toString` cho đến khi tràn stack.

Các tình huống tương tự:

- `equals` hoặc `hashCode` tự gọi vòng qua quan hệ object hai chiều.
- Getter của A gọi getter B, getter B gọi lại A.
- Event listener A kích hoạt B, B gọi lại A vì thiếu flag/reentrancy guard.
- Serializer duyệt graph object có chu trình nhưng không đánh dấu identity đã thăm.
- Traversal cây mà dữ liệu thực tế đã chứa một back-reference tới parent.
- Recursive parser không tiến index khi gặp một token đặc biệt.

**Đừng sửa bằng cách bắt StackOverflowError trong `toString()`.** Hãy giảm độ sâu, không đi vào back-reference, giới hạn output hoặc dùng một context đã thăm.

## 12. Chu trình trong object graph: cần đánh dấu theo identity

Một graph có thể có **chu trình** mà hoàn toàn hợp lệ về mặt dữ liệu. Nếu thuật toán duyệt không ghi nhận đã thăm, nó có thể lặp vô hạn hoặc xử lý lặp cùng node.

Ví dụ:

```text
Node A → Node B → Node C → Node A
```

Với graph tổng quát, dùng một `Set<Node> visited`. Nếu semantics là “đã gặp cùng **đối tượng** chưa?”, Java nên đánh dấu bằng **object identity**, không phải luôn dùng `equals`/`hashCode` có thể tự đệ quy hoặc so sánh theo nội dung.

Một cách tạo identity set:

```java
Set<Node> visited = Collections.newSetFromMap(
        new IdentityHashMap<Node, Boolean>());
```

Mảnh code này cần import `Set`, `Collections`, `IdentityHashMap` và định nghĩa `Node`. `IdentityHashMap` so khóa theo `==` thay vì `equals`.

### 12.1. Java 17 — ví dụ duyệt graph có chu trình an toàn

Tạo **`CyclicGraphTraversalDemo.java`**:

```java
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public class CyclicGraphTraversalDemo {
    static final class Node {
        final String name;
        Node next;

        Node(String name) {
            this.name = name;
        }
    }

    static int countUnique(Node node, Set<Node> visited) {
        if (node == null || !visited.add(node)) {
            return 0;
        }
        return 1 + countUnique(node.next, visited);
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");
        Node c = new Node("C");

        a.next = b;
        b.next = c;
        c.next = a;

        Set<Node> visited = Collections.newSetFromMap(
                new IdentityHashMap<Node, Boolean>());

        int count = countUnique(a, visited);
        System.out.println("Unique nodes: " + count);
        System.out.println("Visited: " + visited.size());
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 CyclicGraphTraversalDemo.java
java CyclicGraphTraversalDemo
```

Stdout:

```text
Unique nodes: 3
Visited: 3
```

Từng bước:

1. A được thêm vào `visited`; đệ quy tới B.
2. B được đánh dấu; đệ quy tới C.
3. C được đánh dấu; bước kế quay về A.
4. `visited.add(a)` trả `false` vì đó là **cùng object A**, nên base case thứ hai trả 0; chu trình kết thúc.
5. Hàm đếm ba node riêng biệt.

**Giới hạn quan trọng:** `visited` xử lý **chu trình** nhưng **không tự giới hạn độ sâu**. Nếu graph là chuỗi 200.000 node khác nhau không có cycle, `countUnique` vẫn có thể dùng quá nhiều stack. Khi dữ liệu có thể rất sâu, cần kết hợp depth limit hoặc duyệt **lặp**.

## 13. Java 17 — duyệt lặp bằng `Deque` để tránh call-stack sâu

Thay vì một lời gọi recursive cho mỗi node, dùng cấu trúc dữ liệu trên heap đại diện cho các node sẽ xử lý.

Tạo **`IterativeGraphTraversalDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.Collections;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.Set;

public class IterativeGraphTraversalDemo {
    static final class Node {
        Node next;
    }

    static int countUnique(Node start) {
        if (start == null) {
            return 0;
        }

        Set<Node> visited = Collections.newSetFromMap(
                new IdentityHashMap<Node, Boolean>());
        Deque<Node> pending = new ArrayDeque<>();
        pending.push(start);

        while (!pending.isEmpty()) {
            Node current = pending.pop();
            if (!visited.add(current)) {
                continue;
            }
            if (current.next != null) {
                pending.push(current.next);
            }
        }
        return visited.size();
    }

    public static void main(String[] args) {
        Node first = new Node();
        Node current = first;
        for (int i = 1; i < 50_000; i++) {
            current.next = new Node();
            current = current.next;
        }

        current.next = first; // Chu trình quay về đầu.
        System.out.println("Unique nodes: " + countUnique(first));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 IterativeGraphTraversalDemo.java
java IterativeGraphTraversalDemo
```

Stdout:

```text
Unique nodes: 50000
```

Ý nghĩa:

- Vòng `for` tạo 50.000 đối tượng `Node` và nối thành danh sách; cuối cùng tạo chu trình về `first`.
- `Deque` chứa các node cần xử lý và `visited` ngăn lặp qua chu trình.
- Hàm `countUnique` không gọi lại chính nó. Độ sâu call stack của **chính thuật toán traversal** không tăng tuyến tính với số node.
- Đổi lại, các object Node, `Deque` và `visited` cần bộ nhớ **heap**. Khi dữ liệu cực lớn, vẫn cần giới hạn bộ nhớ hoặc thuật toán phù hợp; tránh stack overflow không có nghĩa không thể gặp memory pressure.
- Với graph tổng quát có nhiều cạnh, cấu trúc pending có thể chứa nhiều phần tử. Phải đánh giá cả time complexity và memory complexity, không chỉ recursion depth.

### 13.1. Vì sao dùng `ArrayDeque` thay vì `Stack`?

`ArrayDeque` là lựa chọn hiện đại phổ biến khi cần ngữ nghĩa LIFO/FIFO trong Java. Có thể dùng `push`/`pop` làm stack thủ công. Nó không cho phần tử `null`, vì vậy ví dụ chỉ `push` node khác null.

Không nhầm **Java call stack** với **`Deque` object**: `Deque` là một cấu trúc dữ liệu do ứng dụng quản lý, thường trên heap, không tự tạo JVM frame cho mỗi phần tử.

## 14. Độ sâu an toàn cần được kiểm soát tại biên đầu vào

Ngay cả khi đầu vào không có cycle, một API nhận JSON/XML/cây biểu thức lồng nhau từ bên ngoài có thể gặp dữ liệu cực sâu. Nếu dùng recursion, có thể:

- Từ chối đầu vào vượt **độ sâu tối đa** được quy định.
- Chuyển sang parser/traversal dạng lặp khi dữ liệu cần hỗ trợ depth lớn.
- Giới hạn cả kích thước, số node, số cạnh và thời gian xử lý.
- Dùng cấu hình parser/framework có khả năng giới hạn nesting nếu thư viện hỗ trợ.
- Tách lỗi validation thành **exception nghiệp vụ phù hợp**, không chờ VM ném StackOverflowError.

Ví dụ: “Tối đa 64 cấp lồng nhau” là một **hợp đồng ứng dụng** được chọn có chủ đích, khác hoàn toàn “stack của JVM lúc này may mắn chịu được 64 cấp”.

### 14.1. Java 17 — giới hạn depth bằng lỗi có ý nghĩa

Tạo **`DepthLimitDemo.java`**:

```java
public class DepthLimitDemo {
    static final int MAX_DEPTH = 4;

    static int visit(int depth, int remaining) {
        if (depth > MAX_DEPTH) {
            throw new IllegalArgumentException(
                    "Vượt giới hạn độ sâu " + MAX_DEPTH);
        }
        if (remaining == 0) {
            return depth;
        }
        return visit(depth + 1, remaining - 1);
    }

    public static void main(String[] args) {
        System.out.println("Safe result: " + visit(0, 3));
        try {
            visit(0, 5);
        } catch (IllegalArgumentException e) {
            System.out.println("Rejected: " + e.getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 DepthLimitDemo.java
java DepthLimitDemo
```

Stdout:

```text
Safe result: 3
Rejected: Vượt giới hạn độ sâu 4
```

Diễn giải:

- `visit(0,3)` gọi với depth 0,1,2,3 rồi base case trả 3.
- `visit(0,5)` tiến đến depth 5; điều kiện `depth > 4` chủ động từ chối.
- Đây là **IllegalArgumentException do ứng dụng chọn**, không phải `StackOverflowError`.
- Giới hạn depth cần tính rõ từ 0 hay từ 1, và điều kiện xét `>` hay `>=` để không gặp off-by-one.
- Nếu sử dụng với dữ liệu không tin cậy, ngoài depth còn cần kiểm tra `remaining >= 0` và các invariant khác. Ví dụ cố dùng input hợp lệ về số bước để tập trung vào depth.
- Giá trị 4 trong chương trình chỉ là giới hạn minh họa, **không** khẳng định 4 là giới hạn JVM hay giới hạn an toàn chung.

### 14.2. Giới hạn depth và visited set giải quyết hai vấn đề khác nhau

| Cơ chế | Chống được điều gì? | Không tự giải quyết |
| --- | --- | --- |
| Base case + progress | Đệ quy không có đường dừng trên input hợp lệ | Dữ liệu có cycle bất ngờ, độ sâu cực lớn |
| Visited set | Chu trình/đi lại node đã gặp | Chuỗi node mới rất sâu, memory dùng cho set |
| Depth limit | Đệ quy quá sâu | Tính đúng của kết quả khi dữ liệu bị từ chối |
| Duyệt bằng `Deque` | Call stack quá sâu theo số node | Heap lớn, thuật toán có thể vô hạn nếu không có visited |
| Input validation | Trường hợp sai hợp đồng từ đầu | Bug ở recursion nội bộ nếu vẫn triển khai sai |
| `-Xss` lớn hơn | Có thể cho phép một số depth hữu hạn chạy được | Đệ quy vô hạn, side effect, cycle |

## 15. Đệ quy trong cây: độ sâu khác số node

Một cây cân bằng có thể có nhiều node nhưng độ sâu nhỏ. Một cây lệch hoàn toàn có thể có n node và độ sâu khoảng n.

```text
Cây cân bằng:                Cây lệch:
        A                     A
      /   \                    \
     B     C                    B
    / \   / \                    \
   D   E F   G                    C
                                   \
                                    D
```

Nếu recursion giữ một frame trên mỗi tầng:

- Cây cân bằng có độ sâu `O(log n)` trong trường hợp cấu trúc cân bằng lý tưởng.
- Cây lệch có depth `O(n)` và có thể gây tràn stack khi n lớn.
- Tổng số node nhiều không đủ để kết luận stack chắc tràn; phải xem **độ sâu đường đi dài nhất** và cách traversal gọi method.
- Thuật toán có thể tính toán qua nhiều nhánh nhưng **không giữ mọi nhánh trên call stack đồng thời** nếu duyệt tuần tự; tuy nhiên một nhánh rất sâu vẫn nguy hiểm.

### 15.1. Java 17 — minh họa trace vào/ra đệ quy

Tạo **`RecursionTraceDemo.java`**:

```java
public class RecursionTraceDemo {
    static void trace(int depth, int remaining) {
        System.out.println("Enter " + depth);
        if (remaining > 0) {
            trace(depth + 1, remaining - 1);
        }
        System.out.println("Exit " + depth);
    }

    public static void main(String[] args) {
        trace(0, 2);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 RecursionTraceDemo.java
java RecursionTraceDemo
```

Stdout:

```text
Enter 0
Enter 1
Enter 2
Exit 2
Exit 1
Exit 0
```

Với trace này, ba lời gọi `trace` tồn tại lồng nhau trước khi bắt đầu in `Exit`. Cách in như vậy giúp hình dung thứ tự **push** và **unwind** của call stack. Trong recursion không dừng, quá trình đi sâu không bao giờ tới các lệnh `Exit` theo đường bình thường.

## 16. Tại sao không dùng `try/catch(StackOverflowError)` làm điều kiện dừng?

Đây là một anti-pattern:

```java
// CỐ Ý SAI: không dùng stack exhaustion làm thuật toán.
static int count(Node node) {
    try {
        return 1 + count(node.next);
    } catch (StackOverflowError ignored) {
        return 0;
    }
}
```

Đoạn này **minh họa**, không phải chương trình độc lập. Vấn đề:

1. Với danh sách có chu trình, không có cách đếm đúng “số node phân biệt” bằng cách chờ tràn stack.
2. Với danh sách hữu hạn, depth giới hạn bởi tài nguyên VM, kết quả sẽ **phụ thuộc máy và thread**, không phải dữ liệu.
3. Khi gần cạn stack, xử lý error/cleanup phức tạp có thể gặp sự cố.
4. Catch có thể che bug, làm ứng dụng trả kết quả sai hoặc không nhất quán.
5. Trong recursion mà catch ở **mỗi frame**, khi unwind có thể xuất hiện nhiều điểm bắt với những phép tính tiếp theo, càng khó suy luận.
6. Stack exhaustion không đảm bảo tính nguyên tử; trước khi lỗi có thể đã có side effect.
7. Tăng `-Xss` làm đầu ra thuật toán thay đổi nếu nó dựa vào vị trí tràn.

**Giải pháp:** dừng theo dữ liệu/cấu trúc, dùng visited set, giới hạn depth, vòng lặp hoặc stack chủ động; không lấy loại Error làm “giá trị kết thúc”.

### 16.1. Có được bắt Error ở ranh giới kỹ thuật không?

Một số hệ thống hạ tầng có thể bắt `Throwable` trong **ranh giới rất hẹp** để ghi nhận/sandbox failure rồi tái ném hoặc kết thúc tác vụ. Nhưng đây là chính sách nâng cao, và không thể khẳng định VM/thread luôn ở trạng thái đủ an toàn để tiếp tục mọi việc.

Code ứng dụng thông thường nên:

- **Không** bắt `Error` rộng rồi trả response “thành công”.
- **Không** retry vô hạn cùng recursion trong handler.
- Giữ logic cleanup đơn giản, có kiểm soát, và không làm mất thông tin lỗi gốc.
- Xem `StackOverflowError` như một tín hiệu lỗi nghiêm trọng cần **sửa code hoặc giới hạn dữ liệu**.

## 17. Lỗi trong quá trình khởi tạo và `StackOverflowError`

Chủ đề này nằm trong nhóm “Error và khởi tạo”, nên cần phân biệt **đệ quy gây StackOverflowError** với **lỗi khởi tạo class**.

Trong Java, static initializer và việc khởi tạo static fields có thể chạy khi class được dùng lần đầu. Nếu logic khởi tạo vô tình kích hoạt recursion sâu (ví dụ gọi một method đệ quy không dừng), stack của thread cũng có thể bị tràn.

Tuy nhiên:

- `StackOverflowError` là lỗi liên quan đến stack, dù nó xảy ra **trong static initializer**, constructor hay method thường.
- Các quy tắc **class initialization failure** có thể tạo các biểu hiện khác như `ExceptionInInitializerError` hoặc `NoClassDefFoundError` ở những tình huống phù hợp; không được nói mọi lỗi trong static initializer đều chắc chắn bị bọc thành một lớp duy nhất.
- Một `Error` được ném trong lúc class initialization có những quy tắc lan truyền khác với exception thông thường từ initializer.
- Sau khi class khởi tạo thất bại, trạng thái class đối với các lần sử dụng tiếp theo có thể bị đánh dấu lỗi, nên việc retry trong cùng JVM không tự sửa được nguyên nhân.
- Constructor instance tự gọi lại theo **các method thông thường** có thể gây recursion; nhưng lời gọi constructor `this(...)`/`super(...)` có quy tắc compile-time riêng, và không nên đánh đồng với vô hạn method recursion.

**Điểm cần học:** xác định vị trí lỗi trên stack và **tầng phát sinh**. Nếu Error xuất hiện khi class được khởi tạo, ngoài recursion còn phải điều tra chuỗi khởi tạo và các giới hạn của JVM.

### 17.1. Đừng dựa vào retry class initialization thất bại

Nếu một static initializer đã thất bại, code dùng class sau đó không được giả định có thể “thử lại” khởi tạo như một method bình thường. Khi có lỗi do tài nguyên/đệ quy ở giai đoạn khởi tạo, thường cần sửa thiết kế khởi tạo và xử lý vòng đời class/tiến trình, chứ không chỉ bao `try/catch` và gọi lại.

### 17.2. Cẩn trọng với factory gọi qua lại

Một chuỗi như `ServiceHolder.get() → ServiceFactory.create() → ServiceHolder.get()` có thể tạo recursion gián tiếp ngay ở bước khởi tạo dependency. Đặc biệt chú ý vòng phụ thuộc giữa các constructor/factory hoặc lazy getters; việc dùng lazy initialization không tự loại bỏ vòng phụ thuộc.

## 18. Đệ quy và `equals`, `hashCode`, `toString`

Nhiều thư viện hoặc công cụ logging tự gọi `toString`; collection như `HashMap` có thể gọi `hashCode` và `equals`. Nếu hai object có liên kết hai chiều và các method ấy duyệt toàn bộ graph không có visited check, sự cố có thể bộc lộ ở chỗ **log một object**, không phải ở đoạn người viết nghĩ là đang dùng recursion.

Ví dụ:

```java
// Phản thiết kế khi graph có back-reference.
@Override
public String toString() {
    return "Parent{child=" + child + "}";
}
```

Nếu `child.toString()` lại in `parent`, đường gọi quay vòng. Cách sửa có thể là chỉ in ID, tên trường an toàn, hoặc giới hạn độ sâu biểu diễn.

Tương tự:

- `equals` không nên so sánh vô hạn qua back-reference nếu graph có cycle.
- `hashCode` nên dựa trên trường có semantics phù hợp, tránh đi hết graph hai chiều không có giới hạn.
- Auto-generated methods từ công cụ có thể không phù hợp với graph cyclic, dù nhìn như ít code.
- Java `record` có `toString/equals/hashCode` dựa trên components; nếu component graph liên kết theo vòng, vẫn phải xét recursion gián tiếp.
- Một `StackOverflowError` trong log formatter không chứng minh logger hỏng; nguồn có thể là `toString()` của object được truyền vào logger.

## 19. Depth guard có thể đặt ở đâu?

Các tầng phù hợp:

- **Parser:** giới hạn nesting level của JSON/XML/expression.
- **Graph traversal:** giới hạn depth hoặc dùng `visited`/iterative traversal.
- **Business rule:** giới hạn số cấp parent/child trong cấu trúc domain.
- **API boundary:** từ chối input quá sâu hoặc quá lớn trước khi chuyển xuống service.
- **Recursive algorithm:** chứng minh một measure giảm dần và có giới hạn.
- **Library integration:** đọc các giới hạn/cấu hình của thư viện và tránh tắt những biện pháp an toàn mà không có lý do.

Hãy chọn **cách đếm rõ ràng**. Ví dụ root có depth 0 hay depth 1? Depth 64 nghĩa là 64 edges hay 64 nodes? Một hợp đồng được ghi rõ giúp tránh lỗ hổng off-by-one.

### 19.1. Nếu chiều sâu không biết trước?

Khi người dùng có thể gửi dữ liệu rất sâu, không nên chỉ nâng một constant depth guard lên giá trị lớn vô hạn. Hãy:

1. Đánh giá liệu yêu cầu phải xử lý dữ liệu sâu đến đâu.
2. Nếu bắt buộc, chọn thuật toán lặp hoặc cấu trúc parser không dùng call stack tỷ lệ theo nesting.
3. Giới hạn số node/cạnh, thời gian chạy và bộ nhớ.
4. Nếu cần trả lỗi từ chối, dùng loại kết quả/exception nghiệp vụ có mã lỗi phù hợp.
5. Giữ monitoring cho các input biên nhưng tránh in/dump nguyên dữ liệu nhạy cảm hoặc quá lớn.

## 20. Java 17 — mutual recursion hữu hạn có điểm dừng

Không phải mọi cuộc gọi A ↔ B đều sai. Nếu có một **measure giảm** và base case, mutual recursion có thể hợp lệ.

Tạo **`MutualRecursionDemo.java`**:

```java
public class MutualRecursionDemo {
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
        System.out.println("Even 4: " + isEven(4));
        System.out.println("Odd 5: " + isOdd(5));
        System.out.println("Even 0: " + isEven(0));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 MutualRecursionDemo.java
java MutualRecursionDemo
```

Stdout:

```text
Even 4: true
Odd 5: true
Even 0: true
```

Chú ý:

- Ví dụ chỉ dùng **n không âm**; nếu n âm, measure giảm mãi xa 0 và có thể gây stack overflow.
- Trong ứng dụng thật, có thể kiểm tra `n >= 0` ở boundary rồi mới gọi method.
- Lời gọi qua lại không phải vấn đề tự thân; vấn đề là **đường gọi có khả năng dừng và depth có được kiểm soát không**.
- Nếu đầu vào là số nguyên rất lớn, dù recursion dừng về mặt toán học, vẫn có nguy cơ tràn stack do độ sâu quá lớn. Với bài toán chẵn/lẻ, `(n & 1) == 0` đơn giản và không cần recursion.

## 21. Duyệt cây/graph: cách lựa chọn theo dữ liệu

| Dữ liệu và yêu cầu | Lựa chọn hợp lý | Rủi ro còn lại |
| --- | --- | --- |
| Cây nhỏ, depth bị giới hạn | Đệ quy với base case rõ | Input vượt giới hạn nếu validation thiếu |
| Cây có thể rất lệch/sâu | Vòng lặp hoặc `Deque`/`Queue` | Heap dùng cho cấu trúc trung gian |
| Graph có cycle | Visited set, identity khi cần | Bộ nhớ và concurrency |
| Graph có cycle và rất sâu | Iterative + visited | Thời gian, số lượng node/cạnh lớn |
| Chỉ tính tổng dãy số | Vòng lặp/công thức với kiểm tra overflow | Tràn số độc lập với stack |
| JSON/XML sâu đến từ bên ngoài | Parser có depth policy; từ chối hoặc duyệt lặp | Chi phí parse/input lớn |
| Số tầng đã cố định, rất nhỏ | Recursive method đơn giản | Không tự tăng giới hạn nếu input mở rộng |
| Callback/event có khả năng gọi lại chính nó | Reentrancy guard hoặc queue công việc | Deadlock/ordering nếu guard thiết kế sai |

**Đừng đổi đệ quy sang lặp một cách máy móc rồi bỏ hết kiểm tra cycle.** Nếu input graph có chu trình, vòng lặp không có visited set vẫn có thể chạy vô hạn, chỉ là không tràn call stack theo cùng cách.

## 22. Kiểm thử đệ quy và đường lỗi

Các test cần bao phủ:

1. **Base case:** input rỗng/0/null (nếu hợp đồng cho phép).
2. **Một bước:** input rất nhỏ, kiểm tra progress.
3. **Đường bình thường:** giá trị kỳ vọng với depth thấp.
4. **Sai tiền điều kiện:** số âm, depth không hợp lệ.
5. **Cạnh giới hạn:** depth tối đa, ngay trên giới hạn.
6. **Cấu trúc có chu trình:** graph nhỏ A → B → A.
7. **Cấu trúc sâu không chu trình:** thuật toán lặp phải xử lý đúng.
8. **Không làm sai trạng thái:** nếu validation từ chối sớm, chưa phát sinh side effect không cần thiết.
9. **Concurrency (nếu có):** object graph có thể bị sửa trong lúc duyệt không?
10. **Thông báo lỗi:** failure rõ nghĩa và không lộ thông tin nhạy cảm.

### 22.1. Ví dụ JUnit 5 để kiểm tra hợp đồng

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class RecursionContractTest {
    @Test
    void factorialHasWorkingBaseCases() {
        assertEquals(1L, BoundedRecursionDemo.factorial(0));
        assertEquals(120L, BoundedRecursionDemo.factorial(5));
    }

    @Test
    void negativeInputIsRejectedBeforeRecursion() {
        assertThrows(IllegalArgumentException.class,
                () -> BoundedRecursionDemo.factorial(-1));
    }

    @Test
    void depthGuardRejectsExcessiveInput() {
        assertEquals(3, DepthLimitDemo.visit(0, 3));
        assertThrows(IllegalArgumentException.class,
                () -> DepthLimitDemo.visit(0, 5));
    }
}
```

**Đây là file test minh họa cần JUnit Jupiter và hai demo class nằm cùng package**, không phải một chương trình JDK-only độc lập. Test dựa trên **hành vi mong đợi** chứ không cố “chờ JVM tràn stack” để xác minh base case.

### 22.2. Không dùng số depth trước khi `StackOverflowError` làm assert

Số lần gọi chịu ảnh hưởng JVM, thread stack, JIT và kích thước frame. Một test kiểu “assert chắc chắn SOE sau đúng 10.000 lời gọi” sẽ giòn và khó di động. Nếu cần test chủ động gây lỗi VM, nên chạy riêng trong môi trường cô lập, có timeout/giới hạn tài nguyên và coi đó là test chẩn đoán, không phải test đơn vị cơ bản.

## 23. Những nhầm lẫn phổ biến và cách sửa

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “`StackOverflowError` là `Exception`.” | Nó thuộc `Error → VirtualMachineError`. |
| “`catch(Exception)` bắt mọi Throwable.” | Không bắt `Error`. |
| “SOE luôn là do thiếu base case.” | Có thể do recursion hữu hạn quá sâu hoặc chu trình gọi phức tạp. |
| “Có base case thì không thể tràn stack.” | Depth hợp lệ vẫn có thể vượt giới hạn VM. |
| “`-Xss` lớn hơn sửa được recursion vô hạn.” | Chỉ hoãn tràn, không tạo điều kiện dừng. |
| “Mọi JVM cho cùng số lần gọi tối đa.” | Phụ thuộc VM, kiến trúc, frame, JIT, thread và cấu hình. |
| “Đệ quy tail-call trong Java luôn tối ưu thành vòng lặp.” | Java không bảo đảm TCO chung. |
| “Không có cycle thì recursion luôn an toàn.” | Đường đi không cycle vẫn có thể rất dài. |
| “Dùng visited set sẽ hết nguy cơ SOE.” | Giải quyết cycle, không tự giải quyết depth lớn. |
| “Đổi sang vòng lặp thì có thể bỏ visited.” | Graph có cycle vẫn có thể chạy mãi. |
| “Vòng lặp không thể hết bộ nhớ.” | `Deque`/`Set` và dữ liệu trên heap vẫn dùng memory. |
| “Cứ catch StackOverflowError rồi trả 0.” | Kết quả sai và có thể khiến trạng thái không đáng tin. |
| “`OutOfMemoryError` với `StackOverflowError` giống nhau.” | Khác tài nguyên và nguyên nhân. |
| “Tràn số int tạo `StackOverflowError`.” | Tràn số là hiện tượng toán học khác. |
| “Chỉ recuse() mới có SOE.” | ToString/getter/serializer/equals/callback có thể gọi qua lại. |
| “Lỗi log StackOverflowError luôn do logger.” | Có thể do `toString()` của dữ liệu truyền vào log. |
| “Một trace dài cho biết chính xác depth.” | Trace có thể rút gọn/cấu hình giới hạn. |
| “Chạy được trong main là chạy được mọi thread pool.” | Stack cấu hình giữa các thread/môi trường có thể khác. |
| “Static initializer tràn stack giống mọi lỗi exception khởi tạo.” | Cần xét riêng Error và quy tắc class initialization failure. |
| “Chỉ cần memory heap lớn hơn.” | Heap và call stack giải quyết nhu cầu khác nhau. |
| “Đệ quy không kiểm soát là vấn đề hiệu năng thôi.” | Có thể thành lỗi VM nghiêm trọng và mất tính sẵn sàng. |

## 24. Checklist trước khi dùng đệ quy trong Java

- [ ] Tôi đã nêu **base case** rõ cho mọi loại input hợp lệ chưa?
- [ ] Tôi có một measure chứng minh lời gọi con **tiến gần base case** chưa?
- [ ] Tôi đã kiểm tra input âm, null, rỗng và giá trị rất lớn chưa?
- [ ] Tôi đã đánh giá **độ sâu tối đa** chứ không chỉ số node/tổng công việc chưa?
- [ ] Nếu input do người dùng cung cấp, đã áp giới hạn depth/nodes/size chưa?
- [ ] Nếu graph có thể có cycle, tôi có visited set hoặc cơ chế phát hiện cycle chưa?
- [ ] Nếu cần xét object identity, tôi đã tránh dựa nhầm vào `equals/hashCode` chưa?
- [ ] Với dữ liệu rất sâu, tôi có cân nhắc `Deque`/`Queue` thay recursion chưa?
- [ ] Tôi hiểu `StackOverflowError` là `Error` và `catch(Exception)` không bắt nó chưa?
- [ ] Tôi không dùng `catch(StackOverflowError)` làm điều kiện dừng thuật toán chứ?
- [ ] Tôi không mặc định Java luôn tối ưu tail recursion chưa?
- [ ] Tôi không dùng `-Xss` như giải pháp chính cho recursion vô hạn chưa?
- [ ] Tôi phân biệt `StackOverflowError` với `OutOfMemoryError` và tràn số chưa?
- [ ] Tôi đã xét các đường recursion ẩn qua `toString`, `equals`, getter và serializer chưa?
- [ ] Khi gặp trace, tôi tìm pattern frame lặp và điều kiện dừng thay vì chỉ tăng stack chưa?
- [ ] Tôi đã thử trường hợp cây lệch, graph cycle, depth sát giới hạn chưa?
- [ ] Nếu lỗi xảy ra lúc khởi tạo class, tôi đã phân biệt failure class initialization chưa?
- [ ] Tôi đã đảm bảo lời giải còn đúng khi input/môi trường mở rộng chưa?

## 25. Tổng kết

`StackOverflowError` là một **`VirtualMachineError` unchecked** liên quan đến giới hạn call stack của thread. Đệ quy không có base case, không tiến tới base case, gọi vòng qua nhiều method hoặc duyệt graph có chu trình đều có thể gây lỗi; nhưng **đệ quy hữu hạn quá sâu** cũng có thể tràn stack. Để phòng tránh, cần **điều kiện dừng có thể chứng minh, bước tiến, giới hạn độ sâu**, và chọn **thuật toán lặp với stack/queue chủ động** khi dữ liệu có thể sâu. Visited set xử lý chu trình nhưng không loại bỏ mọi rủi ro depth. `-Xss` có thể thay đổi ngưỡng tài nguyên chứ không chữa recursion vô hạn, còn `catch(StackOverflowError)` không phải phương pháp khôi phục thông thường. Thiết kế thuật toán đúng và giới hạn đầu vào mới là cách bảo vệ chương trình đáng tin cậy.