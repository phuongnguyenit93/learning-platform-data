# Bảo toàn giá trị trả về và đối tượng ngoại lệ gốc khi thiết kế điểm đo

Khi cài Java agent hoặc chèn bytecode để đo thời gian, trace, thống kê lỗi hay ghi sự kiện, **điểm đo phải quan sát kết quả của method chứ không tự biến thành một phần của kết quả nghiệp vụ**. Một phép đo tốt không được làm đổi giá trị trả về, thay đối tượng ngoại lệ đang được ném, tự “nuốt” lỗi nghiệp vụ hoặc phát sinh lỗi telemetry khiến caller nhìn thấy kết quả khác.

Đây là nguyên tắc quan trọng của **thiết kế điểm đo trong Java instrumentation**: trên đường thành công, phương thức tiếp tục trả đúng giá trị/đúng tham chiếu; trên đường lỗi, phương thức tiếp tục ném **chính đối tượng `Throwable` ban đầu**. Bài này giải thích ý nghĩa chính xác, quy tắc Java `try/finally`, các đường ra ở mức JVM bytecode, ví dụ Java 17+ chạy được, cách áp dụng với agent/Byte Buddy/ASM và bộ kiểm thử bất biến (*non-interference invariants*).

## 1. “Bảo toàn” nghĩa là gì?

Hãy xem method gốc như một phép tính có hai dạng kết thúc:

~~~text
                      originalMethod(...)
                             |
                +------------+------------+
                |                         |
          Kết thúc bình thường       Kết thúc bất thường
                |                         |
        trả giá trị R / void           ném Throwable T
                |                         |
        điểm đo quan sát              điểm đo quan sát
                |                         |
        trả đúng R / void             ném chính T
~~~

Một điểm đo đạt yêu cầu tối thiểu phải giữ các bất biến sau:

| Trường hợp | Bất biến cần bảo toàn |
| --- | --- |
| `int`, `long`, `boolean` và các kiểu nguyên thủy | Giá trị bit/ngữ nghĩa của kết quả không bị thay ngoài ý muốn |
| `float`, `double` | Không làm mất các trường hợp đặc biệt như `-0.0`; chú ý NaN nếu cần kiểm tra từng bit |
| Trả về object/array | **Đúng tham chiếu** đã được phương thức trả về; dùng `==` để kiểm tra identity |
| Trả về `null` | Tiếp tục trả `null`; không thay bằng object giả hoặc Optional |
| Phương thức `void` | Kết thúc bình thường như trước, không phát sinh exception từ hook |
| Throw checked exception | Caller bắt được **cùng instance** `IOException`/loại lỗi đã ném |
| Throw unchecked exception hoặc `Error` | Caller nhận **cùng instance** `Throwable`, không bị đổi sang exception khác |
| Method tự catch lỗi rồi trả bình thường | Exit hook thấy **kết quả cuối** là thành công, không tự báo lỗi chưa thoát khỏi method |
| Hook telemetry gặp lỗi | Lỗi của hook không được thay return value hay throwable nghiệp vụ |

Với object, “bảo toàn identity” **không có nghĩa object hoàn toàn bất biến**. Nếu hook gọi `toString()` rồi làm thay đổi trạng thái bên trong object, thì `returned == original` vẫn `true` nhưng hành vi ứng dụng có thể đã đổi. Vì vậy cần tránh cả **thay tham chiếu** và **tác dụng phụ ngoài ý muốn**.

Tương tự, kiểm tra exception bằng `actual.getClass() == expected.getClass()` hoặc `actual.getMessage().equals(...)` là chưa đủ: hai instance khác nhau có thể có cùng type và message. Khi yêu cầu “đối tượng ngoại lệ gốc”, bất biến trọng tâm là **`actual == originalThrowable`**.

## 2. Tại sao try/finally vừa hữu ích vừa nguy hiểm?

Java Language Specification (JLS §14.20.2) mô tả thứ tự thực hiện `try/finally`. Khi một khối `try` sắp `return` hoặc `throw`, khối `finally` được thực hiện trước khi lý do kết thúc đó chuyển ra caller.

Nếu `finally` **kết thúc bình thường**, lý do trước đó được giữ lại. Nếu chính `finally` **kết thúc bất thường** (ném exception hoặc thực hiện `return`), lý do cũ có thể bị **thay thế**. Đây là nguồn lỗi nghiêm trọng khi chèn instrumentation.

### 2.1. Mẫu đúng: hook được cô lập

~~~java
static int measured(int input) {
    long started = System.nanoTime();
    try {
        return input * 2;
    } finally {
        safeRecord(started);
    }
}
~~~

Đây là **đoạn minh họa**, cần định nghĩa `safeRecord(long)`; ví dụ đầy đủ ở phần 5. Biểu thức `input * 2` được tính trước, sau đó `safeRecord` chạy. Nếu `safeRecord` hoàn tất bình thường, caller nhận đúng kết quả ban đầu, không cần tính lại và không cần ghi đè giá trị trả về.

### 2.2. Mẫu sai: return trong finally

~~~java
static int broken(int input) {
    try {
        return input * 2;
    } finally {
        return 0; // SAI: mọi kết quả bình thường đều bị thay bằng 0.
    }
}
~~~

