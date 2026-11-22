# Java 7 — Multi-catch: Chọn xử lý chung, xử lý riêng hoặc chuyển đổi ngoại lệ

## Mục tiêu học tập

Từ Java 7, một `catch` có thể liệt kê **nhiều kiểu ngoại lệ** cách nhau bằng dấu `|`, ví dụ `catch (IOException | ParseException e)`. Cú pháp **multi-catch** này vẫn được Java hỗ trợ trên các JDK hiện đại. Nó giảm lặp code khi nhiều loại lỗi **thật sự có chung chính sách xử lý**, nhưng không thay thế việc suy nghĩ về ý nghĩa lỗi và hợp đồng của phương thức.

Bài học giải quyết ba quyết định thường gặp khi xử lý ngoại lệ:

1. **Xử lý chung:** Hai hoặc nhiều ngoại lệ khác loại cần cùng một kết quả, thao tác hoặc chính sách, thì gom vào multi-catch.
2. **Xử lý riêng:** Hai ngoại lệ dẫn tới các hành động nghiệp vụ khác nhau (ví dụ yêu cầu sửa dữ liệu so với báo nguồn dữ liệu không sẵn sàng), thì dùng các `catch` riêng.
3. **Chuyển đổi ngoại lệ (exception translation):** Một tầng API cần che giấu chi tiết của tầng thấp và phát ra ngoại lệ mang ý nghĩa phù hợp với caller; giữ lại nguyên nhân gốc qua `cause`.

Ngoài ra, cần biết lúc nào **không xử lý tại đây** mà nên để ngoại lệ lan lên (propagate/rethrow). Đây là phương án hợp lệ, không phải thất bại trong thiết kế.

Sau bài, bạn có thể viết và chạy các ví dụ trên **JDK 17+**, phân biệt việc nhóm cú pháp với việc ra quyết định nghiệp vụ, bảo toàn nguyên nhân lỗi và tránh các lỗi multi-catch thường gặp. Những kiến thức này đều còn áp dụng hiện nay.

## 1. Nền tảng: `catch` chỉ có ý nghĩa khi gắn với một chính sách

Khi một thao tác đọc hoặc chuyển đổi dữ liệu có thể ném `IOException` hay `ParseException`, lập trình viên phải quyết định ai chịu trách nhiệm về lỗi. Hai kiểu ngoại lệ được bắt không có nghĩa mặc nhiên chúng cần cùng cách phản ứng.

```java
try {
    process();
} catch (IOException | ParseException e) {
    // Chỉ đúng khi cả hai lỗi có cùng chính sách xử lý.
}
```

Đây là **đoạn minh họa**, trong đó `process()` là một thao tác giả định có thể ném hai kiểu ngoại lệ; không phải lớp Java độc lập. Cú pháp `catch (A | B e)` chỉ làm một điều: nếu một ngoại lệ được ném ra **thuộc `A` hoặc `B` (kể cả lớp con tương ứng)** và tới được `catch` này, cùng một thân `catch` sẽ xử lý nó.

Phần quan trọng nhất là **thân `catch` làm gì**:

- Có đủ cơ sở để phục hồi/đưa ra phản hồi cuối cùng hay không?
- Lỗi có phải tạm thời, lỗi dữ liệu, lỗi cấu hình hay lỗi lập trình? Đừng suy diễn chính sách chỉ từ tên lớp exception.
- Caller có cần biết khác biệt giữa từng nguyên nhân không?
- Có nên chuyển đổi lỗi thành một ngoại lệ cấp nghiệp vụ/tầng ứng dụng thay vì ném một `IOException` thấp tầng qua toàn bộ kiến trúc?
- Nếu không xử lý được, giữ nguyên ngoại lệ và `throw e` có tốt hơn không?
- Một lỗi đã được ghi log ở tầng nào? Tránh ghi lặp tại mọi tầng.

**Quy tắc cốt lõi:** Nên chọn **chính sách xử lý trước, cú pháp `catch` sau**. Multi-catch là công cụ thể hiện quyết định, không tự quyết định thay người lập trình.

## 2. Ma trận lựa chọn nhanh

| Tình huống | Lựa chọn | Tại sao |
| --- | --- | --- |
| `IOException` và `ParseException` đều được phép trả cùng một kết quả `UNAVAILABLE` tại ranh giới hiện tại | Multi-catch với một thân xử lý chung | Giảm logic trùng nhau; có chủ ý không phân biệt hai lỗi tại boundary |
| Đầu vào sai định dạng cần `FIX_INPUT`, lỗi nguồn tạm thời cần `RETRY_LATER` | Hai `catch` riêng | Chính sách và hướng dẫn phục hồi khác nhau |
| Tầng truy cập dữ liệu ném exception thấp tầng, còn API công khai cam kết một `RequestLoadException` | Bắt và **chuyển đổi**, thường có thể dùng multi-catch | Giữ abstraction của API; tạo ngữ cảnh nghiệp vụ và giữ `cause` |
| Tầng hiện tại không thể xử lý đúng, caller đã biết cách giải quyết `IOException`/`ParseException` | Rethrow/propagate, có thể multi-catch nếu cần thao tác chung trước khi ném | Không giả vờ xử lý hoặc làm mất thông tin gốc |
| Một ngoại lệ cần retry, ngoại lệ khác phải dừng ngay; chỉ chung thao tác log | Có thể dùng `catch` riêng rồi gọi helper chung cho log | Không ép chung chính sách chỉ để tránh lặp vài dòng |
| Có thể xử lý tất cả lỗi theo một fallback đã được hợp đồng định nghĩa | Có thể multi-catch **các kiểu đã xác định** | Tránh bắt quá rộng `Exception`/`Throwable` |
| Cần xử lý riêng một subtype của `IOException` | `catch` subtype trước, `catch IOException` sau | Multi-catch không cho ghép một subtype với superclass của nó |

