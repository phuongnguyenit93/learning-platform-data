# Vì sao bắt `Throwable` hoặc `Error` cần một ranh giới và mục đích rõ ràng trong Java

Trong Java, **bắt được một ngoại lệ không có nghĩa là có thể khôi phục an toàn**. Sự khác biệt này đặc biệt quan trọng khi viết `catch (Throwable)` hoặc `catch (Error)`: hai lựa chọn ấy mở rộng phạm vi bắt tới những tình trạng nghiêm trọng như lỗi bộ nhớ, lỗi liên kết lớp và các lỗi bất biến, vốn thường **không nên được xử lý như một lỗi nghiệp vụ bình thường**.

Một ví dụ có rủi ro cao:

~~~java
// Anti-pattern: không áp dụng cho hệ thống thật.
try {
    processRequest();
} catch (Throwable failure) {
    return defaultResponse();
}
~~~

Đoạn trên chỉ là **mã minh họa**; cần có `processRequest()` và `defaultResponse()` trong ngữ cảnh thực tế. Vấn đề là nó gộp cả `IOException`, `NullPointerException`, `OutOfMemoryError`, `NoClassDefFoundError`, `AssertionError` và nhiều loại khác vào cùng một “kết quả dự phòng” rồi giả vờ hệ thống còn đáng tin. Một tác vụ có thể đã thực hiện được một phần, tài nguyên có thể bị cạn, mã chương trình có thể không tương thích với runtime. Trả về một kết quả bình thường trong trường hợp đó dễ che giấu lỗi hệ thống, làm lặp giao dịch hoặc gây mất dữ liệu.

Nguyên tắc thực hành:

> **Chỉ bắt ở nơi bạn xác định được ranh giới công việc, mục tiêu xử lý và điều kiện để hệ thống tiếp tục.** Với `Error` hoặc `Throwable` rộng, mục đích thường nên là quan sát tối thiểu, cleanup hoặc truyền lỗi lên ranh giới quản lý phù hợp — không phải nuốt lỗi và xem như thành công.

Bài này làm rõ khi nào có thể dùng `catch (Error)` hay `catch (Throwable)`, khi nào nên dùng `catch (Exception)` hoặc bắt loại cụ thể, cách thiết kế ranh giới cho worker/plugin/test, cách giữ lỗi gốc khi cleanup thất bại, và cách nhận diện những tình huống phải ngừng hoặc tái khởi động thành phần. Các chương trình minh họa sử dụng **Java 17+**, thử nghiệm bằng `AssertionError` có kiểm soát, **không cố tạo lỗi cạn bộ nhớ hoặc cạn stack thật**.

## 1. Vì sao phân cấp kiểu quyết định hành vi của `catch`?

Cấu trúc rút gọn:

~~~text
java.lang.Throwable
├── java.lang.Exception
│   ├── IOException
│   ├── SQLException
│   └── java.lang.RuntimeException
│       ├── IllegalArgumentException
│       ├── IllegalStateException
│       └── NullPointerException
└── java.lang.Error
    ├── VirtualMachineError
    │   ├── OutOfMemoryError
    │   └── StackOverflowError
    ├── LinkageError
    │   ├── NoClassDefFoundError
    │   ├── NoSuchMethodError
    │   └── ExceptionInInitializerError
    ├── AssertionError
    └── ThreadDeath
~~~

Các kiểu trong sơ đồ có **quan hệ kế thừa**, không phải mức độ ưu tiên theo hàng ngang. Một `catch` khớp khi loại runtime của đối tượng ném là lớp đó hoặc subtype thích hợp.

| Nhánh `catch` | Bắt được những loại nào? | Điểm cần nhớ |
| --- | --- | --- |
| `catch (IOException ex)` | `IOException` và subtype | Phù hợp nếu có chính sách khôi phục lỗi I/O |
| `catch (RuntimeException ex)` | Các subtype `RuntimeException` | Không bắt `Error` |
| `catch (Exception ex)` | `Exception` và subtype, gồm checked và runtime exceptions | Không bắt `Error` |
| `catch (Error err)` | `Error` và subtype | Bắt lỗi có thể nghiêm trọng ngoài phạm vi nghiệp vụ |
| `catch (Throwable t)` | Cả `Exception` lẫn `Error` | Phạm vi rộng nhất trong hai nhánh chính |
| Không bắt | Lỗi lan theo stack đến handler phù hợp hoặc cơ chế uncaught | Không tự đồng nghĩa với việc JVM chết ngay |

**`Error` là unchecked**: compiler không buộc phương thức ném nó phải khai báo `throws Error`. “Unchecked” chỉ nói về kiểm tra tại compile time, **không** có nghĩa nó nhẹ, không nguy hiểm hoặc có thể bỏ qua.

Điểm quan trọng thứ hai: `Error` **không phải subtype của `Exception`**, nên một `catch (Exception)` được viết ở ranh giới request thường chủ động để các tình trạng `Error` thoát khỏi cơ chế xử lý lỗi ứng dụng thông thường.

## 2. Phân biệt ba mục tiêu: xử lý, quan sát, và giới hạn hư hại

Từ “bắt lỗi” thường che đi ba hoạt động khác nhau.

### 2.1. Xử lý/phục hồi (handle/recover)

Bạn biết **nguyên nhân đủ cụ thể**, biết **trạng thái tác vụ sau lỗi**, và có **đường phục hồi đúng hợp đồng**. Ví dụ:

~~~java
// Đoạn minh họa trong một phương thức có readFromPrimary/Backup.
try {
    return readFromPrimary();
} catch (java.io.IOException ex) {
    return readFromBackup();
}
~~~

Đường phục hồi có ý nghĩa khi dữ liệu dự phòng hợp lệ và việc dùng dự phòng được cho phép. Đây không phải ví dụ biên dịch độc lập, vì hai phương thức đọc cần được định nghĩa. Nếu `readFromBackup()` cũng ném checked `IOException`, phương thức chứa đoạn mã phải xử lý/khai báo nó.

### 2.2. Quan sát/ghi nhận (observe)

Bạn **chưa chắc sửa được lỗi**, nhưng muốn ghi nhận nguyên nhân, tên tác vụ hoặc thông tin chẩn đoán. Một boundary quản lý tác vụ có thể ghi nhận `Throwable` rồi **ném lại**, cho hệ thống quản lý quyết định có tiếp tục không.

~~~java
// Minh họa ranh giới quan sát có chủ đích.
try {
    runTask();
} catch (Error err) {
    minimalFailureSignal(err);
    throw err;
}
~~~

Đoạn trên không độc lập; hai hàm phụ thuộc ứng dụng. Chính sách “ghi nhận tối thiểu rồi ném lại” **khác** với `return success`.