Nếu khối `try` ném lỗi, `return 0` trong `finally` còn có thể **nuốt luôn exception**. Đây không phải kỹ thuật ghi log; nó thay đổi contract phương thức.

### 2.3. Mẫu sai: exception của điểm đo che exception gốc

~~~java
static void brokenFailure() {
    try {
        throw new IllegalArgumentException("business");
    } finally {
        throw new IllegalStateException("telemetry"); // SAI
    }
}
~~~

Caller nhìn thấy `IllegalStateException("telemetry")`, **không phải** `IllegalArgumentException("business")`. Nếu mục tiêu của agent là quan sát mà không can thiệp, kết quả này không thể chấp nhận.

### 2.4. Mẫu an toàn: chỉ cô lập lỗi do probe sinh ra

~~~java
static void safeRecord(long startedNanos) {
    try {
        long elapsed = System.nanoTime() - startedNanos;
        recordMetric(elapsed);
    } catch (Throwable probeFailure) {
        // Chủ ý không ném lỗi telemetry ra khỏi method nghiệp vụ.
        // Có thể tăng một bộ đếm fail-safe nếu bản thân bộ đếm an toàn.
    }
}
~~~

Đây là **mảnh mã** yêu cầu hàm `recordMetric(long)`. Điểm mấu chốt là `catch` chỉ bọc **hoạt động của điểm đo**, không bọc logic nghiệp vụ để nuốt exception thật. Trong môi trường production, quyết định catch mọi `Throwable` (kể cả `Error`) phải dựa trên chính sách fail-open cho telemetry; khi JVM thiếu tài nguyên nghiêm trọng, không thể hứa mọi trường hợp `OutOfMemoryError` hoặc dừng tiến trình đều có thể phục hồi.

**Phân biệt:** “không để telemetry làm sai kết quả” khác với “mọi lỗi trong hệ thống đều bị bỏ qua”. Chỉ xử lý lỗi phát sinh từ code đo; đừng che lỗi nghiệp vụ.

## 3. Điều gì phải được giữ ở mức JVM bytecode?

Ở mức class file, từng loại return có instruction riêng, và exceptional exit có luồng điều khiển riêng.

| Kiểu method trả về | Instruction JVM thông thường | Dữ liệu cần giữ |
| --- | --- | --- |
| `boolean`, `byte`, `char`, `short`, `int` | `ireturn` | Giá trị int-category trên operand stack |
| `long` | `lreturn` | Giá trị `long` (2 local-variable slots nếu lưu tạm) |
| `float` | `freturn` | Giá trị `float` |
| `double` | `dreturn` | Giá trị `double` (2 local-variable slots nếu lưu tạm) |
| Object, array, `null` | `areturn` | Tham chiếu trên operand stack |
| `void` | `return` | Không có giá trị trả về |
| Throw object | `athrow` | Tham chiếu tới **đối tượng `Throwable` hiện có** |

**Thiết kế luồng normal exit** khi chèn đoạn mã đo ngay trước instruction return:

~~~text
Trước:
  ... tính toán
  IRETURN

Sau (minh họa phương thức trả int):
  ... tính toán
  ISTORE tempReturn      ; giữ nguyên giá trị sắp return
  gọi điểm đo an toàn
  ILOAD tempReturn       ; nạp lại đúng giá trị cũ
  IRETURN
~~~

Đối với `ARETURN`, thay `ISTORE/ILOAD` bằng `ASTORE/ALOAD`, giữ nguyên **tham chiếu**, không clone object. Với `LRETURN` và `DRETURN`, dùng `LSTORE/LLOAD` hoặc `DSTORE/DLOAD` và cấp đủ hai slot. `RETURN` cho `void` không cần lưu giá trị.

**Thiết kế exceptional exit** có thể được biểu diễn logic như sau:

~~~text
Lỗi nghiệp vụ T xảy ra
        |
        v
handler bắt đúng T
        |
    ASTORE tempThrowable
        |
    gọi điểm đo an toàn
        |
    ALOAD tempThrowable
        |
      ATHROW              ; ném lại chính object T
~~~

Cả hai sơ đồ là **pseudocode bytecode**, không phải lệnh assembler có thể biên dịch trực tiếp. Một agent thực tế phải sinh đúng instruction, local slots, branch targets, exception table và stack-map frames.

### Điểm dễ bỏ sót: không chỉ có ATHROW tường minh

JVM có thể phát sinh exception từ nhiều instruction khác, chẳng hạn:

- `invokevirtual` có thể ném `NullPointerException` hoặc lỗi bên trong method được gọi.
- `aaload`/`iaload` có thể ném lỗi truy cập mảng.
- `checkcast` có thể ném `ClassCastException`.
- `idiv` có thể ném `ArithmeticException`.
- Nạp/liên kết class cũng có thể gây lỗi lúc thực thi.

Vì vậy, **chỉ chèn mã khi gặp opcode `ATHROW` chưa đủ để đo mọi exceptional exit**. Một exception có thể thoát khỏi method mà body không chứa `ATHROW` tường minh. Muốn một exit probe xử lý cả lỗi này, cần cơ chế catch-all phù hợp bao quanh vùng thực thi của method hoặc thư viện advice hỗ trợ `onThrowable`.