Ba hướng **không hoàn toàn loại trừ nhau**. Ví dụ, “chuyển đổi ngoại lệ” là **hành động**, còn “multi-catch” là **cách gom những kiểu ngoại lệ chịu cùng hành động**. Bạn có thể dùng `catch (IOException | ParseException e)` để ném cùng một exception cấp nghiệp vụ nếu hợp đồng mới cho phép.

Trong ví dụ “lỗi I/O cần retry”, đó là **quy ước của bài toán giả lập**. Ngoài đời, không phải mọi `IOException` đều có thể retry an toàn. Lỗi đĩa hỏng, thiếu quyền truy cập hoặc kết nối tạm đứt có hướng xử lý khác nhau; chỉ retry khi nguồn lỗi, tính idempotent và giới hạn retry cho phép.

## 3. Phương án A — Xử lý chung bằng multi-catch

### 3.1. Khi nào đúng?

Giả sử một bước thăm dò trạng thái cho phép trả `UNAVAILABLE` nếu **không đọc được nguồn** hoặc **không phân tích được bản ghi**. Ở đúng điểm gọi này, hợp đồng có thể cố ý gom cả hai thành một trạng thái không sẵn sàng; tầng khác vẫn có thể theo dõi nguyên nhân nếu cần.

Nếu hai `catch` riêng đều chỉ `return "UNAVAILABLE";` thì multi-catch là cách diễn đạt gọn, tránh lặp. Nhưng nếu UI cần phân biệt “sửa dữ liệu” với “thử lại”, chính sách gom ấy là không phù hợp — hãy dùng phương án B.

### Chương trình đầy đủ: `SharedPolicyDemo.java`

```java
import java.io.IOException;
import java.text.ParseException;

public final class SharedPolicyDemo {
    private static String execute(String scenario)
            throws IOException, ParseException {
        if ("io".equals(scenario)) {
            throw new IOException("source unavailable");
        }
        if ("parse".equals(scenario)) {
            throw new ParseException("invalid record", 0);
        }
        return "READY";
    }

    private static String handle(String scenario) {
        try {
            return execute(scenario);
        } catch (IOException | ParseException e) {
            return "UNAVAILABLE";
        }
    }

    public static void main(String[] args) {
        System.out.println("io=" + handle("io"));
        System.out.println("parse=" + handle("parse"));
        System.out.println("ok=" + handle("ok"));
    }
}
```

Chạy ở thư mục chứa tệp:

```bash
javac --release 17 -encoding UTF-8 SharedPolicyDemo.java
java SharedPolicyDemo
```

Output chính xác:

```text
io=UNAVAILABLE
parse=UNAVAILABLE
ok=READY
```

**Giải thích:**

- `execute("io")` ném `IOException` và `execute("parse")` ném `ParseException`.
- `catch (IOException | ParseException e)` bắt đúng một trong hai kiểu ngoại lệ (hoặc subtype của một kiểu), không bắt mọi lỗi tồn tại trong chương trình.
- Chính sách của `handle` trả cùng `UNAVAILABLE` cho cả hai nhánh. Không cần đoán loại lỗi tại runtime để quyết định, vì chính sách đã thống nhất.
- Trường hợp `ok` đi qua `return "READY";` trong `try`, không vào `catch`.
- Ví dụ chủ ý mô phỏng việc chuyển lỗi thành **trạng thái trả về**, phù hợp với hợp đồng giả định của một status probe. **Không áp dụng tùy tiện** cho các thao tác cần báo lỗi chính xác; nếu mất nguyên nhân gây khó sửa lỗi, hãy log ở một boundary phù hợp hoặc chuyển đổi ngoại lệ có `cause`.

### 3.2. Multi-catch tốt hơn `catch (Exception e)` ở đâu?

```java
catch (IOException | ParseException e) {
    // Chỉ hai nhóm ngoại lệ đã được cân nhắc.
}
```

khác với:

```java
catch (Exception e) {
    // Rộng hơn, có thể bắt cả lỗi lập trình ngoài dự kiến.
}
```

Hai đoạn trên đều là **minh họa đặt sau một `try`**, không phải chương trình hoàn chỉnh. `catch (Exception e)` có thể bắt thêm `NullPointerException`, `IllegalArgumentException` cùng nhiều loại khác vốn không thuộc chính sách fallback. Việc mở rộng phạm vi bắt có thể **che giấu bug**. Chỉ bắt những kiểu mà tầng hiện tại biết cách xử lý đúng.

## 4. Phương án B — Xử lý riêng khi ý nghĩa lỗi khác nhau

Nếu hệ thống phân biệt **nguồn tạm thời không sẵn sàng** và **bản ghi sai định dạng**, người dùng hoặc tác vụ gọi có thể cần hai hành động khác nhau:

- Lỗi nguồn I/O theo hợp đồng minh họa: đề nghị `RETRY_LATER`.
- Lỗi định dạng: báo `FIX_INPUT` để sửa dữ liệu trước khi thử lại.
- Thành công: `ACCEPTED`.

Dùng hai `catch` riêng giúp thân code diễn đạt trực tiếp sự khác biệt. Không gộp chúng chỉ vì cả hai cùng là checked exception.

### Chương trình đầy đủ: `DistinctPolicyDemo.java`

```java
import java.io.IOException;
import java.text.ParseException;

public final class DistinctPolicyDemo {
    private static String execute(String scenario)
            throws IOException, ParseException {
        if ("io".equals(scenario)) {
            throw new IOException("source unavailable");
        }
        if ("parse".equals(scenario)) {
            throw new ParseException("invalid record", 0);
        }
        return "ACCEPTED";
    }

    private static String handle(String scenario) {
        try {
            return execute(scenario);
        } catch (IOException e) {
            return "RETRY_LATER";
        } catch (ParseException e) {
            return "FIX_INPUT";
        }
    }

    public static void main(String[] args) {
        System.out.println("io=" + handle("io"));
        System.out.println("parse=" + handle("parse"));
        System.out.println("ok=" + handle("ok"));
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 DistinctPolicyDemo.java
java DistinctPolicyDemo
```

Output:

```text
io=RETRY_LATER
parse=FIX_INPUT
ok=ACCEPTED
```

**Giải thích:** Cùng hai ngoại lệ như `SharedPolicyDemo`, nhưng **chính sách mới tạo kết quả khác nhau**. `IOException` dẫn tới một kế hoạch retry theo hợp đồng giả lập; `ParseException` buộc sửa input. Cú pháp hai `catch` không phải “lỗi thời” — nó vẫn là lựa chọn đúng khi ý nghĩa nghiệp vụ khác nhau.

Trong ứng dụng thật, đừng xem `IOException` đồng nghĩa với “mạng chập chờn”. Có thể cần phân loại chi tiết hơn theo **bối cảnh**, subtype, error code, tính lặp lại an toàn của thao tác và deadline. Nếu không đủ thông tin để quyết định retry, tốt hơn nên **propagate** hoặc dùng lỗi domain cụ thể, thay vì trả nhãn sai cho caller.

### 4.1. Hai `catch` có thể chia sẻ helper mà vẫn giữ chính sách riêng

```java
try {
    process();
} catch (IOException e) {
    recordFailure(e);
    scheduleRetry(e);
} catch (ParseException e) {
    recordFailure(e);
    rejectInput(e);
}
```

Đây là đoạn mô tả **trong một ngữ cảnh có sẵn các helper `process`, `recordFailure`, `scheduleRetry`, `rejectInput`**, không phải chương trình chạy độc lập. Cả hai nhánh có thao tác chung `recordFailure` nhưng **chính sách phục hồi khác nhau**. Gọi một helper chung tốt hơn việc gộp thành một `catch` rồi viết chuỗi `if (e instanceof ...)` chỉ để chia tách lại ý nghĩa.

Các helper trong ứng dụng thật cần dùng một cơ chế quan sát lỗi nhất quán. Tránh log cùng một stack trace ở cả tầng repository, service và API nếu tầng bên ngoài đã chịu trách nhiệm báo cáo.

### 4.2. Thứ tự bắt khi có quan hệ kế thừa

Với các subtype khác nhau của cùng nhóm ngoại lệ, nhánh cụ thể phải đi trước nhánh bao quát:

```java
try {
    readFile();
} catch (java.io.FileNotFoundException e) {
    // Chính sách cho trường hợp không tìm thấy tệp.
} catch (IOException e) {
    // Chính sách cho các lỗi I/O còn lại.
}
```

Đây là đoạn minh họa; `readFile()` phải được định nghĩa trong chương trình cụ thể. `FileNotFoundException` là subtype của `IOException`. Nếu đặt `catch (IOException e)` trước, nhánh `FileNotFoundException` phía sau sẽ không còn khả năng được chọn và gây lỗi biên dịch.

**Không viết** `catch (FileNotFoundException | IOException e)`. Multi-catch **không cho phép các lựa chọn có quan hệ subtype/supertype với nhau**; `IOException` đã bao gồm `FileNotFoundException`. Khi chỉ cần chính sách chung, `catch (IOException e)` là đủ. Khi cần chính sách riêng, dùng hai `catch` đúng thứ tự như trên.

## 5. Phương án C — Chuyển đổi ngoại lệ để giữ abstraction API

Trong kiến trúc nhiều tầng, một tầng ứng dụng có thể không muốn caller biết `IOException` hay `ParseException` của tầng tải dữ liệu. Caller chỉ cần hiểu lỗi **không thể nạp yêu cầu**.

Khi đó, thay vì nuốt lỗi hoặc phơi bày chi tiết tầng thấp, có thể chuyển đổi thành `RequestLoadException`. Điều quan trọng là **giữ nguyên cause** qua constructor `super(message, cause)` để chẩn đoán vẫn truy ra ngoại lệ gốc.

### Chương trình đầy đủ: `TranslatePolicyDemo.java`

