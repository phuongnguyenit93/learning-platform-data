# Giới hạn giữa ngoại lệ đồng bộ và ngoại lệ bất đồng bộ của JVM

Khi nói một ngoại lệ Java là *synchronous* (đồng bộ) hoặc *asynchronous* (bất đồng bộ) **theo nghĩa của Java Virtual Machine (JVM)**, ta đang nói đến **thời điểm và nguyên nhân mà ngoại lệ có thể được ném trong luồng thực thi hiện tại**. Đây là phân loại về *cơ chế phát sinh ngoại lệ*, không phải phân loại về cách viết chương trình đa luồng, API bất đồng bộ, hay checked/unchecked exception.

Trong Java SE 21, Java Language Specification (JLS) §11.1.2–§11.1.3 và Java Virtual Machine Specification (JVMS) §2.10 xác định ranh giới này:

- **Ngoại lệ đồng bộ** gắn với một hành động cụ thể của thread đang thực thi, tại vị trí mà đặc tả cho phép hành động đó ném ngoại lệ. Ví dụ: chia số nguyên cho 0, truy cập chỉ số mảng ngoài phạm vi, thực thi câu lệnh `throw` hoặc gặp lỗi khi liên kết lớp.
- **Ngoại lệ bất đồng bộ của JVM** có thể phát sinh tại một điểm không được gắn trực tiếp với phép toán cụ thể trong mã ứng dụng, do JVM gặp lỗi nội bộ hoặc giới hạn tài nguyên nghiêm trọng. Theo Java SE 21, ngoại lệ bất đồng bộ loại này thuộc nhánh `VirtualMachineError`; việc phát sinh rất hiếm và JVM được phép trì hoãn trong một khoảng thực thi nhỏ nhưng hữu hạn.
- **Cả hai vẫn là ngoại lệ Java chính xác (*precise exceptions*)**: khi quyền điều khiển chuyển sang bộ xử lý ngoại lệ, các hiệu ứng nhìn thấy được phải phù hợp với một điểm ném nhất quán trên đường thực thi.

Ví dụ dễ gây nhầm: một tác vụ chạy bằng `CompletableFuture.supplyAsync(...)` rồi ném `IllegalStateException` **không vì thế mà trở thành “JVM asynchronous exception”**. Đây là lỗi thông thường được ném trong thread thực thi tác vụ; kết quả thất bại của tác vụ chỉ được chuyển cho thread khác qua API bất đồng bộ.

## 1. “Đồng bộ” ở đây nghĩa là gì?

Theo JLS §11.1.2, có bốn nhóm nguyên nhân khiến ngoại lệ được ném:

| Nguyên nhân | Ví dụ | Cách hiểu |
| --- | --- | --- |
| Câu lệnh `throw` | `throw new IllegalArgumentException("bad input");` | Chương trình chủ động ném ngoại lệ tại câu lệnh được thực thi. |
| Câu lệnh `assert` được bật và điều kiện sai | `assert value > 0;`, khi chạy với `-ea` và điều kiện sai | JVM ném `AssertionError` tại việc thực thi câu lệnh `assert`. Nếu assertion bị tắt, điều kiện không được đánh giá. |
| JVM phát hiện tình huống bất thường **đồng bộ** | `x / zero` với phép chia nguyên và mẫu số 0; `array[index]` sai giới hạn; lỗi loading/linking | Lỗi xảy ra ở thao tác có khả năng phát sinh ngoại lệ được ngôn ngữ hoặc JVM xác định. Giới hạn tài nguyên cũng có thể được phát hiện đồng bộ. |
| JVM phát sinh ngoại lệ **bất đồng bộ** | Lỗi nội bộ hoặc giới hạn tài nguyên JVM được phát hiện ngoài thời điểm gắn với một phép toán cụ thể | Trường hợp hiếm; theo Java SE 21, loại ngoại lệ là lớp con `VirtualMachineError`. |

Trong hàng thứ nhất, `throw` là hành vi chủ động của mã Java. Hàng thứ ba bao gồm những ngoại lệ được JVM phát hiện khi thực hiện mã; chúng **không có nghĩa** rằng JVM có thể tự ném chúng bất cứ lúc nào. Ví dụ, `ArithmeticException` do chia số nguyên cho 0 gắn với phép chia cụ thể.