Một đoạn code ASM kiểu `AdviceAdapter.onMethodExit(int opcode)` hữu ích để xử lý các opcode exit tường minh, nhưng không tự động thay thế catch-all handler cho mọi exception phát sinh ngầm. Hãy kiểm thử cả lỗi do instruction và lỗi lan truyền từ một method được gọi.

## 4. Giữ đối tượng Throwable gốc, không chỉ đúng loại lỗi

Hai code path sau **khác nhau** về contract:

~~~java
catch (Throwable original) {
    recordFailureSafely(original);
    throw original; // Cùng instance (nếu recordFailureSafely không ném lỗi).
}
~~~

~~~java
catch (Throwable original) {
    recordFailureSafely(original);
    throw new RuntimeException(original); // SAI: caller nhìn thấy instance mới.
}
~~~

Đây là **các mảnh mã** để so sánh, không phải lớp hoàn chỉnh. Mẫu thứ hai tạo wrapper exception; class, identity, cách bắt `catch`, stack trace hiển thị và hành vi caller có thể thay đổi.

Ngoài `new RuntimeException(original)`, các thao tác sau cũng có thể làm mất nguyên trạng exception:

- `throw new SomeException(original.getMessage())`: bỏ instance gốc, có thể mất cause/suppressed.
- `return defaultValue` trong exceptional path: nuốt hoàn toàn lỗi.
- Gán `null` hoặc exception khác vào vị trí lưu `Throwable` trong bytecode/advice.
- Gọi `fillInStackTrace()`, `setStackTrace(...)`, `initCause(...)` hoặc `addSuppressed(...)` chỉ để phục vụ telemetry: vẫn có thể **đột biến đối tượng gốc**.
- Gọi `toString()` hoặc `getMessage()` tùy tiện trên throwable/user object khi dựng log: code override của ứng dụng có thể tốn thời gian, có tác dụng phụ hoặc lại ném exception.
- Dùng `getCause()` thay cho chính exception đang thoát: cause là một Throwable khác (nếu có), không phải đối tượng đang được ném.

Nếu muốn phân loại lỗi, thu thập metadata tối thiểu như sự hiện diện của `Throwable` và loại lỗi bằng API phù hợp, sau đó gửi sự kiện ra một kênh telemetry có giới hạn. **Quan sát không đồng nghĩa được quyền sửa object lỗi**.

### Đừng tự động dùng addSuppressed cho lỗi điểm đo

Có trường hợp framework muốn giữ một lỗi phụ dưới dạng `suppressed exception`. Tuy nhiên nếu hợp đồng là **giữ nguyên đối tượng ngoại lệ gốc và trạng thái của nó**, việc gọi `original.addSuppressed(probeFailure)` cũng thay đổi object gốc. Thông thường nên ghi lỗi telemetry ở kênh riêng thay vì gắn nó vào lỗi nghiệp vụ; nếu không thể ghi vì telemetry hỏng, chấp nhận mất dữ liệu đo.

Nếu method gốc dùng `try-with-resources`, lỗi xảy ra trong `close()` có thể đã được Java quản lý vào danh sách suppressed của ngoại lệ nghiệp vụ. Điểm đo đặt tại **exit của toàn method** nên quan sát Throwable cuối cùng sau logic đóng tài nguyên, không thay thứ tự đóng hoặc can thiệp vào danh sách suppressed vốn có.

## 5. Ví dụ Java 17+ hoàn chỉnh: hook cố ý hỏng nhưng kết quả gốc vẫn giữ

Ví dụ sau dùng `try/finally` ở **mức source code** để tái hiện nguyên tắc mà bytecode instrumentation cần đạt. Nó không yêu cầu Byte Buddy, ASM hay Java agent; do đó dễ chạy để xác thực giá trị/identity. Điểm đo ở đây **cố ý ném `IllegalStateException`** mỗi lần, nhưng `recordSafely` cô lập lỗi đó.

### 5.1. Tạo ExitPreservationDemo.java

~~~java
import java.io.IOException;

public final class ExitPreservationDemo {
    private static final IOException ORIGINAL_CHECKED =
            new IOException("business-checked");
    private static final IllegalArgumentException ORIGINAL_UNCHECKED =
            new IllegalArgumentException("business-unchecked");
    private static final AssertionError ORIGINAL_ERROR =
            new AssertionError("business-error");

    private static volatile boolean failTelemetry = true;
    private static volatile long lastElapsedNanos;
    private static int probeCalls;
    private static int probeFailures;

    private static void recordSafely(long startedNanos) {
        try {
            probeCalls++;
            lastElapsedNanos = System.nanoTime() - startedNanos;
            if (failTelemetry) {
                throw new IllegalStateException("simulated telemetry failure");
            }
        } catch (Throwable ignored) {
            probeFailures++;
        }
    }

    private static int intValue() {
        long started = System.nanoTime();
        try {
            return 42;
        } finally {
            recordSafely(started);
        }
    }