```java
import java.io.IOException;
import java.text.ParseException;

public final class TranslatePolicyDemo {
    static final class RequestLoadException extends RuntimeException {
        RequestLoadException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    private static String load(String scenario) {
        try {
            return readRaw(scenario);
        } catch (IOException | ParseException e) {
            throw new RequestLoadException("request load failed", e);
        }
    }

    private static String readRaw(String scenario)
            throws IOException, ParseException {
        if ("io".equals(scenario)) {
            throw new IOException("source unavailable");
        }
        if ("parse".equals(scenario)) {
            throw new ParseException("invalid record", 0);
        }
        return "READY";
    }

    public static void main(String[] args) {
        for (String scenario : new String[]{"ok", "io", "parse"}) {
            try {
                System.out.println(scenario + "=" + load(scenario));
            } catch (RequestLoadException e) {
                System.out.println(scenario + "=" + e.getMessage()
                        + "; cause=" + e.getCause().getClass().getSimpleName());
            }
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 TranslatePolicyDemo.java
java TranslatePolicyDemo
```

Output:

```text
ok=READY
io=request load failed; cause=IOException
parse=request load failed; cause=ParseException
```

**Ý nghĩa của ba lớp:**

1. `readRaw` là điểm có thể sinh checked exception gắn với thao tác thấp tầng.
2. `load` quy đổi hai nguyên nhân thành một ngoại lệ **tầng ứng dụng**. Nó vẫn dùng multi-catch vì cả hai cùng dẫn tới chính sách “không nạp được yêu cầu”.
3. Caller bắt `RequestLoadException` và không cần khai báo `throws IOException, ParseException` ở `load`, vì trong ví dụ `RequestLoadException` được định nghĩa là subclass của `RuntimeException`.
4. `e.getCause()` vẫn cho biết lỗi gốc; điều này khác với `new RequestLoadException("request load failed", null)` hoặc tạo ngoại lệ mới mà bỏ qua cause.

### 5.1. Khi nào chuyển thành checked, khi nào thành unchecked?

Không có quy tắc “mọi exception thấp tầng phải biến thành runtime exception”. Đây là **quyết định hợp đồng của API**:

- **Checked domain exception:** phù hợp nếu caller được thiết kế để nhận diện và có hành động phục hồi cụ thể bắt buộc cân nhắc; chữ ký phương thức ghi `throws YourCheckedException`.
- **Unchecked domain exception:** có thể phù hợp khi caller không có cách phục hồi tại điểm gọi và chính sách thường được xử lý ở ranh giới request/job. Vẫn cần mô tả hợp đồng và tránh giấu lỗi ngoài dự kiến.
- **Giữ nguyên loại gốc:** phù hợp khi giao diện của tầng đang gọi cố ý cung cấp thông tin kỹ thuật đó và caller thực sự xử lý được.
- **Chuyển thành kết quả thường (`Result`/status/enum):** chỉ phù hợp nếu thất bại là một trạng thái nghiệp vụ được dự kiến, có biểu diễn minh bạch. Không tự động trả success giả.

**Không đổi checked thành unchecked chỉ để “cho code compile”.** Hãy xác định caller cần biết điều gì, ở tầng nào có khả năng xử lý và yêu cầu của API là gì.

### 5.2. Bảo toàn ngữ cảnh và tránh đánh mất cause

Một bản dịch tốt có thông điệp phù hợp cấp nghiệp vụ, ví dụ `"request load failed"`, và giữ nguyên `Throwable` gốc trong cause. Nếu cần thêm ID của yêu cầu hoặc tên nguồn để truy vết, chỉ đưa thông tin **không nhạy cảm** vào message/log. Tránh lộ dữ liệu nội bộ, đường dẫn bí mật hoặc chi tiết không phù hợp ra response công khai.

Hạn chế **dịch lặp qua nhiều tầng** khi không tăng thêm ngữ nghĩa, chẳng hạn liên tục bọc `AException` vào `BException` rồi `CException` mà không có ranh giới hợp đồng rõ. Nếu nhiều tầng đều log và bọc, stack trace khó đọc và cảnh báo bị nhân lên.

### 5.3. Chuyển đổi khác với rethrow

```java
catch (IOException | ParseException e) {
    throw e; // Lan truyền cùng đối tượng ngoại lệ gốc.
}
```

so với:

```java
catch (IOException | ParseException e) {
    throw new RequestLoadException("request load failed", e);
    // Ném đối tượng ngoại lệ mới, loại mới, có cause trỏ đến e.
}
```

Đây là **hai nhánh thay thế mang tính minh họa**; đoạn thứ hai cần lớp `RequestLoadException` như đã định nghĩa trong chương trình đầy đủ. `throw e` bảo toàn loại và đối tượng exception, nhưng caller vẫn phải xử lý checked exceptions theo quy tắc Java. `throw new ...` thay loại ngoại lệ mà caller thấy, vì vậy phải được chọn có chủ đích.

## 6. Phương án D — Không xử lý tại đây: rethrow có kiểm soát

Một tầng trung gian có thể cần thực hiện thao tác quan sát chung (ví dụ ghi metric) rồi để ngoại lệ **đến caller có đủ ngữ cảnh**. Java hỗ trợ rethrow mà không cần gói lại mọi lần.