Một lỗi hệ thống có thể khiến thao tác I/O bị thất bại rồi API ném `IOException` tại điểm thực hiện thao tác. Việc thiết bị I/O hoạt động ở bên ngoài JVM không tự biến `IOException` thành ngoại lệ bất đồng bộ theo JLS. Cũng vậy, lỗi đọc kết quả `Future.get()` không tự thuộc loại JVM asynchronous exception.

**Đồng bộ không đồng nghĩa checked; bất đồng bộ không đồng nghĩa unchecked “vì chạy trên thread khác”.** Checked/unchecked là phân loại dựa trên cây lớp ngoại lệ và quy tắc `catch`/`throws` lúc biên dịch, tách biệt với thời điểm phát sinh. Trong Java SE 21, ngoại lệ bất đồng bộ của JVM thuộc `VirtualMachineError` (nhánh `Error`, unchecked), nhưng phần lớn unchecked exceptions khác như `NullPointerException` vẫn phát sinh đồng bộ.

## 2. Ranh giới đặc tả: những gì JVM được phép làm

### Ngoại lệ đồng bộ bị ràng buộc bởi điểm phát sinh

JLS §11.1.2 xác định ngoại lệ đồng bộ không được ném tại vị trí tùy tiện. Chúng được phát sinh ở nơi mà việc đánh giá biểu thức hoặc thực thi câu lệnh có thể có kết quả đó theo đặc tả.

Ví dụ:

```java
int[] items = {4, 8};
int value = items[2]; // ArrayIndexOutOfBoundsException tại phép truy cập sai
```

Đây là đoạn minh họa trong thân phương thức. Truy cập `items[2]` là thao tác làm phát sinh lỗi; không nên hình dung lỗi này “rơi từ ngoài vào” trong lúc một lệnh bất kỳ đang chạy.

Ngoại lệ có thể được ném trực tiếp bằng `throw` hoặc do JVM tạo khi thực hiện opcode tương ứng. Ở mức bytecode, lệnh `athrow` thực hiện việc ném một đối tượng thuộc `Throwable`; nhưng **không phải mọi ngoại lệ đồng bộ đều đòi hỏi có lệnh `athrow` tường minh trong mã nguồn**.

Các lỗi loading, linking, initializing (như một số `LinkageError`) có thể phát sinh khi JVM phải thực hiện hoạt động tương ứng. Những lỗi đó vẫn tuân theo quy tắc điểm phát sinh đã được xác định cho hành động liên quan.

### Ngoại lệ bất đồng bộ không bị gắn với một phép toán nguồn cụ thể

JLS §11.1.3 định nghĩa ngoại lệ bất đồng bộ là ngoại lệ **có khả năng xảy ra ở bất kỳ điểm nào** trong quá trình thực thi chương trình, khi JVM gặp lỗi nội bộ hoặc giới hạn tài nguyên khiến nó không thể duy trì ngữ nghĩa Java. Theo đặc tả Java SE 21, lớp ngoại lệ được ném thuộc nhánh `VirtualMachineError`.

Cụm “có khả năng ở bất kỳ điểm nào” cần hiểu đúng:

1. Không có nghĩa JVM buộc phải ném lỗi ngay tức khắc ở một lệnh nguồn bất kỳ do ứng dụng chọn.
2. Đặc tả **cho phép một lượng thực thi nhỏ nhưng hữu hạn** trước khi ném ngoại lệ bất đồng bộ. Cách phát hiện và điểm kiểm tra cụ thể là chi tiết triển khai.
3. JVM có thể chèn các điểm kiểm tra phù hợp với mã đã tối ưu. Đặc tả nêu việc kiểm tra tại những chỉ thị chuyển luồng điều khiển như một **ví dụ triển khai**, không phải lời bảo đảm rằng mọi JVM chỉ kiểm tra tại những chỉ thị đó.
4. Dù thời điểm phát hiện linh hoạt hơn, ngoại lệ vẫn phải giữ **tính chính xác của trạng thái quan sát được** tại điểm chuyển quyền điều khiển.

Ngoại lệ loại này rất hiếm; không nên xây chương trình dựa vào giả định nó sẽ xuất hiện đều đặn, có thể kích hoạt tại một dòng mã cố định hoặc luôn có thể phục hồi.