    private static long longValue() {
        long started = System.nanoTime();
        try {
            return Long.MAX_VALUE;
        } finally {
            recordSafely(started);
        }
    }

    private static double negativeZero() {
        long started = System.nanoTime();
        try {
            return -0.0d;
        } finally {
            recordSafely(started);
        }
    }

    private static Object sameReference(Object original) {
        long started = System.nanoTime();
        try {
            return original;
        } finally {
            recordSafely(started);
        }
    }

    private static Object nullable() {
        long started = System.nanoTime();
        try {
            return null;
        } finally {
            recordSafely(started);
        }
    }

    private static void completeVoid() {
        long started = System.nanoTime();
        try {
            // Business code that completes normally.
        } finally {
            recordSafely(started);
        }
    }

    private static String checkedFailure() throws IOException {
        long started = System.nanoTime();
        try {
            throw ORIGINAL_CHECKED;
        } finally {
            recordSafely(started);
        }
    }

    private static String uncheckedFailure() {
        long started = System.nanoTime();
        try {
            throw ORIGINAL_UNCHECKED;
        } finally {
            recordSafely(started);
        }
    }

    private static String errorFailure() {
        long started = System.nanoTime();
        try {
            throw ORIGINAL_ERROR;
        } finally {
            recordSafely(started);
        }
    }

    public static void main(String[] args) {
        System.out.println("int=" + intValue());
        System.out.println("longPreserved="
                + (longValue() == Long.MAX_VALUE));
        System.out.println("negativeZeroBits="
                + (Double.doubleToRawLongBits(negativeZero())
                == Double.doubleToRawLongBits(-0.0d)));

        Object original = new Object();
        System.out.println("referenceSame="
                + (sameReference(original) == original));
        System.out.println("nullPreserved=" + (nullable() == null));

        completeVoid();
        System.out.println("voidCompleted=true");

        try {
            checkedFailure();
        } catch (IOException actual) {
            System.out.println("checkedSame=" + (actual == ORIGINAL_CHECKED));
        }

        try {
            uncheckedFailure();
        } catch (IllegalArgumentException actual) {
            System.out.println("uncheckedSame="
                    + (actual == ORIGINAL_UNCHECKED));
        }

        try {
            errorFailure();
        } catch (AssertionError actual) {
            System.out.println("errorSame=" + (actual == ORIGINAL_ERROR));
        }

        System.out.println("probeCalls=" + probeCalls);
        System.out.println("probeFailures=" + probeFailures);
    }
}
~~~

### 5.2. Biên dịch và chạy

Lưu file đúng tên và thực hiện trong thư mục chứa file bằng **JDK 17+**:

~~~bash
javac ExitPreservationDemo.java
java ExitPreservationDemo
~~~

**Stdout đã xác minh bằng JDK 24:**

~~~text
int=42
longPreserved=true
negativeZeroBits=true
referenceSame=true
nullPreserved=true
voidCompleted=true
checkedSame=true
uncheckedSame=true
errorSame=true
probeCalls=9
probeFailures=9
~~~

Lý giải từng nhóm kiểm thử:

- `int=42` và `longPreserved=true` xác nhận giá trị primitive không đổi.
- `negativeZeroBits=true` kiểm tra **raw bit pattern** của `-0.0d`, điều mà `== 0.0d` không phân biệt được.
- `referenceSame=true` xác nhận chính object đầu vào được trả lại, không phải object bằng nhau theo `equals()`.
- `nullPreserved=true` xác nhận không tự biến `null` thành một giá trị khác.
- `voidCompleted=true` xác nhận method `void` không bị telemetry exception làm hỏng đường thành công.
- Ba dòng `checkedSame`, `uncheckedSame`, `errorSame` kiểm tra identity của ngoại lệ checked, unchecked và `Error` bằng toán tử `==`.
- `probeCalls=9`, `probeFailures=9` cho biết tất cả chín lần gọi hook đều cố ý thất bại, nhưng **không một thất bại telemetry nào đổi kết quả từ method nghiệp vụ**.

Đây là mô phỏng tuần tự, không phải một bộ đếm metrics thread-safe: `probeCalls++` và `probeFailures++` trong demo không an toàn khi nhiều thread cùng ghi. Trong ứng dụng đa luồng, dùng cơ chế phù hợp như `LongAdder`, hoặc hàng đợi bounded không chặn, và thử các chế độ thất bại của chúng.

### 5.3. Quan sát bytecode được javac sinh ra

Chạy:

~~~bash
javap -c -p ExitPreservationDemo
~~~

Tùy mã do compiler phát ra, bạn có thể thấy việc lưu tạm giá trị return và các **exception table** để chạy cleanup trong `finally`. Khi biên dịch ví dụ trên bằng JDK 24, `javap` cho thấy các instruction `ireturn`, `lreturn`, `dreturn`, `areturn`, `athrow` và exception tables phù hợp với mô hình của mục 3.

**Không sao chép nguyên vị trí local slot/offset bytecode làm giả định** cho compiler hoặc JDK khác. Bất biến cần kiểm tra là kết quả/throwable quan sát được sau instrumentation, không phải hình dạng bytecode phải giống một output `javap` duy nhất.