### Chương trình đầy đủ: `RethrowPolicyDemo.java`

```java
import java.io.IOException;
import java.text.ParseException;

public final class RethrowPolicyDemo {
    private static void parse(String scenario)
            throws IOException, ParseException {
        try {
            if ("io".equals(scenario)) {
                throw new IOException("offline");
            }
            if ("parse".equals(scenario)) {
                throw new ParseException("bad request", 0);
            }
        } catch (IOException | ParseException e) {
            System.out.println("observed=" + e.getClass().getSimpleName());
            throw e;
        }
    }

    public static void main(String[] args) {
        for (String scenario : new String[]{"io", "parse", "ok"}) {
            try {
                parse(scenario);
                System.out.println(scenario + "=OK");
            } catch (IOException | ParseException e) {
                System.out.println(scenario + "=PROPAGATED");
            }
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 RethrowPolicyDemo.java
java RethrowPolicyDemo
```

Output:

```text
observed=IOException
io=PROPAGATED
observed=ParseException
parse=PROPAGATED
ok=OK
```

**Giải thích:**

- `parse` quan sát loại exception nhưng không cố làm nó biến mất; `throw e` đẩy lỗi cho caller.
- Caller `main` bắt cùng hai loại ngoại lệ và có thể đưa ra quyết định của mình.
- Chữ ký `parse` ghi `throws IOException, ParseException`; đó là một phần của hợp đồng compile-time với checked exceptions.
- Multi-catch từ Java 7 cho phép biểu diễn chung thân `catch`. Khi rethrow, trình biên dịch áp dụng phân tích checked exception theo những loại có thể được ném; ví dụ đã biên dịch được trên JDK 17.
- Hãy thận trọng khi log trước `throw e`: nếu caller cũng log cùng stack trace, hệ thống có thể ghi lỗi hai lần. Một metric không chứa dữ liệu nhạy cảm có thể có ích, nhưng vẫn cần quy ước quan sát lỗi nhất quán.

**Phương án “để ngoại lệ tự lan lên” cũng hợp lệ:** Nếu phương thức chỉ ủy quyền và không có việc gì cần làm tại đây, có thể không viết `try/catch` ở tầng trung gian, khai báo/để exception lan theo hợp đồng thích hợp. Đừng thêm `catch` chỉ để `throw e` mà không tạo thêm giá trị.

## 7. Quy tắc cú pháp multi-catch cần nhớ

### 7.1. Cú pháp và ý nghĩa của dấu `|`

```java
catch (IOException | ParseException e) {
    // Xử lý chung.
}
```

Đoạn này là một `catch` của một `try` bên ngoài; **không viết** `catch (IOException e | ParseException e)` vì chỉ có **một** tên biến `e` đứng sau danh sách các type thay thế.

`IOException` và `ParseException` là hai loại không có quan hệ kế thừa trực tiếp. Mỗi loại có thể có các subtype phù hợp được bắt. Việc liệt kê hai loại là quy tắc **OR khi bắt ngoại lệ**, không phải giao kiểu dữ liệu hay phép toán bitwise trên giá trị số.

### 7.2. Không kết hợp hai lựa chọn có quan hệ kế thừa

```java
// CỐ Ý SAI: FileNotFoundException là subclass của IOException.
catch (java.io.FileNotFoundException | IOException e) {
    System.out.println(e.getMessage());
}
```

Ví dụ này chỉ là **mảnh mã cố ý sai** và không thể biên dịch. Theo Java Language Specification, nếu một kiểu trong danh sách là subtype của kiểu khác cũng trong danh sách, multi-catch bị từ chối. Thay bằng `catch (IOException e)` nếu muốn chung cách xử lý; hoặc viết hai `catch` riêng với nhánh cụ thể đứng trước nếu muốn chính sách khác nhau.

### 7.3. Tham số multi-catch ngầm là `final`

```java
// CỐ Ý SAI: không được gán lại tham số multi-catch.
catch (IOException | ParseException e) {
    e = new IOException("replacement");
}
```

Đây là **mảnh code cố ý sai**. Biến `e` trong multi-catch **được xem như khai báo `final`**; compiler không cho gán lại. Điều này không cấm gọi `e.getMessage()`, `e.getCause()` hay `throw e`. Cũng không cấm tạo exception **mới** với `new DomainException(..., e)` và ném nó, vì đó không phải gán lại `e`.

Trong multi-catch, kiểu tĩnh dùng được của `e` dựa trên kiểu chung phù hợp của các alternative. Không thể tùy tiện gọi method chỉ có trên riêng `IOException` mà không có ở nhóm type chung. Nếu hành vi của nhánh thật sự cần method riêng, hai `catch` thường dễ diễn đạt hơn.

### 7.4. Checked exceptions vẫn được kiểm tra

Multi-catch không vô hiệu hóa nguyên tắc checked exception:

- Một phương thức có thể ném checked exception chưa được bắt phải khai báo `throws` tương ứng hoặc chuyển đổi thành loại exception khác phù hợp.
- `catch (IOException | ParseException e)` chỉ bắt những loại được liệt kê hoặc subtype tương ứng, không tự xử lý một checked exception khác.
- `throw e` có thể yêu cầu hợp đồng `throws IOException, ParseException` ở hàm bao quanh.
- Việc đổi thành `catch (Exception e)` để tránh nghĩ về kiểu exception không phải cách làm tốt; còn có thể bắt nhầm các runtime exception chưa được dự kiến.