## 3. `VirtualMachineError`: cùng một lớp lỗi có thể có hai cơ chế xuất hiện

`VirtualMachineError` là lớp con của `Error`, được dùng cho các tình huống JVM bị hỏng hoặc hết tài nguyên để tiếp tục thực thi đúng. Những lớp con thường gặp cần biết gồm `OutOfMemoryError`, `StackOverflowError`, `InternalError` và `UnknownError`.

**Không được kết luận chỉ từ tên lớp rằng một ngoại lệ cụ thể chắc chắn là bất đồng bộ.** JLS §11.1.3 chỉ rõ:

- `StackOverflowError` có thể được ném **đồng bộ** khi thực hiện lời gọi phương thức làm tràn stack; nó cũng có thể xuất hiện **bất đồng bộ** liên quan việc chạy phương thức `native` hoặc giới hạn tài nguyên JVM.
- `OutOfMemoryError` có thể xuất hiện **đồng bộ** khi tạo đối tượng, tạo mảng, khởi tạo lớp, boxing, v.v.; nó cũng có thể xuất hiện **bất đồng bộ**.
- Các trường hợp lỗi JVM nội bộ hoặc giới hạn tài nguyên được xử lý dưới quy tắc của `VirtualMachineError`. Loại thông tin như tên lớp hoặc message **không nhất thiết chỉ ra chính xác thời điểm phát hiện lỗi**.

Ví dụ cách suy luận phù hợp:

```text
new int[veryLargeLength]
  └─ có thể thất bại khi cấp phát mảng
     └─ OutOfMemoryError (trường hợp đồng bộ tại phép cấp phát)

Một giới hạn tài nguyên JVM nghiêm trọng được phát hiện ngoài điểm
gắn với phép toán nguồn hiện tại
  └─ JVM có thể ném một lớp con VirtualMachineError bất đồng bộ
```

Sơ đồ trên chỉ minh họa hai cơ chế; **không phải kịch bản để ép JVM hết bộ nhớ**. Mức heap, heap dump, hoạt động GC và chi tiết cảnh báo lỗi thay đổi theo JVM/cấu hình. Việc cố tạo `OutOfMemoryError` hoặc `StackOverflowError` để “kiểm thử async exception” không chứng minh cơ chế bất đồng bộ và có thể làm tiến trình mất ổn định.

## 4. Quy tắc *precise exception* áp dụng cho cả hai loại

JLS §11.3 khẳng định **mọi ngoại lệ, đồng bộ lẫn bất đồng bộ, đều precise**. Tại thời điểm chuyển quyền điều khiển:

- Hiệu ứng của những câu lệnh và biểu thức được hoàn tất **trước điểm ném** phải được phản ánh như đã xảy ra.
- Những câu lệnh, biểu thức hoặc phần của chúng nằm **sau điểm ném** không được tạo ra hiệu ứng quan sát được như thể chúng đã được thực thi.
- JVM có thể thực thi suy đoán (*speculative execution*) để tối ưu hiệu năng nhưng phải ngăn các hiệu ứng suy đoán sai thứ tự xuất hiện trong trạng thái chương trình mà ngôn ngữ bảo đảm.

Quy tắc này nói về tính nhất quán của **đường thực thi và trạng thái quan sát được tại điểm ném**. Nó không hứa rằng toàn bộ tiến trình sẽ không bao giờ ngừng đột ngột, rằng mọi hiệu ứng I/O bên ngoài đều có thể hoàn tác, hay rằng chương trình có thể bắt và phục hồi khỏi mọi `VirtualMachineError`.

Trong `try-catch`, nếu một ngoại lệ được ném, các phần còn lại trên đường bình thường của `try` sẽ bị bỏ qua; quyền điều khiển đi đến bộ xử lý phù hợp gần nhất ở ngữ cảnh gọi hiện tại. Java không tiếp tục chạy ngay tại phép toán đã gây lỗi sau khi `catch` được thực thi.

### Ví dụ Java 17+: quan sát điểm ném và truyền ngoại lệ

Lưu thành `ExceptionBoundaryDemo.java`:

```java
public class ExceptionBoundaryDemo {
    static int divideByZero() {
        System.out.println("inside: before division");
        int denominator = 0;
        int result = 12 / denominator;
        System.out.println("inside: after division");
        return result;
    }

    public static void main(String[] args) {
        try {
            try {
                System.out.println("caller: before call");
                divideByZero();
                System.out.println("caller: after call");
            } finally {
                System.out.println("finally: cleanup");
            }
        } catch (ArithmeticException ex) {
            System.out.println("caught: " + ex.getClass().getSimpleName());
        }
        System.out.println("caller: continue");
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 ExceptionBoundaryDemo.java
java ExceptionBoundaryDemo
```

Kết quả xác định:

```text
caller: before call
inside: before division
finally: cleanup
caught: ArithmeticException
caller: continue
```

Điều cần quan sát: phép chia `12 / denominator` với `denominator = 0` làm JVM ném `ArithmeticException` **đồng bộ tại phép chia**. Không có dòng `inside: after division` hay `caller: after call`. Khối `finally` chạy trong quá trình truyền ngoại lệ; `catch` nhận đúng kiểu và cho phép `main` tiếp tục.

Đây là ví dụ về **ngoại lệ đồng bộ và tính chính xác của chuyển quyền điều khiển**. Không thể chỉ sửa câu lệnh trên thành `throw new OutOfMemoryError(...)` rồi gọi đó là minh họa ngoại lệ bất đồng bộ: câu lệnh `throw` tường minh luôn là một điểm ném do chương trình quyết định.

## 5. “Bất đồng bộ” trong thư viện lập trình không đồng nghĩa “ngoại lệ bất đồng bộ của JVM”

Cùng một từ *asynchronous* được dùng cho hai vấn đề khác nhau:

| Tình huống | Có phải ngoại lệ bất đồng bộ của JVM theo JLS §11.1.3? | Giải thích |
| --- | --- | --- |
| `CompletableFuture.supplyAsync(...)` chạy hàm rồi hàm `throw` | **Không**, chỉ vì tác vụ chạy bất đồng bộ. | Câu lệnh `throw` nằm trong thread thực thi tác vụ; API ghi nhận kết quả thất bại của tác vụ. |
| `future.join()` thấy một tác vụ đã thất bại | **Không**, chỉ vì `join` ném `CompletionException`. | Lời gọi `join` báo lỗi đã được lưu; nguyên nhân thường nằm ở `getCause()`. |
| `Future.get()` ném `ExecutionException` vì tác vụ thất bại | **Không**, chỉ vì tác vụ chạy thread khác. | Lỗi được bọc và báo tại thao tác lấy kết quả. |
| Thread khác gọi `interrupt()` vào thread đang `sleep()` | **Không**. | Cơ chế ngắt thread tác động đến trạng thái interrupt và những API có quy tắc phản ứng riêng. |
| `Thread.sleep()` ném `InterruptedException` | **Không** theo nghĩa ngoại lệ bất đồng bộ của JVM. | Ngoại lệ được ném theo hợp đồng của thao tác `sleep` khi có tín hiệu interrupt. |
| JVM phát hiện lỗi tài nguyên nội bộ và ném `VirtualMachineError` tại điểm không gắn với phép toán nguồn cụ thể | **Có thể**. | Đây mới là tình huống thuộc định nghĩa bất đồng bộ theo JLS. |

Điều này vẫn đúng nếu chương trình dùng platform thread, virtual thread, `ExecutorService`, callback hay reactive pipeline: **mô hình tổ chức tác vụ không quyết định phân loại của cơ chế ném ngoại lệ**.

### Ví dụ Java 17+: một tác vụ bất đồng bộ thất bại

Lưu thành `FutureFailureDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class FutureFailureDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> task = CompletableFuture.supplyAsync(() -> {
            throw new IllegalStateException("worker failed");
        });

        try {
            task.join();
        } catch (CompletionException ex) {
            Throwable original = ex.getCause();
            System.out.println("wrapper=" + ex.getClass().getSimpleName());
            System.out.println("cause=" + original.getClass().getSimpleName());
            System.out.println("message=" + original.getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 FutureFailureDemo.java
java FutureFailureDemo
```

Kết quả:

```text
wrapper=CompletionException
cause=IllegalStateException
message=worker failed
```