## 6. Dùng Byte Buddy: giữ các binding ở chế độ read-only

Khi dùng Byte Buddy `Advice`, exit hook có thể quan sát normal và exceptional exit mà không phải tự tạo exception table. Nhưng **cấu hình mặc định của `@Advice.OnMethodExit` không chạy khi method kết thúc bằng exception**. Muốn quan sát cả hai đường, cần chú ý `onThrowable`.

Ví dụ **minh họa API, không phải chương trình độc lập** (cần dependency Byte Buddy và hàm `Metrics.recordExit(...)` do bạn tự cung cấp):

~~~java
import net.bytebuddy.asm.Advice;

public final class SafeExitAdvice {
    @Advice.OnMethodEnter(suppress = Throwable.class)
    static long enter() {
        return System.nanoTime();
    }

    @Advice.OnMethodExit(
            onThrowable = Throwable.class,
            suppress = Throwable.class)
    static void exit(
            @Advice.Enter long startedNanos,
            @Advice.Thrown(readOnly = true) Throwable originalFailure) {
        Metrics.recordExit(startedNanos, originalFailure);
    }
}
~~~

Các chi tiết quyết định:

1. `onThrowable = Throwable.class` yêu cầu exit advice chạy cả trên đường method ném một `Throwable`. Nếu bỏ cấu hình này, ví dụ có thể **bỏ sót số lần thất bại**.
2. `@Advice.Thrown(readOnly = true)` đọc đối tượng được ném trên exceptional exit; trên normal exit có giá trị `null`. **Không gán** exception khác vào binding và không đặt `readOnly=false` chỉ để dễ thay đổi nó.
3. `suppress = Throwable.class` trên **cả enter và exit advice** là lựa chọn fail-open: khi code telemetry phát sinh Throwable, Byte Buddy suppress nó theo khả năng xử lý của advice. Cần kiểm tra tính khả thi của việc bắt mọi `Error` theo chính sách reliability của môi trường; không có bảo đảm khôi phục khi JVM đã mất khả năng hoạt động.
4. `@Advice.Enter` chuyển dữ liệu từ enter advice sang exit advice; ở đây là mốc đo thời gian, không liên quan tới return value.
5. Không dùng `@Advice.Return(readOnly = false)` hay `@Advice.Thrown(readOnly = false)` khi mục tiêu chỉ là quan sát; chế độ có thể ghi được tạo khả năng thay đổi kết quả nghiệp vụ.
6. Code `Metrics.recordExit(...)` là **phụ thuộc phải khả kiến** trong môi trường class loader/module của method được instrument. Nếu dùng dependency không nạp được, advice vẫn có thể gây lỗi linkage hoặc instrumentation thất bại trước khi có cơ hội suppress tại runtime.

Có thể quan sát return value thông qua `@Advice.Return` trong các advice phù hợp, nhưng cần tính tới method `void`, primitive types, boxing, `null` và giới hạn binding kiểu dữ liệu. Nếu chỉ đo latency và outcome (success/failure), **không cần động tới return value** là phương án ít rủi ro hơn.

**Không đặt `repeatOn` hoặc `skipOn`** khi yêu cầu là giữ nguyên đúng một lần chạy method. Các tùy chọn đó có thể thay đổi số lần thực thi logic nghiệp vụ. Cũng không biến exit advice thành nơi gọi lại method đang instrument — có thể gây recursion và thay đổi kết quả.

### Có nên bắt lỗi telemetry trực tiếp trong advice?

`suppress` là cơ chế do Byte Buddy cung cấp, nhưng production code vẫn nên thiết kế `Metrics.recordExit(...)` theo hướng nhanh, không ném và không tự gọi lại các method bị instrument. Với một số pipeline, một hàm telemetry fail-safe độc lập sẽ dễ kiểm thử hơn việc dựa hoàn toàn vào suppression của framework.

Không nên nhầm lời khuyên trên với việc **suppress Throwable gốc**. `suppress = Throwable.class` áp dụng cho lỗi phát sinh **trong advice**; `@Advice.Thrown(readOnly=true)` dùng để **quan sát lỗi của method**. Hai nguồn lỗi này có vai trò khác nhau.

## 7. Dùng ASM hoặc Class-File API: phải bao phủ cả hai đường thoát

Nếu tự viết bytecode transformer, nên thiết kế như một bài toán **bảo toàn control flow**:

1. Nhận diện descriptor của method để chọn đúng nhóm return instruction và kích thước local slot.
2. Tại mỗi normal return, **lưu đúng giá trị đang ở operand stack**, gọi helper an toàn, nạp lại **chính giá trị đó**, rồi thực hiện return gốc.
3. Tạo đường catch-all phù hợp cho mọi exception **thoát khỏi phần thân nghiệp vụ**, không chỉ các lệnh `ATHROW` tường minh.
4. Trong handler, lưu **chính tham chiếu Throwable** vào local, chạy helper an toàn, nạp lại cùng tham chiếu và `ATHROW`.
5. Không để vùng exception handler bao gồm chính mã đo nếu điều đó gây catch lại lỗi của hook, vòng lặp hoặc nuốt exception.
6. Cập nhật exception table, try ranges, stack-map frames, `maxStack` và `maxLocals` phù hợp class-file version.
7. Giữ nguyên exception handlers và logic cleanup hiện có của method, nhất là `try-with-resources`, `synchronized`, `finally` và các đoạn code có nhiều return.