### 7.5. Thứ tự `catch` vẫn quan trọng

Các `catch` của một `try` được xét theo thứ tự. Khi có nhánh subtype và supertype, đặt subtype trước. Với hai ngoại lệ không liên quan như `IOException` và `ParseException`, việc chọn chung hay riêng được quyết định bởi chính sách; không cần sắp xếp giả theo “độ nghiêm trọng” của class name.

### 7.6. Thời điểm dọn tài nguyên

Nếu thao tác có file, stream hoặc resource `AutoCloseable`, dùng **try-with-resources** để đóng tài nguyên đúng cách; đừng xem multi-catch là cơ chế giải quyết việc đóng. Hai tính năng có thể phối hợp:

```java
try (java.io.BufferedReader reader =
             java.nio.file.Files.newBufferedReader(path)) {
    // Đọc/parse dữ liệu, có thể phát sinh IOException hoặc exception khác.
} catch (IOException | ParseException e) {
    // Áp dụng chính sách khi các ngoại lệ này thực sự có thể xảy ra.
}
```

Đây là **minh họa có các biến/hành động `path` và phần parse chưa được định nghĩa**, không phải chương trình độc lập. Trong chương trình thực tế, `ParseException` phải có khả năng được ném từ phần try (hoặc từ method mà nó gọi) thì kiểu checked này mới thích hợp trong `catch`. Try-with-resources giải quyết vòng đời tài nguyên; multi-catch giải quyết nhóm ngoại lệ. Không dùng `finally` thủ công để đóng tài nguyên khi try-with-resources diễn đạt đúng yêu cầu.

## 8. Cách quyết định qua một luồng câu hỏi

Khi gặp nhiều `catch` lặp code, đừng ngay lập tức dùng `|`. Hãy trả lời theo thứ tự:

**Câu 1 — Tầng hiện tại có đủ ngữ cảnh để quyết định không?**

- **Không:** để exception lan lên hoặc thêm thông tin cần thiết bằng một domain exception có `cause`.
- **Có:** xác định chính xác hành động phục hồi/kết quả với từng nhóm exception.

**Câu 2 — Mọi kiểu ngoại lệ đang cân nhắc có thật sự cùng hành động?**

- **Có:** dùng multi-catch với danh sách type cụ thể nếu các loại không có quan hệ subtype với nhau.
- **Không:** dùng nhiều `catch` riêng; chỉ gom phần phụ trợ (log/metric) vào helper nếu hữu ích.

**Câu 3 — Caller có nên biết loại exception thấp tầng không?**

- **Có, vì caller có logic xử lý đã định nghĩa:** giữ nguyên/rethrow các exception đó.
- **Không, vì hợp đồng API mô tả lỗi nghiệp vụ/tầng ứng dụng:** chuyển đổi sang exception có tên phù hợp và gắn `cause`.

**Câu 4 — Có đang vô tình che giấu lỗi không?**

- Trả kết quả success giả sau exception có thể khiến dữ liệu hỏng bị bỏ qua.
- Bắt `Exception` rộng vì ngại khai báo type có thể làm mất tín hiệu lỗi lập trình.
- Log rồi nuốt lỗi mà caller vẫn tưởng thành công có thể gây sai lệch giao dịch.

**Câu 5 — Cần test điều gì trước khi chấp nhận thiết kế?**

- Phản hồi cho từng loại lỗi, không chỉ happy path.
- Đúng kiểu ngoại lệ được propagate hoặc translate.
- `getCause()` trỏ về lỗi gốc trong trường hợp translation.
- Không có branch bắt trùng/hierarchy sai; checked exception được trình biên dịch xác nhận.
- Không retry hoặc commit thao tác nhiều lần ngoài mong muốn.

Có thể tóm lại:

| Quyết định thực tế | Tín hiệu chọn |
| --- | --- |
| Shared | Cùng mục đích nghiệp vụ, cùng action, cùng kết quả |
| Distinct | Khác khả năng phục hồi, trách nhiệm caller, thông báo hoặc hành động |
| Translate | Đổi từ mô hình lỗi nội bộ sang hợp đồng của tầng gọi, giữ cause |
| Rethrow | Chưa xử lý được ở đây, giữ nguyên type/object và giao cho caller |

## 9. Ma trận kiểm thử bắt buộc và kết quả tham chiếu

Bốn chương trình trên sử dụng đầu vào cố định, không cần file thật hay mạng. Bạn có thể kiểm tra bằng lệnh `javac --release 17` để bảo đảm không dựa vào cú pháp quá mới so với mức tương thích Java 17.