`CompletableFuture.supplyAsync` đưa tác vụ tới executor mặc định; ví dụ chỉ in từ thread chính sau khi `join()` quan sát hoàn tất của tác vụ nên **thứ tự đầu ra là xác định**. `IllegalStateException` bắt nguồn từ một câu lệnh `throw` thông thường trong tác vụ. `CompletionException` là cách API truyền thông tin thất bại đến nơi gọi `join`, không phải dấu hiệu JVM vừa ném một ngoại lệ bất đồng bộ theo JLS.

Nếu sử dụng `get()` thay `join()`, chương trình phải xử lý hợp đồng checked exceptions của `get()` (đáng chú ý `InterruptedException` và `ExecutionException`). Điều này vẫn là cơ chế tương tác API, không thay đổi định nghĩa lỗi bất đồng bộ của JVM.

## 6. `Thread.interrupt()`: yêu cầu hợp tác, không phải “ném ngoại lệ vào bất cứ đâu”

`interrupt()` gửi tín hiệu gián đoạn cho thread đích. Tác động cụ thể tùy trạng thái thread và API đang thực hiện:

- Nếu thread đang `sleep`, `wait` hoặc `join` theo API chuẩn, một `InterruptedException` có thể được ném từ **chính thao tác chờ**; trạng thái interrupt được xóa khi ngoại lệ được ném trong các trường hợp đó.
- Nếu thread đang làm phép toán tính toán thuần Java không kiểm tra trạng thái, `interrupt()` không tự động ném `InterruptedException` vào một dòng tính toán bất kỳ. Cờ interrupt có thể được quan sát bằng `isInterrupted()`, hoặc thread có thể hợp tác kết thúc.
- Những API I/O và thư viện đồng thời khác có hợp đồng phản ứng riêng: đóng channel, trả sớm, ném loại ngoại lệ khác hoặc không phản ứng ngay. Đọc Javadoc của thao tác cụ thể.

Lưu thành `InterruptBoundaryDemo.java`:

```java
public class InterruptBoundaryDemo {
    public static void main(String[] args) {
        Thread.currentThread().interrupt();

        try {
            Thread.sleep(10);
            System.out.println("sleep completed");
        } catch (InterruptedException ex) {
            System.out.println("caught=" + ex.getClass().getSimpleName());
            System.out.println("flag after catch="
                    + Thread.currentThread().isInterrupted());

            Thread.currentThread().interrupt();
        }

        System.out.println("flag restored="
                + Thread.currentThread().isInterrupted());
    }
}
```

```bash
javac -encoding UTF-8 InterruptBoundaryDemo.java
java InterruptBoundaryDemo
```

Kết quả:

```text
caught=InterruptedException
flag after catch=false
flag restored=true
```

Ví dụ gọi `interrupt()` trên thread hiện tại **trước** khi thực hiện `sleep()` nên không có phụ thuộc vào thứ tự lập lịch giữa hai thread. Theo hợp đồng `Thread.sleep`, khi thread đã bị interrupt, `sleep` ném `InterruptedException` và xóa trạng thái interrupt; `catch` đặt lại cờ để tầng gọi biết có yêu cầu hủy tác vụ. Đây là một cách xử lý phổ biến nếu phương thức không thể khai báo tiếp `throws InterruptedException`, nhưng code thực tế còn phải quyết định có dừng công việc hiện tại hay không.

Không dùng `interrupt()` như cách “thử phát sinh asynchronous JVM exception”. Cơ chế interrupt là cơ chế điều phối/hủy tác vụ có hợp đồng Java API riêng.

## 7. Giới hạn lịch sử của `Thread.stop()`

Các tài liệu JVM cũ từng mô tả `Thread.stop()` có thể gây `ThreadDeath` ở thread khác, một trường hợp ném ngoại lệ bất đồng bộ. **Không áp dụng hành vi lịch sử đó như phương pháp thực hành trong Java SE 21**:

- `Thread.stop()` đã bị deprecated từ lâu vì có thể làm thread thoát trong trạng thái dữ liệu chưa nhất quán, giải phóng monitor ngoài ý muốn.
- Trong JDK 21, API `Thread.stop()` luôn ném `UnsupportedOperationException` **ở thread gọi**, thay vì dừng thread đích bằng `ThreadDeath`. Javadoc ghi phương thức này deprecated for removal.
- Cách hủy công việc nên dựa trên trạng thái hủy do chương trình quản lý, `interrupt()`, hoặc cơ chế hủy ở `Future`/executor với hợp đồng phù hợp.