Các bước trên là **mô hình thiết kế**. Chi tiết triển khai cần dựa trên contract của ASM `AdviceAdapter` hoặc JDK Class-File API phù hợp phiên bản, và phải chạy qua verifier. Không có một thao tác “chèn trước mọi return” chung nào tự xử lý hết **exceptional exits do JVM phát sinh ngầm**.

### Nhóm lệnh return và kích thước local slot

Một lỗi bytecode thường thấy là dùng `ASTORE` cho mọi kết quả. `ASTORE` chỉ áp dụng cho tham chiếu; nếu đang có `long`/`double` trên stack, kiểu và số slot hoàn toàn khác:

~~~text
int/boolean/byte/short/char -> ISTORE / ILOAD -> IRETURN
long                        -> LSTORE / LLOAD -> LRETURN
float                       -> FSTORE / FLOAD -> FRETURN
double                      -> DSTORE / DLOAD -> DRETURN
object/array/null           -> ASTORE / ALOAD -> ARETURN
void                        -> (không cần slot return) -> RETURN
Throwable bất thường        -> ASTORE / ALOAD -> ATHROW
~~~

Đây là **bảng ánh xạ opcode**, không phải một code fence có thể chạy độc lập. Với `float`/`double`, không đổi sang kiểu số khác để “tiện ghi metrics”; phép chuyển đổi có thể làm mất raw-bit identity, NaN payload hoặc dấu của zero. Không gọi `equals()` hay `toString()` của object trả về chỉ để kiểm tra identity.

### Đặc biệt với constructor và static initializer

Constructor `<init>` có quy tắc khởi tạo object và trạng thái `uninitializedThis` trước lời gọi `super(...)`; chèn catch-all hoặc code gọi instance helper sai vị trí có thể dẫn đến lỗi verifier. `<clinit>` cũng có ý nghĩa khởi tạo class đặc biệt. Không dùng công thức dành cho method bình thường như một phép biến đổi mù cho mọi method; cần test riêng hoặc loại khỏi phạm vi điểm đo ban đầu.

Ngoài ra, instrumentation trên `native`/`abstract` method không thể chỉ thêm JVM instructions vào một `Code` attribute vốn không tồn tại. Nếu muốn quan sát chúng, cần kỹ thuật hoặc điểm bao phù hợp khác và giữ đúng contract.

## 8. Các nguy cơ ngoài return value và exception identity

Dù hai bất biến chính được giữ, telemetry vẫn có thể can thiệp vào hành vi khi chạy:

| Nguy cơ | Vì sao nguy hiểm | Hướng kiểm soát |
| --- | --- | --- |
| Hook chạy trước business logic và ném lỗi | Method thật có thể chưa được gọi | Bảo vệ cả enter advice hoặc tránh pre-call failures |
| Hook ghi log đồng bộ/chờ network | Tăng latency, thay lock contention, timeout | Queue có giới hạn, sampling, fail-open khi quá tải |
| Hook gọi chính method đang instrument | Vòng lặp/stack overflow | Reentrancy guard, loại trừ package/helper khỏi transform |
| Hook chạm vào giá trị trả về | Có thể gọi `toString()`/getter gây side effect | Chỉ ghi metadata tối thiểu khi không cần payload |
| Hook thay Throwable hoặc cause/suppressed | Caller nhận exception bị đổi hoặc state khác | `@Advice.Thrown(readOnly=true)`; không mutate exception |
| Hook gọi `Thread.interrupted()` | Lệnh đó có thể **xóa interrupt flag** | Không đọc interrupt bằng API có side effect; cân nhắc `isInterrupted()` |
| Hook đặt trong vùng khóa `synchronized` | Thời gian giữ lock có thể dài hơn | Đo tối thiểu, thử contention, xem xét vị trí hook |
| Hook ghi chung biến đếm không atomic | Lost updates, số liệu sai | `LongAdder`/cơ chế đồng bộ thích hợp |
| Dùng `catch(Exception)` thay vì `catch(Throwable)` trong hook | `Error` từ hook vẫn có thể thay exception gốc | Chọn chính sách fail-open rõ ràng; hiểu giới hạn với fatal errors |
| Thay logic của `try-with-resources` | Thay thứ tự `close()` hoặc suppressed exceptions | Quan sát outcome cuối sau cleanup nghiệp vụ |
| Transformer sinh sai stack maps/handler range | `VerifyError`, `ClassFormatError` hoặc class load thất bại | Verify bytecode và test ở JDK mục tiêu |

**Không có instrumentation hoàn toàn “không ảnh hưởng” theo nghĩa vật lý**: bản thân đo thời gian và cập nhật bộ đếm tiêu tốn CPU, có thể đổi lịch thread hoặc thứ tự interleaving. Mục tiêu thực tế là **giữ nguyên contract nghiệp vụ có thể quan sát** và giảm overhead/rủi ro xuống mức kiểm soát được.