| Chương trình | Đầu vào/kịch bản | Kỳ vọng | Ý nghĩa |
| --- | --- | --- | --- |
| `SharedPolicyDemo` | `io` | `UNAVAILABLE` | Xử lý chung IOException |
| `SharedPolicyDemo` | `parse` | `UNAVAILABLE` | Xử lý chung ParseException |
| `SharedPolicyDemo` | `ok` | `READY` | Không vào catch khi thành công |
| `DistinctPolicyDemo` | `io` | `RETRY_LATER` | Chính sách riêng cho nguồn |
| `DistinctPolicyDemo` | `parse` | `FIX_INPUT` | Chính sách riêng cho định dạng |
| `DistinctPolicyDemo` | `ok` | `ACCEPTED` | Không đánh đồng thành công/thất bại |
| `TranslatePolicyDemo` | `io` | `RequestLoadException` có cause `IOException` | Dịch loại và giữ lỗi gốc |
| `TranslatePolicyDemo` | `parse` | `RequestLoadException` có cause `ParseException` | Dịch loại và giữ lỗi gốc |
| `TranslatePolicyDemo` | `ok` | `READY` | Không tạo exception khi thành công |
| `RethrowPolicyDemo` | `io` và `parse` | Caller nhận cùng nhóm lỗi đã ném | Giữ nguyên ngoại lệ để caller xử lý |
| `RethrowPolicyDemo` | `ok` | `OK` | Không phát sinh false failure |

### Kiểm chứng âm bằng `javac`

Ba lỗi sau cần được phát hiện bằng **compile test**, không phải chờ đến runtime:

1. `catch (FileNotFoundException | IOException e)` — **FAIL** do hai alternative có quan hệ subclass/superclass.
2. Gán `e = new IOException()` bên trong `catch (IOException | ParseException e)` — **FAIL** vì `e` là tham số ngầm `final`.
3. Một phương thức `throws IOException` nhưng lại có `ParseException` chưa bị bắt và có thể thoát ra — **FAIL** do hợp đồng checked exceptions không đầy đủ.

Các tình huống cố ý sai nên thử trong **file độc lập** và biên dịch riêng từng ca. Thông điệp chẩn đoán của compiler khác nhau theo phiên bản; điều cần xác nhận là mã biên dịch trả trạng thái thất bại và đúng nguyên nhân. Không đưa chúng vào cùng file chứa các chương trình mẫu chạy thành công.

### Kiểm thử việc chuyển đổi cause

Với `TranslatePolicyDemo`, thử sửa:

```java
throw new RequestLoadException("request load failed", e);
```

thành phiên bản bỏ cause (nếu constructor cho phép). Hỏi: caller có còn quan sát được `IOException`/`ParseException` từ `getCause()` không? Với phiên bản chuẩn ở trên, có; đó là một điều kiện quan trọng của translation đáng tin cậy. Đừng thực hiện thay đổi này trong mã sản phẩm chỉ để “giảm thông tin lỗi”.

## 10. Những anti-pattern quan trọng

### 10.1. Gom vì “cho ngắn” dù chính sách khác nhau

```java
catch (IOException | ParseException e) {
    return "RETRY_LATER";
}
```

Nếu parse sai định dạng không thể tự hết khi retry, chính sách này có thể khiến hệ thống thử đi thử lại vô ích. Nó chỉ đúng khi **tài liệu nghiệp vụ** cho phép gộp cả hai vào retry; không thể suy ra từ cú pháp.

### 10.2. Bắt `Exception` rồi trả thành công

```java
catch (Exception e) {
    return "SUCCESS";
}
```

Trong một workflow có side effect, đây là cách làm sai lệch trạng thái. Chỉ trả kết quả thành công khi nghiệp vụ thật sự đã hoàn tất theo hợp đồng, không phải vì muốn giấu stack trace hoặc làm test xanh.

### 10.3. Chuyển exception mà bỏ nguyên nhân

```java
// Mất nguyên nhân gốc nếu constructor không lưu cause.
throw new IllegalStateException("request load failed");
```

Đặt trong `catch`, dòng này xóa mất liên kết nguyên nhân tới exception ban đầu. Khi chuyển đổi, ưu tiên constructor nhận `cause` phù hợp:

```java
throw new IllegalStateException("request load failed", e);
```

Hai dòng trên là ví dụ minh họa; dòng thứ hai phải ở scope có biến `e` là nguyên nhân thực tế.

### 10.4. Đổi mọi checked exception thành unchecked

Việc bọc mọi `IOException`, `ParseException` và exception khác trong `RuntimeException` chung có thể làm mất các quyết định phục hồi mà caller vốn phải xử lý. Chỉ translate tại ranh giới có ý nghĩa, với loại thông báo và hợp đồng rõ.

### 10.5. Catch trùng quan hệ subclass

`catch (FileNotFoundException | IOException e)` là không hợp lệ. Đừng giải quyết bằng `catch (Exception e)`. Nếu cùng chính sách, dùng `catch (IOException e)`; nếu khác, tách hai nhánh với subtype trước.

### 10.6. Ghi log ở mọi tầng hoặc nuốt lỗi hoàn toàn

Một exception đi qua nhiều tầng có thể bị log lặp lại 3–4 lần dù chỉ là một sự cố. Ngược lại, `catch` rỗng không để lại dấu vết khiến hệ thống khó chẩn đoán. Chọn đúng nơi xử lý, quan sát và propagate theo kiến trúc ứng dụng.

### 10.7. Retry không kiểm soát

Trả `RETRY_LATER` hoặc gọi retry không đồng nghĩa với khả năng chạy lại an toàn. Phải cân nhắc giới hạn lần thử, backoff, timeout và idempotency. Exception type cung cấp **một phần** thông tin; không đủ thay thế quyết định về tác dụng phụ.

### 10.8. Dùng `instanceof` trong một multi-catch để xây lại hàng loạt nhánh