### 2.3. Giới hạn hư hại (contain/isolate)

Một hệ thống thử nghiệm plugin, test runner hoặc supervisor có thể cần giữ cho **đơn vị quản lý bên ngoài** còn vận hành khi một **đơn vị con đã được cô lập** thất bại. Tuy nhiên, điều này chỉ có căn cứ nếu có kiểm soát về **state, quyền sở hữu resource, side effect và loại lỗi**. Một `catch(Throwable)` đặt ở cùng heap/JVM **không tạo ra ranh giới an toàn trước `OutOfMemoryError`**.

Ví dụ một test runner có thể bắt `AssertionError` để đánh dấu một test thất bại và tiếp tục test kế tiếp; nhưng chính test runner đó không mặc định có khả năng phục hồi an toàn sau lỗi JVM nội bộ.

**Nguyên tắc:** mỗi nhánh `catch` phải trả lời rõ “tôi làm gì với lỗi này?” và “vì sao vẫn được phép chạy tiếp?”. Không trả lời được thì không nên dùng `catch` quá rộng.

## 3. Một `Error` không giống một lỗi nghiệp vụ có thể dự kiến

Lỗi nghiệp vụ thường có **quy tắc xác định** và **cách phản hồi hợp lệ**:

- Input số lượng âm → từ chối bằng `IllegalArgumentException` hoặc mã validation.
- Không tìm thấy file cấu hình → `IOException` hoặc một exception ở abstraction cấu hình.
- Người dùng không có quyền → lỗi quyền truy cập phù hợp.
- Tác vụ hết hạn chờ → chính sách timeout/retry có kiểm soát.

Trong khi đó:

- `OutOfMemoryError`: cấp phát không được đáp ứng. Thậm chí thao tác log hoặc tạo response có thể tiếp tục thất bại.
- `StackOverflowError`: stack của luồng có thể đã cạn; đường gọi phức tạp trong handler có thể không an toàn.
- `LinkageError`: bytecode/dependency/runtime có thể không tương thích. Retry cùng bản triển khai thường không sửa được.
- `AssertionError`: có thể chỉ ra một bất biến lập trình đã bị phá vỡ; dữ liệu và side effects của tác vụ cần được kiểm tra.

Những loại trên đều là **`Error`** nhưng nguồn phát sinh khác nhau. Đừng dùng một phán đoán tuyệt đối như “mọi `Error` đều chấm dứt JVM”, cũng đừng dùng một nhánh recovery chung cho tất cả.

## 4. Câu hỏi bắt buộc trước khi viết `catch (Error)` hoặc `catch (Throwable)`

Trước khi đặt một catch rộng, xác định:

1. **Ranh giới ở đâu?** Một phương thức nghiệp vụ, một request, một worker, một test case, hay cả tiến trình?
2. **Ai sở hữu trạng thái?** Có transaction, dữ liệu trung gian, lock, stream hay biến toàn cục chưa hoàn tất không?
3. **Tại sao cần bắt loại rộng?** Vì quan sát, cleanup, chuyển quyền điều phối, hay thực sự có một đường phục hồi?
4. **Có nên ném lại ngay không?** Nếu không, bằng chứng gì cho phép tiếp tục?
5. **Lỗi gốc được bảo toàn thế nào?** Stack trace, cause và suppressed có bị thay thế hoặc mất không?
6. **Nếu cả handler/logging cũng lỗi thì sao?** Đặc biệt khi thiếu bộ nhớ và stack.
7. **Có phân biệt `Error` với `Exception` không?** Không đánh đồng lỗi hệ thống với đầu vào sai.
8. **Ai ra quyết định restart/isolate?** Ứng dụng, supervisor, container orchestrator hay test framework?
9. **Có thể kiểm thử bằng tình huống an toàn không?** Dùng `AssertionError` mô phỏng thay vì cố cạn heap.
10. **Người gọi có bị nhận kết quả thành công giả không?** Đây thường là dấu hiệu design sai.

Một catch rộng không thỏa các câu hỏi này nên được thay bằng catch **những loại exception cụ thể** hoặc được chuyển tới ranh giới quản lý hợp lý.

## 5. `catch (Exception)` thường là lựa chọn hợp lý hơn ở nghiệp vụ

Một request handler có thể xử lý:

~~~java
// Đoạn minh họa, phụ thuộc processRequest và response classes.
try {
    return processRequest();
} catch (IllegalArgumentException ex) {
    return invalidRequest(ex.getMessage());
} catch (java.io.IOException ex) {
    return temporaryFailure();
} catch (Exception ex) {
    reportUnexpectedException(ex);
    return internalFailure();
}
~~~

Cấu trúc này vẫn đòi hỏi chính sách rõ cho mỗi loại, nhưng **`Error` không bị bắt bởi `catch (Exception)`**. Nó tránh biến những lỗi JVM/linkage thành response “lỗi 500 thông thường” rồi cứ tiếp tục phục vụ như không có gì.

Không phải `catch (Exception)` luôn phù hợp: nó vẫn rất rộng so với `IOException` hay `IllegalArgumentException` và có thể nuốt cả các lỗi lập trình thuộc `RuntimeException`. Trong thư viện thấp tầng, nên ưu tiên catch **loại cụ thể mà bạn có thể xử lý**.

Ngược lại, một controller hoặc boundary thực thi có thể cần bắt `Exception` để ghi log/tạo response cuối cùng, miễn là không hứa khôi phục trạng thái chưa kiểm chứng.

## 6. Trường hợp bắt `Error` để ghi nhận rồi ném lại

Hãy tách xử lý đầu vào thông thường với lỗi bất biến nghiêm trọng.

Chương trình Java 17 hoàn chỉnh `BoundaryRethrowDemo.java`:

~~~java
public class BoundaryRethrowDemo {
    static void runTask(String mode) {
        if ("invalid".equals(mode)) {
            throw new IllegalArgumentException("tham số sai");
        }
        if ("bug".equals(mode)) {
            throw new AssertionError("bất biến hỏng");
        }
        System.out.println("Tác vụ hoàn thành");
    }

    static void boundary(String mode) {
        try {
            runTask(mode);
        } catch (IllegalArgumentException ex) {
            System.out.println("Xử lý đầu vào: " + ex.getMessage());
        } catch (Error err) {
            System.out.println("Quan sát lỗi nghiêm trọng: "
                    + err.getClass().getSimpleName());
            throw err;
        }
    }