Cũng không thể bảo đảm `finally` chạy khi tiến trình bị kill, `Runtime.halt(...)` dừng JVM, mất nguồn hoặc VM crash. Nói “exit advice chạy trên mọi cách kết thúc trong mọi hoàn cảnh” là quá mức.

## 9. Chiến lược kiểm thử: đối chiếu hành vi trước và sau instrumentation

Bộ test nên so sánh **cùng một method** trước/sau, không chỉ nhìn log “onExit được gọi”. Một ma trận thiết thực:

| Nhóm test | Input / tình huống | Assertion thiết yếu |
| --- | --- | --- |
| Primitive thường | `int 42`, `long Long.MAX_VALUE` | So sánh giá trị chính xác |
| Primitive đặc biệt | `double -0.0`, `NaN`, `float` | So sánh raw bits khi bảo toàn bit pattern là yêu cầu |
| Object | Trả chính object `o` | `assertSame(o, actual)` |
| Array | Trả object mảng ban đầu | `actual == originalArray` |
| Null | Trả `null` | `actual == null` |
| Void | Body kết thúc bình thường | Không có Throwable do probe |
| Checked | `IOException original` | Caught exception `== original` |
| Runtime | `IllegalArgumentException original` | Caught exception `== original` |
| Error | `AssertionError original` | Caught object `== original` |
| Nhiều return branches | Nhiều nhánh if/switch | Mỗi nhánh giữ outcome đúng, probe ghi đúng số lần |
| Exceptional exit ngầm | `throw` từ method được gọi, NPE, lỗi chia cho 0 | Vẫn báo exit và ném đúng object |
| Lỗi telemetry | Hook ném exception ở cả enter/exit | Business outcome không đổi |
| Reentrant instrumentation | Helper cũng bị transform | Không recursion vô hạn |
| Try-with-resources | Body lỗi, `close()` cũng lỗi | Thứ tự và suppressed exceptions của method gốc không bị đổi |
| Synchronized/concurrent | Nhiều thread, exception và return đan xen | Không deadlock hoặc thay lỗi; metrics đúng quy tắc |

Với JUnit, bất biến identity thường được viết là:

~~~java
Throwable actual = org.junit.jupiter.api.Assertions.assertThrows(
        IOException.class, () -> instrumentedMethod());
org.junit.jupiter.api.Assertions.assertSame(originalThrowable, actual);
~~~

Đây là **mảnh test minh họa**, cần dependency JUnit 5, một `instrumentedMethod()` thực sự ném checked exception và biến `originalThrowable` được cung cấp trong test. Nếu dùng Java thuần, toán tử `==` như chương trình phần 5 đủ để kiểm tra identity.

Ngoài identity, hãy so sánh `getCause()` và `getSuppressed()` khi contract yêu cầu chúng không đổi. Không nên tạo stack trace mới hoặc gọi `fillInStackTrace()` trong quá trình đo. Nếu bạn cần assertion về stack frames, phải xét rằng bytecode weaving có thể thay line-number mapping hoặc thêm frame phụ; không đồng nhất mọi khác biệt trình bày stack trace với việc đổi object Throwable.

### Kiểm thử trước/sau bằng reference oracle

Một cách tự động hóa hữu ích là chuẩn bị hai phiên bản cùng logic nghiệp vụ: **không instrument** và **có instrument**. Chạy bộ input giống nhau và ghi outcome theo cặp:

~~~text
Original invocation                 Instrumented invocation
returns primitive V       ---->    returns same V
returns object R          ---->    returns same R (identity)
returns null              ---->    returns null
completes void            ---->    completes void
throws Throwable T        ---->    throws exact same T reference
~~~

Với exception identity, cần chủ động tạo/giữ tham chiếu tới một instance lỗi trước khi ném (như ví dụ phần 5), thay vì so sánh hai exceptions được **tạo độc lập** ở hai lần chạy. Hai lần gọi khác nhau có thể hợp lệ tạo hai Throwable khác nhau; so sánh identity chỉ có ý nghĩa khi cùng một instance được đưa qua đường instrumented.

## 10. Checklist triển khai điểm đo bảo toàn outcome

1. **Chọn đúng phạm vi:** những method cần theo dõi; hạn chế probe vào chính telemetry/logger/class loader.
2. **Xác định hai đường kết thúc:** normal return và exceptional exit **thoát khỏi method**, không chỉ lệnh `ATHROW` tường minh.
3. **Giữ nguyên return:** với primitive bảo toàn giá trị; với object giữ tham chiếu; với `void` không tạo return value.
4. **Giữ nguyên Throwable:** không wrap/replace/suppress, không sửa cause/suppressed/stack trace chỉ để thu metrics.
5. **Giữ code telemetry fail-open:** hook phải kết thúc bình thường trong điều kiện lỗi do chính nó gây ra; có chính sách rõ ràng cho lỗi nghiêm trọng của JVM.
6. **Không chạy lại nghiệp vụ:** không gọi method gốc lần thứ hai để đo, không dùng `repeatOn`/`skipOn` nếu không có yêu cầu riêng.
7. **Bảo toàn bytecode hợp lệ:** locals/stack/handlers/frames và các nguyên tắc đặc biệt của constructor.
8. **Tránh side effects phụ:** không gọi getters/`toString()` của return/Throwable một cách tùy tiện; không clear interrupt flag.
9. **Kiểm thử cả đường lỗi:** checked, unchecked, `Error`, exception phát sinh ngầm, lỗi hook và nhiều return branches.
10. **Đo ảnh hưởng vận hành:** latency, lock contention, reentrancy, sampling và hành vi khi hệ thống telemetry bị quá tải.