```java
catch (IOException | ParseException e) {
    if (e instanceof IOException) {
        // Xử lý riêng cho I/O.
    } else {
        // Xử lý riêng cho parsing.
    }
}
```

Đoạn minh họa này không sai cú pháp, nhưng khi hai hành động thật sự khác nhau và không có shared policy, **hai `catch` riêng** thường dễ đọc và bảo trì hơn. Nếu có một bước chung rồi bước riêng phức tạp, cân nhắc helper hoặc refactor ở tầng trách nhiệm thay vì dựng cây `instanceof` khó hiểu.

## 11. Bài tập tự luyện

**Bài 1 — Chọn shared hay distinct.** Một bộ đọc cấu hình gặp `IOException` vì file không sẵn sàng hoặc `ParseException` vì cấu trúc file sai. Caller có thể sửa file cấu hình, nhưng không thể sửa kết nối tới ổ lưu trữ. Có nên trả một mã `RETRY_LATER` chung? Giải thích điều kiện để dùng multi-catch.

**Bài 2 — Sửa chính sách.** Dùng `SharedPolicyDemo` làm cơ sở để tạo phiên bản trả `RETRY_LATER` cho `IOException` và `FIX_INPUT` cho `ParseException`. Đối chiếu stdout với `DistinctPolicyDemo` và giải thích vì sao không dùng chung một `catch`.

**Bài 3 — Dịch exception.** Mở rộng `TranslatePolicyDemo` để thông điệp domain chứa tên thao tác an toàn như `"load request"`. Kiểm thử `getCause()` vẫn trả đúng loại ngoại lệ gốc. Vì sao không nên trả trực tiếp message kỹ thuật cho người dùng cuối?

**Bài 4 — Rethrow.** Trong `RethrowPolicyDemo`, bỏ toàn bộ `catch` tại tầng `parse`, để các lệnh trong phương thức trực tiếp ném lỗi theo khai báo `throws`. Quan sát output thay đổi ở các dòng `observed=...` nhưng caller vẫn nhận lỗi. Khi nào catch chỉ để log là không cần?

**Bài 5 — Subclass.** Thiết kế chính sách “file không tồn tại: báo `CREATE_FILE`; các lỗi I/O khác: báo `CHECK_SOURCE`”. Viết hai `catch` đúng thứ tự. Giải thích vì sao `FileNotFoundException | IOException` không được phép trong một multi-catch.

**Bài 6 — Chẩn đoán.** Viết câu trả lời ngắn cho ba lỗi compile: quan hệ subclass, tham số catch ngầm final và thiếu checked exception trong `throws`. Phân biệt lỗi compiler với lỗi nghiệp vụ ở hai ví dụ `SharedPolicyDemo`/`DistinctPolicyDemo`.

### Checklist cho code review

- [ ] Xác định rõ ai chịu trách nhiệm xử lý mỗi loại lỗi; không gom chỉ để code ngắn.
- [ ] Nếu dùng multi-catch, các alternative độc lập về quan hệ subtype/supertype.
- [ ] Shared handler chỉ có khi **chính sách của các loại lỗi giống nhau**.
- [ ] Nếu chính sách khác, dùng các `catch` riêng và đặt subtype trước supertype khi cần.
- [ ] Nếu translate exception, loại exception mới có ý nghĩa ở tầng API và **giữ cause**.
- [ ] Không biến checked exception thành unchecked chỉ nhằm bỏ lỗi biên dịch.
- [ ] Nếu chưa xử lý được, propagate/rethrow; không tạo kết quả success giả.
- [ ] Không bắt quá rộng, không bắt rỗng, không log lặp, không retry mù quáng.
- [ ] Có test cho từng loại lỗi và ca thành công; checked types đã được `javac` xác nhận.
- [ ] Tài nguyên I/O được quản lý riêng bằng cơ chế đóng tài nguyên phù hợp.

## Tài liệu chính thức và vẫn áp dụng

- [Java Language Specification 17 — `14.20: `try`, `catch` và multi-catch](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): type alternative, quan hệ subtype, tham số catch ngầm `final`, thứ tự catch.
- [Java Language Specification 17 — Chapter 11: Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): checked exceptions, phân tích các ngoại lệ có thể được ném và bắt.
- [Dev.java — Catching and Handling Exceptions](https://dev.java/learn/catching-and-handling-exceptions/): hướng dẫn Java hiện đại về các kiểu xử lý exception, multi-catch, propagation.
- [Oracle — Catching Multiple Exception Types and Rethrowing Exceptions](https://docs.oracle.com/javase/8/docs/technotes/guides/language/catch-multiple.html): tài liệu gốc của tính năng từ Java 7, nêu multi-catch và precise rethrow; các quy tắc này vẫn được đặc tả Java hiện nay duy trì.

**Kết luận:** `catch (A | B e)` là lựa chọn tốt khi **A và B thực sự có cùng chính sách**; nếu hậu quả khác nhau, giữ `catch` riêng; nếu caller chỉ nên thấy lỗi ở cấp abstraction cao, **translate với cause**; nếu tầng hiện tại chưa thể quyết định, **rethrow/propagate**. Quyết định dựa trên hợp đồng và khả năng phục hồi, không chỉ trên việc làm code ngắn hơn.