Vì vậy, **không dùng `Thread.stop()` trong demo, bài kiểm thử hoặc mã triển khai** để tạo ngoại lệ bất đồng bộ. Nếu đọc tài liệu JVM rất cũ, cần xem rõ phiên bản trước khi áp dụng ví dụ của nó. Nên dùng JLS/JVMS của cùng phiên bản Java khi đối chiếu các khẳng định về trường hợp hiếm này.

## 8. Khi ngoại lệ được ném, JVM xử lý ra sao?

Dù phát sinh đồng bộ hay bất đồng bộ, sau khi có một đối tượng ngoại lệ, quy tắc ném và truyền ngoại lệ tuân theo hệ thống xử lý chung:

1. **Tìm `catch` gần nhất có thể xử lý kiểu ngoại lệ.** Một `catch (Exception ex)` sẽ không bắt `VirtualMachineError` vì nhánh `Error` không kế thừa `Exception`.
2. **Hoàn tất đột ngột các câu lệnh và lời gọi đang mở.** Những bước trên đường chạy bình thường sau điểm ném không được tiếp tục tự động.
3. **Thực hiện `finally` phù hợp trong quá trình tháo stack** nếu luồng thực thi còn cho phép; nếu chính `finally` ném ngoại lệ khác, lý do mới có thể thay thế lý do cũ.
4. **Giải phóng monitor** khi một khối `synchronized` hoặc lời gọi synchronized kết thúc đột ngột. Việc giải phóng monitor không có nghĩa các thay đổi dữ liệu trước đó được tự động rollback.
5. **Nếu không có `catch` phù hợp**, ngoại lệ không được bắt dẫn đến việc kết thúc thread theo cơ chế xử lý ngoại lệ chưa bắt của Java.

Có giới hạn thực tế quan trọng: một lỗi tài nguyên trầm trọng có thể khiến JVM không còn đủ tài nguyên để ghi log, cấp phát đối tượng mới hoặc thực hiện đường phục hồi mong muốn. Nếu toàn bộ tiến trình bị hệ điều hành cưỡng bức chấm dứt, đó không phải quá trình ném ngoại lệ Java theo nghĩa thông thường; không có bảo đảm rằng `finally` hay uncaught exception handler sẽ được thực thi.

Tuy `catch (Throwable ex)` có thể bắt một `VirtualMachineError` nếu lỗi được JVM ném và đi tới `catch`, **không nên bắt toàn bộ `Throwable` rồi giả định chương trình đủ an toàn để tiếp tục**. Lựa chọn xử lý phù hợp nhất thường là ghi nhận sự cố bằng cơ chế giám sát và để quá trình phục hồi ở cấp dịch vụ/tiến trình đảm nhiệm, tùy yêu cầu hệ thống.

## 9. Liên hệ tới tối ưu hóa JVM và việc quan sát lỗi

JLS cho phép độ trễ nhỏ và hữu hạn khi phát sinh ngoại lệ bất đồng bộ nhằm tạo không gian cho JIT tối ưu hóa. Nếu bất kỳ phép toán nào cũng phải được coi là điểm có thể bị chen lỗi một cách tức thời, nhiều phép biến đổi mã hợp lệ sẽ bị hạn chế. Với cơ chế phát hiện được phép trì hoãn, trình tạo mã có thể đặt điểm kiểm tra phù hợp mà vẫn tuân thủ ngữ nghĩa ngôn ngữ và giới hạn quan sát.

Tuy nhiên, **không được lấy các khái niệm triển khai như safepoint, polling hoặc trình tự bytecode làm lời cam kết bất biến cho mọi JVM**. Các chi tiết này phụ thuộc phiên bản và cách hiện thực JVM. Điều người lập trình có thể dựa vào là các bảo đảm của đặc tả về lý do ném, giới hạn độ trễ được phép và tính precise khi ngoại lệ thực sự chuyển quyền điều khiển.

Để phân tích log thực tế:

- Tìm **kiểu ngoại lệ, cause chain, suppressed exceptions và stack trace**. Đừng suy ra sync/async chỉ từ tên `OutOfMemoryError`.
- Xác định thao tác nào vừa được thực hiện: cấp phát mảng/đối tượng, gọi phương thức sâu, nạp lớp, chờ I/O, lấy kết quả `Future`, hay chạy callback.
- Với lỗi tài nguyên, kiểm tra metrics, heap/GC logs và cấu hình giới hạn tài nguyên theo hệ thống. Stack trace không luôn đủ để chỉ ra nguyên nhân căn bản.
- Phân biệt một **lỗi trong tác vụ bất đồng bộ** do API ghi nhận với một **lỗi bất đồng bộ của JVM** theo JLS. Cách sửa khác nhau hoàn toàn.

## 10. Câu hỏi tự kiểm tra

**1.** `new int[n]` ném `OutOfMemoryError` khi cấp phát có nhất thiết là JVM asynchronous exception?  
**Không.** Đây có thể là lỗi tài nguyên **đồng bộ** tại thao tác cấp phát được chỉ định. `OutOfMemoryError` cũng có thể xuất hiện bất đồng bộ trong điều kiện khác.

**2.** Một `CompletableFuture` thất bại trên thread khác là JVM asynchronous exception?  
**Không.** “Async” mô tả cách thực thi tác vụ. Ngoại lệ được ném trong tác vụ tuân theo cơ chế thông thường của thread đó; API cung cấp cách quan sát kết quả thất bại từ thread gọi.

**3.** `interrupt()` bảo đảm làm thread đích lập tức ném `InterruptedException` tại bất kỳ câu lệnh nào?  
**Không.** Thread nhận tín hiệu interrupt và mỗi API phản ứng theo hợp đồng riêng. Các thao tác như `sleep` có thể ném ngoại lệ tại điểm chờ cụ thể.

**4.** Mọi `VirtualMachineError` đều bất đồng bộ?  
**Không.** `StackOverflowError` và `OutOfMemoryError` có thể phát sinh đồng bộ hoặc bất đồng bộ.

**5.** JVM asynchronous exception có được ném mà bỏ qua tính nhất quán trạng thái chương trình không?  
**Không.** Cả ngoại lệ đồng bộ và bất đồng bộ đều precise theo JLS §11.3, dù điểm phát sinh của loại bất đồng bộ có độ linh hoạt và độ trễ được phép.

**6.** Bắt `Throwable` có thể bảo đảm chương trình phục hồi mọi lỗi JVM?  
**Không.** Việc bắt được đối tượng ngoại lệ không bảo đảm tài nguyên, trạng thái hoặc chính tiến trình còn khả năng phục hồi. Tiến trình cũng có thể dừng mà không đi qua cơ chế ném ngoại lệ Java.

**7.** Trong Java SE 21, có nên dùng `Thread.stop()` để thử ném `ThreadDeath` bất đồng bộ?  
**Không.** `Thread.stop()` của JDK 21 luôn ném `UnsupportedOperationException` và không phải cơ chế hủy tác vụ được hỗ trợ.

## Tham khảo chuẩn

- [JLS Java SE 21 — §11.1.2 The Causes of Exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.1.2).
- [JLS Java SE 21 — §11.1.3 Asynchronous Exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.1.3).
- [JLS Java SE 21 — §11.3 Run-Time Handling of an Exception, precise exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.3).
- [JVMS Java SE 21 — §2.10 Exceptions](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.10).
- [JDK 21 — `Thread.stop()`, `Thread.interrupt()` và `Thread.sleep()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html).
- [JDK 21 — `CompletableFuture`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html).

**Ghi nhớ:** Phân loại đồng bộ/bất đồng bộ của JVM dựa vào **mối liên hệ giữa điểm ném và hành động đang thực thi**, không dựa trên tên API có chữ “async”. Ngoại lệ đồng bộ gắn với điểm được đặc tả; ngoại lệ bất đồng bộ của JVM là trường hợp hiếm thuộc `VirtualMachineError` và có thể được phát hiện với độ trễ nhỏ, hữu hạn. Cả hai vẫn phải tuân thủ quy tắc ngoại lệ *precise* khi chuyển quyền điều khiển.