Tóm lại: **điểm đo nên lấy dữ liệu từ kết quả cuối cùng của lời gọi, nhưng không nắm quyền quyết định kết quả đó**. Một phương thức sau khi instrument phải tiếp tục trả đúng giá trị hoặc tiếp tục ném đúng đối tượng lỗi ban đầu; các sự cố riêng của telemetry không được thay contract nghiệp vụ.

## 11. Bài tập và đáp án

**Câu 1.** Method trả `Object o` và exit advice gọi `o.toString()` để log. Kết quả trả về vẫn `o`. Có thể khẳng định điểm đo hoàn toàn không thay hành vi không?

**Câu 2.** Một method `int compute()` có `return 7` trong `try` và `return 0` trong `finally`. Caller nhìn thấy gì? Nếu `try` ném một exception thì sao?

**Câu 3.** Hook catch exception gốc `IOException original` rồi `throw new RuntimeException(original)`. Việc bảo toàn “đúng exception object” có được đáp ứng không?

**Câu 4.** Agent chỉ thêm callback trước mỗi opcode `ATHROW`. Có đo được mọi exceptional exit khi method gọi một method khác và method đó ném lỗi không?

**Câu 5.** Đang xử lý `LRETURN`, bytecode transformer lưu giá trị vào local bằng `ISTORE`, sau đó gọi hook. Lỗi thiết kế là gì?

**Câu 6.** Byte Buddy `@Advice.OnMethodExit` không có `onThrowable`. Số lần exception của method có chắc được ghi nhận không?

**Câu 7.** `catch(Throwable probeFailure)` ở trong `safeRecord` có đồng nghĩa mọi exception nghiệp vụ sẽ bị bỏ qua không?

**Câu 8.** Hai exception cùng class, message và stack trace nhưng được tạo bằng hai lần `new`. Có bằng chứng chúng là một object không?

**Câu 9.** Với method trả `double -0.0`, chỉ so `actual == -0.0` có đủ để kiểm tra bit pattern không?

### Đáp án

1. **Không.** `toString()` có thể bị override, ném lỗi hoặc gây side effect. Bảo toàn identity chưa đủ để khẳng định không có tác động khác.
2. Caller nhận **0**; `return 0` trong `finally` ghi đè kết quả và có thể nuốt cả exception của `try`.
3. **Không.** Caller nhận wrapper `RuntimeException` mới, không phải `IOException original`.
4. **Không.** Exception có thể phát sinh hoặc lan truyền từ instruction khác mà method không chứa `ATHROW` tại đường thoát.
5. `long` cần lưu/nạp qua `LSTORE/LLOAD`, chiếm hai local slots; dùng `ISTORE` sai kiểu/stack, có thể bị verifier từ chối.
6. **Không.** Mặc định exit advice không được gọi khi method kết thúc bằng exception; cần cấu hình `onThrowable=Throwable.class` nếu cần đo đường lỗi.
7. **Không.** Catch chỉ bọc hoạt động probe; nghiệp vụ nằm ngoài `safeRecord` và exception gốc tiếp tục truyền nếu finally hoàn tất bình thường.
8. **Không.** Cần toán tử `==`/`assertSame` trên hai tham chiếu tới chính cùng instance.
9. **Không.** `0.0d == -0.0d` là `true`. Muốn kiểm tra bit pattern dùng `Double.doubleToRawLongBits(...)`.

## 12. Tài liệu tham khảo chính thức

- [Java Language Specification 21 — §14.20.2, Execution of try-finally](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.2): quy tắc giữ hoặc thay lý do hoàn tất khi `finally` chạy.
- [Java Virtual Machine Specification 21 — §2.11.8–2.11.9](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.11.8): `ireturn/lreturn/freturn/dreturn/areturn/return` và exceptional completion.
- [JVM Specification 21 — §6.5, athrow](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html#jvms-6.5.athrow): instruction `athrow` và việc truyền tham chiếu Throwable trong handler.
- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): contract của transformer và yêu cầu class bytes hợp lệ.
- [Byte Buddy API 1.18.2 — Advice.OnMethodExit](https://javadoc.io/static/net.bytebuddy/byte-buddy/1.18.2/net/bytebuddy/asm/Advice.OnMethodExit.html): `onThrowable`, `suppress` và semantics của exit advice.
- [Byte Buddy API 1.18.2 — Advice.Thrown](https://javadoc.io/static/net.bytebuddy/byte-buddy/1.18.2/net/bytebuddy/asm/Advice.Thrown.html): binding exception ở exit, chế độ `readOnly` và nguy cơ thay đổi exception.