    public static void main(String[] args) {
        boundary("ok");
        boundary("invalid");
        try {
            boundary("bug");
        } catch (AssertionError err) {
            System.out.println("Tầng gọi nhận lại: " + err.getMessage());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 BoundaryRethrowDemo.java
java BoundaryRethrowDemo
~~~

Stdout chính xác:

~~~text
Tác vụ hoàn thành
Xử lý đầu vào: tham số sai
Quan sát lỗi nghiêm trọng: AssertionError
Tầng gọi nhận lại: bất biến hỏng
~~~

Cách hiểu:

- `mode="ok"`: tác vụ kết thúc thành công.
- `mode="invalid"`: một `IllegalArgumentException` được bắt ở boundary và xử lý như trường hợp đầu vào sai.
- `mode="bug"`: tạo `AssertionError`; `catch (Error)` chỉ ghi nhận rồi dùng `throw err;`, **không đổi loại đối tượng** và không coi tác vụ đã thành công.
- `main` có handler rất cụ thể `catch (AssertionError)` để **minh họa** rằng lỗi đã được chuyển lên tầng gọi. Trong production, việc tầng ngoài làm gì còn phụ thuộc chính sách dừng tác vụ/tiến trình.

**Cảnh báo:** nhánh ghi log dùng `System.out.println` cho ví dụ dễ thấy; không nên suy rằng luôn có thể in log khi thực sự gặp `OutOfMemoryError`. Một ranh giới cấp production cần phương án giám sát tối giản và không được dựa vào khả năng cấp phát bộ nhớ không giới hạn.

## 7. `throw err;` khác với `throw new RuntimeException(err);`

Xét hai lựa chọn sau trong cùng một `catch(Error err)`:

~~~java
// Truyền chính đối tượng Error ban đầu ra ngoài.
throw err;
~~~

~~~java
// Tạo wrapper RuntimeException mới; thường không nên làm với Error nghiêm trọng.
throw new RuntimeException("lỗi tác vụ", err);
~~~

Khác biệt:

| Tiêu chí | `throw err` | `throw new RuntimeException(..., err)` |
| --- | --- | --- |
| Loại đối tượng ngoài cùng | Giữ loại `Error` gốc | `RuntimeException` mới |
| Danh tính đối tượng | Giữ nguyên đối tượng | Đối tượng wrapper mới |
| Cause | Không tạo liên kết mới | `Error` được giữ dưới `getCause()` nếu constructor đúng |
| `catch (Exception)` ở caller | Không bắt trực tiếp `Error` gốc | Có thể bắt wrapper `RuntimeException` |
| Nguy cơ | Lỗi tiếp tục lan đúng loại | Có thể làm caller xử lý như exception nghiệp vụ nếu không xem cause |

**Không bao bọc `OutOfMemoryError` hoặc `LinkageError` thành `RuntimeException` chỉ để chúng lọt vào một bộ xử lý “Exception chung”.** Điều đó thay đổi thông tin phân loại và có thể che một sự cố hệ thống nghiêm trọng. Nếu một framework có hợp đồng bao `Throwable`, người tích hợp cần tra nguyên nhân thực tế trước khi quyết định recovery.

Bản thân thao tác tạo wrapper cũng cấp phát một đối tượng mới — không đáng tin khi đang thiếu bộ nhớ nghiêm trọng.

## 8. Khi nào `catch (Throwable)` có thể có mục đích chính đáng?

`catch (Throwable)` bắt cả nhánh `Exception` lẫn `Error`. Một số ranh giới **có thể** cần quan sát mọi `Throwable`:

- Test runner thu thập thất bại của một test case để báo cáo toàn bộ suite.
- Framework điều phối tác vụ nhận một báo cáo lỗi cuối cùng từ worker.
- Một lớp quản lý lifecycle nhận thất bại của plugin sandbox đã được kiểm soát chặt.
- Một đoạn cleanup/giám sát cuối ở nơi cần ghi nhận lỗi trước khi chuyển quyền xử lý.
- Bộ thực thi task/future cần lưu trữ `Throwable` theo hợp đồng API.

Nhưng điều kiện áp dụng nghiêm ngặt: **nhận mọi `Throwable` không có nghĩa là phục hồi được mọi `Throwable`**. Có những lỗi fatal mà sau khi ghi nhận, process nên ngừng, để supervisor bên ngoài xử lý.

Nếu chỉ cần ghi nhận rồi truyền tiếp, mẫu:

~~~java
// Mã minh họa khi phương thức runTask() có thể ném Exception.
try {
    runTask();
} catch (Throwable failure) {
    observeMinimal(failure);
    throw failure;
}
~~~

Ở đây `observeMinimal` cần là phương thức giám sát đã được định nghĩa. Đoạn này **không độc lập**. Khi `runTask()` có checked exception, phương thức chứa phải thỏa catch-or-declare. Với `throw failure` của một tham số catch effectively final, Java có quy tắc **precise rethrow**, cho phép compiler phân tích các loại checked thực sự có thể thoát từ vùng `try`. Không được nghĩ rằng `catch(Throwable)` làm mọi checked exception biến mất.

## 9. Java 17: quan sát cả `Exception` và `Error` rồi truyền đúng loại

Tệp `ThrowableGuardDemo.java`:

~~~java
public class ThrowableGuardDemo {
    static void simulate(String mode) throws Exception {
        if ("checked".equals(mode)) {
            throw new Exception("lỗi kiểm tra");
        }
        if ("error".equals(mode)) {
            throw new AssertionError("lỗi bất biến");
        }
    }

    static void observeAndPropagate(String mode) throws Exception {
        try {
            simulate(mode);
        } catch (Throwable failure) {
            System.out.println("Quan sát: " + failure.getClass().getSimpleName());
            throw failure;
        }
    }

    public static void main(String[] args) {
        for (String mode : new String[]{"checked", "error"}) {
            try {
                observeAndPropagate(mode);
            } catch (Exception ex) {
                System.out.println("Bên ngoài Exception: " + ex.getMessage());
            } catch (Error err) {
                System.out.println("Bên ngoài Error: " + err.getMessage());
            }
        }
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 -encoding UTF-8 ThrowableGuardDemo.java
java ThrowableGuardDemo
~~~

Stdout chính xác:

~~~text
Quan sát: Exception
Bên ngoài Exception: lỗi kiểm tra
Quan sát: AssertionError
Bên ngoài Error: lỗi bất biến
~~~

Phân tích:

1. `simulate()` có thể tạo `Exception` checked hoặc `AssertionError` unchecked.
2. `catch(Throwable)` ở `observeAndPropagate()` nhận cả hai trường hợp, in loại thực và **ném lại cùng đối tượng**.
3. Chữ ký `observeAndPropagate() throws Exception` đủ cho đường checked; không cần khai báo `throws Error`.
4. Caller `main()` bắt được từng loại theo **quan hệ runtime**: `Exception` đi vào `catch(Exception)`; `AssertionError` đi vào `catch(Error)`.
5. Ví dụ mô phỏng quan sát rồi chuyển tiếp, không chứng minh mọi `Error` trong ứng dụng nên được xử lý bằng cách bắt loại rộng.

Đừng lạm dụng `throws Throwable` trong public API chỉ vì đã dùng `catch(Throwable)`. Việc mở rộng checked contract tới `Throwable` có thể buộc caller xử lý một tập kiểu quá rộng và làm khó bảo trì.

## 10. Quy tắc thứ tự `catch` cũng quan trọng

Nếu cùng một `try` có cả handler cụ thể và handler bao quát, phải đặt handler **cụ thể trước handler rộng**:

~~~java
try {
    runTask();
} catch (IllegalArgumentException ex) {
    // Xử lý input sai.
} catch (Exception ex) {
    // Những Exception khác.
} catch (Error err) {
    // Quan sát Error nếu boundary thật sự cần.
}
~~~

Đây là đoạn minh họa, `runTask()` phải tồn tại. Có thể dùng `catch(Throwable)` cuối nếu API ranh giới có chính sách đặc biệt, nhưng đừng tự thêm vào mọi method.

Ví dụ không hợp lệ:

~~~java
// CỐ Ý SAI: nhánh cụ thể bị bao phủ bởi catch rộng trước đó.
try {
    runTask();
} catch (Throwable t) {
    // ...
} catch (Exception ex) {
    // Unreachable catch: Exception đã được Throwable bao phủ.
}
~~~

Compiler từ chối nhánh `catch(Exception)` vì không thể đến được. Bên cạnh yêu cầu ngôn ngữ, cách sắp xếp cụ thể → rộng cũng giúp code review nhìn rõ loại lỗi nào được chủ động xử lý và loại nào chỉ được quan sát.

## 11. `finally` và `try-with-resources` thường phù hợp hơn catch rộng để cleanup

Mục tiêu của `finally` và `try-with-resources` không phải quyết định một lỗi có recoverable hay không; chúng cung cấp đường **thu dọn tài nguyên** khi scope thoát bình thường hoặc bất thường theo ngữ nghĩa Java.

~~~java
// Đoạn minh họa.
try {
    doWork();
} finally {
    closeLocalResources();
}
~~~

Nếu `doWork()` ném `AssertionError`, JVM bình thường cố chạy `finally` trước khi truyền tiếp lỗi. Nhưng:

- `finally` có thể **không chạy** nếu tiến trình bị kill, `Runtime.halt()` xảy ra hoặc JVM không thể tiếp tục.
- Nếu code trong `finally` tự ném lỗi, lỗi mới **có thể che lỗi gốc** trừ khi có thiết kế bảo toàn.
- Một `closeLocalResources()` quá phức tạp có thể gây hỏng trạng thái phụ, làm việc điều tra khó hơn.
- Cleanup không tự chứng minh rằng mọi side effect hoặc transaction đã rollback.

Đối với tài nguyên implement `AutoCloseable`, `try-with-resources` có khả năng giữ ngoại lệ chính và gắn lỗi đóng tài nguyên dưới dạng **suppressed**. Đây thường là lựa chọn tốt để giảm rủi ro che nguyên nhân.

## 12. Java 17: `Error` chính và lỗi `close()` là suppressed

Tệp `CleanupErrorDemo.java`:

~~~java
import java.io.IOException;

public class CleanupErrorDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("Đã gọi close()");
            throw new IOException("đóng lỗi");
        }
    }

    public static void main(String[] args) throws IOException {
        try (Resource resource = new Resource()) {
            throw new AssertionError("lỗi chính");
        } catch (AssertionError err) {
            System.out.println("Chính: " + err.getMessage());
            System.out.println("Số suppressed: " + err.getSuppressed().length);
            System.out.println("Phụ: " + err.getSuppressed()[0].getMessage());
        } finally {
            System.out.println("finally kết thúc");
        }
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 -encoding UTF-8 CleanupErrorDemo.java
java CleanupErrorDemo
~~~

Stdout chính xác:

~~~text
Đã gọi close()
Chính: lỗi chính
Số suppressed: 1
Phụ: đóng lỗi
finally kết thúc
~~~

Giải thích:

- Phần thân `try` ném `AssertionError`, là lỗi chính.
- Khi rời scope, `close()` được gọi và ném `IOException`.
- `IOException` được thêm vào **`getSuppressed()` của `AssertionError`**, chứ không tự động thay lỗi chính.
- `catch(AssertionError)` trong ví dụ chỉ đọc cấu trúc lỗi để giảng giải; trong ứng dụng thông thường, có thể để lỗi lan tiếp sau cleanup.
- `main throws IOException` vẫn cần có để compiler chấp nhận lời gọi `close()` ngầm có checked `IOException`. Đừng hiểu rằng một `Error` được ném trong body làm các nghĩa vụ checked của resource close biến mất.
- `getSuppressed()[0]` ở ví dụ an toàn vì chính `close()` cố định ném một ngoại lệ. Code tổng quát phải kiểm tra mảng trước khi truy cập.

Một `Error` có thể có suppressed exception giống các `Throwable` khác; tuy nhiên điều này không biến lỗi tài nguyên thành **cause** của Error. `getCause()` và `getSuppressed()` mô tả hai quan hệ khác nhau.

## 13. Vì sao không nên nuốt lỗi trong `finally`?

Đoạn sau gây rủi ro:

~~~java
// Anti-pattern: lỗi trong finally có thể che lỗi gốc.
try {
    throw new AssertionError("nguyên nhân chính");
} finally {
    throw new IllegalStateException("cleanup thất bại");
}
~~~

Khi `finally` ném `IllegalStateException`, lý do thoát sau cùng của biểu thức là lỗi mới, còn `AssertionError` trước đó **không tự động được gắn làm cause/suppressed**.

Thay vì dùng `return` hoặc `throw` tùy tiện trong `finally`, hãy ưu tiên `try-with-resources` khi phù hợp. Nếu bắt buộc cleanup thủ công, thiết kế để **bảo toàn lỗi chính** và xử lý lỗi cleanup đúng cách; việc dùng `Throwable.addSuppressed()` cũng cần thận trọng với vòng tham chiếu và trường hợp suppress bị vô hiệu hóa trong custom throwable.

**Không dùng `return` trong `finally` để “ổn định” chương trình.** Nó có thể thay thế cả kết quả và đường ngoại lệ, khiến lỗi nghiêm trọng bị nuốt.

## 14. Ranh giới thread: một `Error` không bắt có thể kết thúc chỉ một luồng

Java cho phép đặt `Thread.UncaughtExceptionHandler` để nhận `Throwable` khi một luồng kết thúc bất thường mà không có handler xử lý trước.

Chương trình `WorkerUncaughtDemo.java`:

~~~java
public class WorkerUncaughtDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(
                () -> { throw new AssertionError("worker lỗi"); }, "worker-196");

        worker.setUncaughtExceptionHandler((thread, failure) ->
                System.out.println("Uncaught " + thread.getName() + ": "
                        + failure.getClass().getSimpleName()));

        worker.start();
        worker.join();
        System.out.println("Main còn chạy");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 WorkerUncaughtDemo.java
java WorkerUncaughtDemo
~~~

Stdout chính xác:

~~~text
Uncaught worker-196: AssertionError
Main còn chạy
~~~

**Diễn giải đúng:**

- `worker` ném `AssertionError` không được bắt, nên kết thúc bất thường.
- Uncaught handler nhận lỗi của worker và in thông điệp.
- `join()` của main hoàn tất sau khi worker kết thúc; main tiếp tục.
- Sự thật “main còn chạy” **không chứng minh trạng thái chia sẻ còn nhất quán** hoặc có thể tự động chạy lại công việc đã thất bại.
- Handler là chỗ **ghi nhận thất bại của luồng**, không phải một phương thức có thể tiếp tục chạy chính luồng đó sau câu lệnh ném lỗi.

Đối với `ExecutorService` hoặc `Future`, lỗi của task có thể được ghi nhận theo hợp đồng executor/future và chỉ lộ ra khi truy xuất kết quả bằng những API như `Future.get()`. Không nên giả định mọi task failure đều đi qua cùng một uncaught handler như ví dụ `Thread` thuần.

## 15. Ranh giới test/plugin được cô lập: khi nào tiếp tục có lý do?

Một test runner có thể **chủ động thiết kế** để một test thất bại vì `AssertionError` nhưng suite vẫn tiếp tục. Điều đó khác với việc production nuốt bất kỳ `Error` nào trong core business logic.

Chương trình Java 17 `IsolatedPluginDemo.java` chỉ dùng một **fixture nội bộ**, không gọi mã plugin bên ngoài:

~~~java
public class IsolatedPluginDemo {
    interface Plugin {
        void execute();
    }

    static boolean runIsolatedFixture(Plugin plugin) {
        try {
            plugin.execute();
            return true;
        } catch (AssertionError err) {
            System.out.println("Plugin thử nghiệm thất bại: "
                    + err.getClass().getSimpleName());
            return false;
        }
    }

    public static void main(String[] args) {
        boolean first = runIsolatedFixture(
                () -> { throw new AssertionError("fixture"); });
        boolean second = runIsolatedFixture(
                () -> System.out.println("Plugin thử nghiệm OK"));
        System.out.println("Kết quả: " + first + ", " + second);
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 -encoding UTF-8 IsolatedPluginDemo.java
java IsolatedPluginDemo
~~~

Stdout:

~~~text
Plugin thử nghiệm thất bại: AssertionError
Plugin thử nghiệm OK
Kết quả: false, true
~~~

Ví dụ cho thấy: ở một boundary có **mục tiêu rõ là ghi nhận lỗi fixture**, catch **đúng `AssertionError`** và tiếp tục fixture sau có thể hợp lý. Nhưng tên `IsolatedPluginDemo` không có nghĩa cùng JVM tạo sandbox bảo mật, tách bộ nhớ hay cô lập side effects của plugin không đáng tin. **Đây không phải một sandbox thực sự**; nó chỉ cô lập *luồng điều khiển và biến cục bộ của demo*.

Với plugin không đáng tin, một `catch(Throwable)` trong cùng JVM **không đủ cách ly**: plugin có thể sửa trạng thái tĩnh, tạo thread, giữ tài nguyên, block vô hạn, làm cạn heap hoặc gọi API nguy hiểm. Cần kiểm soát quyền hạn và có thể cần **tách process/container** theo yêu cầu hệ thống, cùng chính sách timeout/kill/restart. Đừng quảng cáo `catch(Error)` như cơ chế cô lập lỗi đáng tin.

## 16. Phân loại lỗi sau khi `catch(Throwable)`: tránh một nhánh “thành công giả”

Nếu một framework buộc phải quan sát mọi `Throwable`, nó cần **phân loại theo khả năng xử lý** thay vì trả `true` bất kể lỗi.

Một logic gợi ý (không phải code framework hoàn chỉnh):

~~~java
// Mã minh họa ở boundary có chính sách riêng.
try {
    invokePlugin();
} catch (java.io.IOException ex) {
    reportRecoverableFailure(ex);
} catch (Error fatal) {
    reportCriticalFailureBestEffort(fatal);
    throw fatal;
} catch (Exception ex) {
    reportUnexpectedException(ex);
    throw ex;
}
~~~

Các hàm phụ thuộc ứng dụng; method bao ngoài có thể cần khai báo `throws Exception` nếu có checked exception thoát. Điều quan trọng là **tách bản chất lỗi**: nếu code phát hiện `Error`, nó không vội chuyển thành trạng thái “plugin thất bại bình thường, cứ dùng tiếp”.

Không nhất thiết phải catch toàn bộ `Error` để phân loại: một boundary có thể để Error lan ra và dùng giám sát ngoài process. Chiến lược ghi nhận `Error` trong process chỉ phù hợp nếu chi phí và rủi ro được hiểu rõ.

Trường hợp đặc biệt: `ThreadDeath` là subclass của `Error`. Tài liệu Java nhấn mạnh nếu ứng dụng bắt `ThreadDeath`, thường nên **ném lại** để cơ chế dừng luồng được tiếp tục; tránh chặn/nuốt lỗi này. Tương tự, đừng bắt `VirtualMachineError` chỉ để thử “phục hồi chung”.

## 17. Catch rộng và `InterruptedException`: đừng phá hỏng tín hiệu hủy

Một catch rất rộng có thể gây vấn đề ngay cả với loại **`Exception`**. `InterruptedException` là checked exception thường báo một luồng đang bị yêu cầu gián đoạn khi block trong những API như `sleep()` hoặc `wait()`.

Ví dụ trong một worker:

~~~java
try {
    Thread.sleep(10_000);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Đây là đoạn minh họa nằm trong method `void` thích hợp. Việc **khôi phục interrupt flag** bằng `Thread.currentThread().interrupt()` trước khi rời scope là một lựa chọn phổ biến khi tầng hiện tại không thể khai báo truyền `InterruptedException` lên trên. Nếu hợp đồng cho phép, có thể `throw ex;` để caller xử lý đúng.

Một `catch(Exception ex)` hoặc `catch(Throwable t)` rồi bỏ qua có thể che tín hiệu hủy tác vụ. Dù đây không phải `Error`, nó minh họa lý do catch rộng phải có **mục đích và chính sách** thay vì xử lý mọi lỗi bằng một đường duy nhất.

**Không đồng nhất `InterruptedException` với `ThreadDeath`**: chúng là hai loại và cơ chế rất khác nhau; `Thread.stop()` gây `ThreadDeath` đã bị deprecated vì mất an toàn. Trong code mới, ưu tiên cơ chế hủy hợp tác như interrupt, flag hủy hoặc API task cancellation phù hợp.

## 18. Ranh giới giao dịch và side effects: “đã catch” chưa phải rollback

Giả sử một thao tác:

~~~text
Đọc yêu cầu
    ↓
Ghi một phần dữ liệu
    ↓
Gửi thông báo ngoài hệ thống
    ↓
Lỗi nghiêm trọng được ném
    ↓
catch(Throwable) { return success; }
~~~

Việc `catch` thành công **không hoàn tác** hai bước đã thực hiện. Nếu caller thấy thành công và thử gửi yêu cầu khác, trạng thái có thể còn rối hơn.

Khi cân nhắc recovery:

1. Giao dịch lưu trữ có thực sự rollback tự động không?
2. Side effect ngoài transaction (email, thanh toán, message queue) có thể đã xảy ra chưa?
3. Có định danh **idempotency** để tránh thực hiện trùng không?
4. Có resource/lock còn giữ không?
5. Có thể xác định thao tác đã hoàn tất hay chưa?
6. Nếu không biết, có cần chuyển sang trạng thái **unknown/pending investigation** thay vì thành công không?

Một boundary đáng tin có thể **dừng xử lý tác vụ**, ghi nhận thất bại và để quy trình đối soát/giám sát quyết định bước tiếp theo. Bắt `Throwable` rồi trả mặc định hiếm khi là giải pháp đúng cho công việc có side effects.

## 19. `OutOfMemoryError`: vì sao cleanup/logging trong `catch` cũng có thể thất bại?

Trong trường hợp cạn bộ nhớ, rất nhiều hành động thông thường cần cấp phát: tạo chuỗi, định dạng stack trace, serialize JSON, tạo exception wrapper mới hoặc ghi log bất đồng bộ.

Vì thế:

~~~java
// Anti-pattern: KHÔNG coi đây là chiến lược khôi phục OOM.
try {
    runHeavyTask();
} catch (OutOfMemoryError err) {
    logger.error("Thất bại: " + err.getMessage(), err);
    return new LargeFallbackResponse();
}
~~~

Đoạn minh họa này phụ thuộc `runHeavyTask`, `logger`, `LargeFallbackResponse` và không phải chương trình chạy. Nó không an toàn để coi là chính sách tổng quát: **chính xử lý bên trong catch có thể tiếp tục yêu cầu bộ nhớ**.

Thực hành tốt hơn: thiết lập **monitoring, resource limits, heap dump khi phù hợp, restart policy và health check** trước khi sự cố xảy ra. Đối với hệ thống cần chịu lỗi ở cấp tác vụ, cân nhắc cô lập workload trong process/container để supervisor ngoài tiến trình kiểm soát khi một instance không còn đáng tin.

Không thể khẳng định mọi `OutOfMemoryError` đều chắc chắn làm JVM chết; nhưng **không có bảo đảm an toàn để tiếp tục chỉ vì đã catch được nó**.

## 20. `LinkageError` và lỗi khởi tạo lớp: retry cùng một class không giải quyết vấn đề

Một `LinkageError` thường liên quan tới phiên bản dependency, trạng thái classloader hoặc bytecode. Ví dụ:

- `NoSuchMethodError` khi mã gọi method không tồn tại ở runtime version của library.
- `UnsupportedClassVersionError` khi JVM không hỗ trợ class file version.
- `NoClassDefFoundError` khi không có định nghĩa class phù hợp hoặc class đã khởi tạo thất bại.
- `ExceptionInInitializerError` khi static initialization kết thúc bất thường với nguyên nhân không phải Error.

Giả sử một static initializer đã ném `IllegalStateException`. JVM có thể báo `ExceptionInInitializerError` ở lần sử dụng đầu, rồi **`NoClassDefFoundError`** ở lần sử dụng tiếp trong cùng classloader vì class ở trạng thái erroneous.

Một `catch(Throwable)` rồi thử truy cập class đó lần nữa **không làm chạy lại static initializer bình thường**. Việc khôi phục thường phải sửa cấu hình/deployment/lifecycle, không phải thêm retry cục bộ mù quáng.

Nếu gặp `NoClassDefFoundError`, đừng mặc định “thiếu file .class”; cần kiểm tra lỗi đầu tiên, classpath/module path và log class initialization. Loại `Error` ngoài cùng không phải luôn cung cấp toàn bộ nguyên nhân.

## 21. Đọc `cause` và `suppressed` ở một boundary

Một `Throwable` cung cấp nhiều góc chẩn đoán:

- `getClass()`: loại đối tượng thực tế đang quan sát.
- `getMessage()`: thông điệp chẩn đoán; không nên parse như mã lỗi ổn định.
- `getCause()`: ngoại lệ/Throwable được gắn là nguyên nhân trực tiếp, nếu có.
- `getSuppressed()`: các lỗi phụ, thường gặp khi cleanup trong `try-with-resources`.
- Stack trace: các frame liên quan tới đường xảy ra lỗi.

Khi lỗi được bọc, outermost exception có thể thuộc nhánh `Exception` nhưng cause sâu hơn lại là `Error`. Do đó một boundary không nên quyết định “lỗi có thể retry” chỉ dựa trên việc **wrapper ngoài cùng** là `Exception`.

Ví dụ:

~~~java
// Minh họa bên trong một phương thức.
Throwable fatal = new AssertionError("bất biến hỏng");
Exception wrapper = new Exception("tác vụ thất bại", fatal);

System.out.println(wrapper instanceof Exception);  // true
System.out.println(wrapper.getCause() instanceof Error); // true
~~~

Hai dòng trên sẽ in `true` và `true`. Đây là **mã minh họa không có lớp/main đầy đủ**. Điều cần thấy là **wrapper thay đổi loại ngoài cùng nhưng không làm lỗi bên dưới trở nên recoverable**.

Nếu muốn duyệt toàn bộ cause chain và suppressed của một `Throwable` bất kỳ, nên có cơ chế tránh tham chiếu lặp/vòng bất thường; không dùng vòng lặp `getCause()` vô hạn đối với dữ liệu không kiểm soát.

## 22. `Thread.UncaughtExceptionHandler` không phải phương thức sửa lỗi tự động

Uncaught handler có thể nhận `Throwable` khi thread kết thúc bất thường. Nó phù hợp để **ghi nhận sự kiện** và cập nhật trạng thái supervisor. Nhưng:

- Handler không quay lại chính câu lệnh đã ném.
- Handler chạy theo cơ chế xử lý uncaught; nó không biến exception thành kết quả thành công của worker.
- Một uncaught handler có thể tự lỗi; đừng phụ thuộc vào các thao tác nặng hoặc cấp phát lớn.
- Nếu worker sở hữu dữ liệu dùng chung, các luồng khác có thể bị ảnh hưởng.
- Nếu một tác vụ do `ExecutorService` quản lý, lỗi có thể được bao trong `Future` thay vì luôn đi qua thread uncaught handler.

Vì vậy cần **thiết kế ranh giới theo cơ chế thực thi đang dùng** (Thread trực tiếp, executor, actor, job queue, test runner), không sao chép một khối `catch(Throwable)` chung tới mọi vị trí.

## 23. Cây quyết định khi xem xét một catch rộng

~~~text
Một thao tác có thể thất bại
        |
        v
Biết loại lỗi và có cách xử lý hợp đồng?
        |
        +-- Có --> Bắt loại cụ thể (IOException, domain exception...)
        |             |
        |             +--> Khôi phục/biến đổi/lỗi có cấu trúc, theo chính sách
        |
        +-- Không --> Có thật sự cần quan sát mọi Throwable ở boundary?
                      |
                      +-- Không --> Để lỗi lan truyền; dùng finally/TWR cleanup
                      |
                      +-- Có --> Ranh giới đã được xác định rõ?
                                    |
                                    +-- Không --> Thiết kế lại boundary
                                    |
                                    +-- Có --> Ghi nhận tối thiểu
                                                  |
                                                  +--> Lỗi Error nghiêm trọng?
                                                  |       |
                                                  |       +--> Thường rethrow/đánh dấu
                                                  |             thành phần không khỏe
                                                  |
                                                  +--> Exception có chính sách?
                                                          |
                                                          +--> Bắt/biến đổi theo contract
~~~

Sơ đồ là **công cụ tư duy**, không phải thuật toán tự động phân loại mọi exception. Một số `Error` như `AssertionError` được dùng có chủ đích trong test runner; một số lỗi `Exception` cũng có thể báo trạng thái không đáng tin và không nên retry. Các quyết định đều phải xét **ngữ cảnh**.

## 24. Những anti-pattern thường gặp

| Anti-pattern | Rủi ro | Cách sửa |
| --- | --- | --- |
| `catch(Throwable) { }` | Nuốt mọi lỗi, kể cả `Error` nghiêm trọng | Bắt cụ thể; nếu cần quan sát, rethrow hoặc báo trạng thái thất bại |
| `catch(Error) { return fallback; }` trong mọi request | Giả vờ hệ thống khỏe dù có thể hết bộ nhớ/linkage lỗi | Để Error lan truyền và dùng chính sách supervisor |
| `catch(Throwable)` rồi convert mọi thứ thành HTTP 200 | Che lỗi và side effects chưa hoàn tất | Trả lỗi có cấu trúc chỉ cho tình huống có hợp đồng hợp lệ |
| `catch(OutOfMemoryError)` rồi tạo hàng loạt đối tượng để log | Handler có thể lại cạn bộ nhớ | Giám sát/dump/restart được chuẩn bị sẵn; giảm xử lý trong process |
| Retry ngay cùng lời gọi sau `LinkageError` | Không sửa được dependency/classloader sai | Kiểm tra build/deploy, sửa version, restart phù hợp |
| Bọc `Error` thành `RuntimeException` vô điều kiện | Che loại nghiêm trọng khiến catch(Exception) xử lý như nghiệp vụ | Giữ nguyên loại/propagate hoặc dùng hợp đồng framework minh bạch |
| Dùng `return` trong `finally` | Có thể nuốt Throwable đang lan truyền | Dùng cleanup rõ, tránh return/throw đè lỗi gốc |
| Cleanup ném lỗi mới che lỗi chính | Mất dấu vết nguyên nhân | `try-with-resources`, suppressed hoặc chiến lược bảo toàn lỗi |
| Chỉ ghi `getMessage()` | Mất stack trace, cause, suppressed | Ghi nguyên Throwable tại boundary thích hợp |
| Thấy worker thread kết thúc nhưng main còn chạy, rồi coi hệ thống an toàn | State dùng chung có thể hỏng | Đánh giá transaction, lock, resource và consistency |
| Dùng `catch(Throwable)` như sandbox cho plugin không đáng tin | Không cô lập heap, threads và side effects | Quản lý quyền/tài nguyên và cân nhắc process isolation |
| Nuốt `InterruptedException` cùng các loại khác | Mất tín hiệu hủy hợp tác | Propagate hoặc khôi phục interrupt flag |
| Nuốt `ThreadDeath` | Có thể cản cơ chế dừng luồng legacy | Tránh `Thread.stop`; nếu bắt phải có lý do và thường rethrow |
| Cho rằng `Error` không thể ném thủ công | Đánh giá sai `AssertionError` trong test | Đọc loại thực tế và nguồn ném |
| Cho rằng catch được OOM nghĩa là bộ nhớ đã phục hồi | Không có bảo đảm tài nguyên khả dụng | Giám sát, giới hạn tài nguyên, quản lý lifecycle |

## 25. Checklist review code có `catch(Error)` hoặc `catch(Throwable)`

Trước khi phê duyệt:

1. Tên method/class có cho thấy đây là **boundary điều phối** (runner, supervisor, framework) hay chỉ là method nghiệp vụ?
2. Có **chính sách loại lỗi** rõ ràng không, đặc biệt cho `VirtualMachineError` và `LinkageError`?
3. Handler chỉ ghi nhận/cleanup hay trả **thành công giả**?
4. Nếu handler không ném lại, có **cách ly trạng thái thật sự** để cho phép tiếp tục không?
5. Cleanup có giữ lỗi chính nếu chính cleanup ném lỗi không?
6. Có đoạn nào `return` hoặc `throw` trong `finally` có thể che `Error` gốc không?
7. Khi cần log, có giữ **class, stack trace, cause và suppressed** không?
8. Có hạn chế chi phí log, tránh cấp phát lớn khi thiếu tài nguyên không?
9. Có tránh retry không kiểm soát sau `OutOfMemoryError`, `StackOverflowError`, `LinkageError` không?
10. Có khác biệt giữa thread thực tế, executor/future và plugin runner không?
11. `InterruptedException` và `ThreadDeath` có được bảo toàn đúng chính sách không?
12. Có kiểm thử cả đường **thành công, lỗi recoverable và lỗi mô phỏng nghiêm trọng** không?
13. Các kiểm thử có **không cố gây cạn heap/stack** trên máy dùng chung không?
14. Ai sở hữu quyết định **dừng, restart, đánh dấu unhealthy hoặc đối soát** khi boundary không thể bảo đảm an toàn?

Có thể xem một nhánh `catch(Throwable)` không có câu trả lời cho những câu hỏi trên là một **rủi ro thiết kế**, ngay cả khi code biên dịch và test đường thành công đều chạy.

## 26. Tự kiểm tra kiến thức

**Câu 1.** `catch(Exception)` có bắt `OutOfMemoryError` không?

**Đáp án:** Không. `Error` không nằm dưới `Exception`.

**Câu 2.** `catch(Throwable)` có bắt cả `Exception` lẫn `Error` không?

**Đáp án:** Có. Chính vì thế nó cần boundary và mục đích rõ ràng.

**Câu 3.** Bắt một `Error` có chứng minh ứng dụng có thể tiếp tục bình thường không?

**Đáp án:** Không. Cần xác định loại lỗi, tài nguyên và trạng thái sau thất bại.

**Câu 4.** Vì sao test runner có thể bắt `AssertionError` của một test case mà không phải mọi web request handler đều nên bắt `Error`?

**Đáp án:** Test runner có contract **ghi nhận test thất bại** và có ranh giới test; request handler không mặc định có khả năng phục hồi sau mọi lỗi JVM hoặc lỗi bất biến.

**Câu 5.** `throw err` từ `catch(Error err)` có tạo wrapper mới không?

**Đáp án:** Không. Nó ném lại chính đối tượng Error.

**Câu 6.** `throw new RuntimeException("x", err)` có thể làm `catch(Exception)` bên ngoài bắt wrapper không?

**Đáp án:** Có; nhưng một `Error` trong cause vẫn có thể báo tình trạng nghiêm trọng.

**Câu 7.** `finally` có chạy khi phần thân ném `AssertionError` trong đường thực thi Java bình thường không?

**Đáp án:** Thông thường có. Nhưng không bảo đảm khi JVM bị dừng cưỡng bức hoặc không còn khả năng tiếp tục.

**Câu 8.** Nếu `close()` ném `IOException` trong lúc phần thân `try-with-resources` ném `AssertionError`, lỗi đóng nằm ở đâu?

**Đáp án:** Thường ở `getSuppressed()` của lỗi chính `AssertionError`.

**Câu 9.** Worker thread ném `AssertionError` không bắt, main có thể tiếp tục không?

**Đáp án:** Có. Nhưng không có bảo đảm trạng thái chia sẻ và side effects vẫn hợp lệ.

**Câu 10.** `UncaughtExceptionHandler` có làm worker quay lại chỗ trước khi ném lỗi không?

**Đáp án:** Không. Nó nhận báo cáo lỗi khi luồng kết thúc bất thường.

**Câu 11.** Vì sao `catch(Throwable) { return success; }` nguy hiểm trong tác vụ có thanh toán hoặc ghi dữ liệu?

**Đáp án:** Lỗi có thể xảy ra sau các side effects không rollback; trả thành công giả làm caller hiểu sai trạng thái và có nguy cơ lặp thao tác.

**Câu 12.** Bắt `OutOfMemoryError` rồi tạo đối tượng log/response lớn có đáng tin không?

**Đáp án:** Không. Những bước đó cũng có thể cần cấp phát và thất bại thêm.

**Câu 13.** Khi một task chạy trong `ExecutorService`, có nên trông đợi mọi lỗi đều được uncaught handler thông báo như `Thread` trực tiếp không?

**Đáp án:** Không. Kết quả task và exception có thể được quản lý bởi `Future` hoặc cơ chế riêng của executor.

**Câu 14.** Nếu cần thu dọn resource mà không cần chuyển một `Error` thành kết quả thành công, nên dùng gì?

**Đáp án:** Ưu tiên `finally` hoặc `try-with-resources` đúng hợp đồng, đồng thời bảo toàn lỗi gốc.

**Câu 15.** Một plugin được gọi cùng JVM nhưng quanh nó có `catch(Throwable)` đã thành sandbox an toàn chưa?

**Đáp án:** Chưa. Nó vẫn chia sẻ tài nguyên và trạng thái của JVM; cần kiểm soát thêm, đôi khi phải tách process.

## 27. Tài liệu tham khảo Java 17

- [Java SE 17 API — `Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): phân cấp lỗi, `getCause()`, `getSuppressed()`, stack trace và `addSuppressed()`.
- [Java SE 17 API — `Error`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Error.html): ý nghĩa nhánh `Error` và định hướng ứng dụng không nên bắt đại trà.
- [Java SE 17 API — `Exception`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Exception.html): phân biệt nhánh `Exception`.
- [Java SE 17 API — `VirtualMachineError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/VirtualMachineError.html), [`OutOfMemoryError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/OutOfMemoryError.html), [`StackOverflowError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackOverflowError.html): lỗi tài nguyên JVM.
- [Java SE 17 API — `LinkageError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/LinkageError.html), [`NoClassDefFoundError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html): sự cố liên kết và khởi tạo.
- [Java SE 17 API — `Thread.UncaughtExceptionHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.UncaughtExceptionHandler.html): xử lý uncaught `Throwable` ở mức luồng.
- [Java SE 17 API — `ThreadDeath`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadDeath.html): đặc điểm lịch sử của lỗi dừng luồng.
- [Java Language Specification 17 — §11](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): phân loại checked/unchecked và truyền ngoại lệ.
- [Java Language Specification 17 — §14.20](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): `try`, `catch`, `finally` và `try-with-resources`.
- [Java Language Specification 17 — §12.4.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): khởi tạo class và trạng thái erroneous.

**Kết luận:** `catch(Throwable)` hoặc `catch(Error)` chỉ có ý nghĩa tốt khi được đặt ở **ranh giới đã xác định**, với **mục tiêu cụ thể** như quan sát, cleanup, báo trạng thái thất bại hoặc cô lập một fixture đã được kiểm soát. Bắt được một `Error` không bảo đảm còn đủ tài nguyên hay dữ liệu nhất quán để tiếp tục. Trong code nghiệp vụ, ưu tiên **bắt loại `Exception` cụ thể có cách khôi phục rõ**; với lỗi hệ thống nghiêm trọng, thường để lan truyền, bảo toàn nguyên nhân và dùng giám sát/lifecycle bên ngoài thay vì nuốt lỗi rồi trả về thành công.
