# Java 7 — Ném lại ngoại lệ: Kiểm tra đường đi ngoại lệ và hợp đồng phương thức

## Mục tiêu bài học

Trong Java, câu lệnh `throw e;` nằm trong `catch` có thể **ném lại chính đối tượng ngoại lệ vừa bắt** (rethrow). Từ Java 7, trình biên dịch còn hỗ trợ **precise rethrow**: ở một số tình huống bắt ngoại lệ bằng kiểu rộng như `Exception` nhưng không gán lại biến catch, compiler vẫn có thể suy ra chính xác hơn các checked exception có thể thoát ra.

Điều cần học không chỉ là cú pháp. Khi xem code có ném lại ngoại lệ, bạn phải kiểm tra được **đường đi của luồng điều khiển** và **hợp đồng phương thức**: ở đâu ngoại lệ được tạo, bắt, ghi nhận, ném lại, đóng tài nguyên, được caller xử lý hay chuyển đổi, và phương thức nào phải khai báo `throws`.

Sau bài, bạn có thể:

1. Vẽ đường đi từ `throw` trong tầng thấp đến `catch` ở caller, kể cả `finally`.
2. Phân biệt `throw e` (ném lại đối tượng gốc) và `throw new ...(..., e)` (bọc/chuyển đổi có giữ nguyên nhân).
3. Viết chữ ký `throws` đúng cho checked exception, phân biệt với unchecked exception.
4. Giải thích **precise rethrow** của Java 7 và điều kiện biến catch được xem là effectively final.
5. Kiểm chứng cả **đường đi thành công, đường đi lỗi, luồng cleanup, loại exception, cause, suppressed exception** và các ca compiler phải từ chối.
6. Đánh giá khi nào rethrow thực sự có ích và khi nào nên để exception tự propagate, chuyển thành lỗi tầng ứng dụng, hay xử lý ở boundary.

Tất cả ví dụ đầy đủ đều biên dịch bằng **`javac --release 17`** và chạy trên JDK 17+; các quy tắc này vẫn hiện hành. Không cần dùng môi trường Java cũ hoặc các API đã legacy.

## 1. Nền tảng: “ném lại” khác “bắt” và “xử lý xong”

Xét luồng gọi đơn giản:

```text
main() / API boundary
    |
    v
service.load()
    |
    v
repository.read()
    |
    +-- success ---------------> giá trị trả về
    |
    +-- throw IOException ----> service catch
                                  |
                                  +-- throw e ---> caller catch
```

Trên đường thành công, mỗi phương thức có thể trả về bình thường. Trên đường lỗi:

1. Tại điểm `throw`, biểu thức và câu lệnh đang chạy **hoàn tất bất thường**; những câu lệnh bình thường phía dưới trong cùng đường đi không tự tiếp tục.
2. Java tìm handler `catch` phù hợp trong các `try` bao quanh. Nếu chưa có, ngoại lệ lan lên phương thức gọi.
3. Khi handler bắt ngoại lệ, biến catch, ví dụ `e`, tham chiếu tới đối tượng lỗi được ném.
4. Nếu handler dùng `throw e;`, việc thực thi trong handler **kết thúc bất thường một lần nữa** và Java tìm handler ở phạm vi ngoài.
5. Các khối `finally` áp dụng trên đường chuyển điều khiển sẽ được thực thi theo quy tắc Java. Nếu chính một `finally` hoàn tất bất thường (ví dụ ném exception mới), lý do hoàn tất bất thường trước đó có thể bị thay thế.
6. Caller bắt, xử lý hoặc tiếp tục để ngoại lệ lan lên tầng tiếp theo.

Cụm từ “rethrow” chỉ mô tả việc **ném lại**, không bảo đảm caller đã được khắc phục lỗi. Nếu ngoại lệ đã bị catch rồi trả giá trị giả hoặc bị bỏ qua, hành vi ấy là **swallow**, không phải rethrow.

### Phân biệt bốn thao tác ở một catch

| Mã trong `catch` | Ý nghĩa chính | Điều caller nhìn thấy |
| --- | --- | --- |
| `throw e;` | Ném lại **chính đối tượng** đang được bắt | Loại và nguyên nhân gốc vẫn đi lên, theo hợp đồng checked exception |
| `throw new DomainException("...", e);` | Chuyển thành đối tượng/loại exception mới và giữ cause | Caller nhận DomainException; có thể truy gốc qua `getCause()` |
| `return FALLBACK;` | Kết thúc bằng một giá trị thường | Caller thấy fallback, không nhận exception ở đường này |
| `handle(e);` rồi ra khỏi catch | Coi như xử lý hoàn tất nếu không ném tiếp | Caller tiếp tục bình thường sau `try/catch` |

Không có đáp án chung cho mọi codebase. Việc chọn cách nào phụ thuộc **hợp đồng API**: caller có thể phục hồi gì, lỗi có phải trạng thái dự kiến, và boundary chịu trách nhiệm báo cáo ở đâu.

## 2. Thí nghiệm A — Vẽ và kiểm tra đúng đường đi với `throw e`

Mục tiêu là quan sát cụ thể thứ tự: caller gọi service → service vào `try` → xảy ra hoặc không xảy ra `IOException` → service `catch` → service `finally` → caller nhận giá trị hoặc catch lỗi.

Lưu **toàn bộ** mã sau vào tệp `RethrowTraceDemo.java`:

```java
import java.io.IOException;

public final class RethrowTraceDemo {
    private static String load(boolean fail) throws IOException {
        System.out.println("service:begin");
        try {
            if (fail) {
                throw new IOException("disk unavailable");
            }
            System.out.println("service:success");
            return "DATA";
        } catch (IOException e) {
            System.out.println("service:rethrow " + e.getClass().getSimpleName());
            throw e;
        } finally {
            System.out.println("service:finally");
        }
    }

    public static void main(String[] args) {
        for (boolean fail : new boolean[]{false, true}) {
            System.out.println("caller:case=" + (fail ? "fail" : "ok"));
            try {
                String result = load(fail);
                System.out.println("caller:value=" + result);
            } catch (IOException e) {
                System.out.println("caller:catch=" + e.getMessage());
            }
        }
    }
}
```

Chạy từ thư mục chứa file:

```bash
javac --release 17 -encoding UTF-8 RethrowTraceDemo.java
java RethrowTraceDemo
```

**Output chính xác:**

```text
caller:case=ok
service:begin
service:success
service:finally
caller:value=DATA
caller:case=fail
service:begin
service:rethrow IOException
service:finally
caller:catch=disk unavailable
```

### 2.1. Đường thành công

Với `fail=false`:

```text
caller -> load -> service:begin -> service:success
       -> return DATA (đang chờ) -> finally -> caller:value=DATA
```

- `catch (IOException e)` **không** chạy vì không có `IOException` được ném từ `try`.
- `finally` của phương thức `load` vẫn chạy khi `try` chuẩn bị hoàn tất bằng `return`.
- Caller chỉ nhận kết quả và in `caller:value=DATA` **sau khi** `finally` hoàn thành.

### 2.2. Đường ngoại lệ

Với `fail=true`:

```text
caller -> load -> service:begin -> throw IOException
       -> service:catch -> throw e -> service:finally
       -> caller:catch=...
```

- Dòng `service:success` không chạy vì ngoại lệ xảy ra trước nó.
- `catch` tại `load` thấy đối tượng `IOException`, ghi một thông tin quan sát rồi `throw e`.
- `finally` chạy trong khi ngoại lệ tiếp tục được truyền ra.
- Caller chỉ bắt ngoại lệ sau khi `load` hoàn tất bất thường; dòng `caller:value=...` không chạy với trường hợp lỗi.
- `load` khai báo `throws IOException`: checked exception có thể thoát khỏi phương thức, và caller phải bắt hoặc khai báo tiếp.

**Quan trọng:** Trong các đường đi bình thường của ví dụ này, `finally` chạy dù có `return` hay `throw`. Không nên phát biểu “finally luôn luôn chạy” vô điều kiện; cưỡng bức dừng JVM, lỗi môi trường nghiêm trọng hoặc một số cách kết thúc chương trình có thể ngăn nó. Cũng không nên `return`/`throw` từ `finally` vì có thể làm mất kết quả/lỗi gốc.

### 2.3. Tại sao `throw e` không tự “bắt lại chính nó”?

`throw e` nằm trong phần thân `catch`, nên nó không quay về cùng một `catch` để chạy vòng lặp vô hạn. Ngoại lệ thoát phạm vi xử lý hiện tại và tiếp tục tìm handler ở phần bao ngoài/caller. Nếu cần xử lý thêm ở cùng tầng, phải thiết kế cụ thể; không giả định rằng một catch sẽ xử lý lại chính lỗi do nó ném.

## 3. Hợp đồng phương thức: checked, unchecked, `throws` và caller

**Chữ ký phương thức** là điều compiler và caller dựa vào để biết ràng buộc nào phải được xử lý. Xét:

```java
private static String load(boolean fail) throws IOException
```

Đó là một **chữ ký minh họa được dùng trong `RethrowTraceDemo`**. `IOException` là checked exception; nếu một đường đi có thể để nó thoát ra, compiler yêu cầu phương thức khai báo `throws IOException` (hoặc kiểu cha phù hợp) hoặc bắt và xử lý nó trước khi thoát.

| Thành phần | Checked exception | Unchecked exception |
| --- | --- | --- |
| Phân loại | Thường là subclass của `Exception` nhưng không thuộc `RuntimeException` | `RuntimeException` và các subtype, cùng các `Error` |
| Bắt ở caller | Phải bắt hoặc tiếp tục khai báo nếu compiler thấy có thể bị ném | Không có yêu cầu `catch`/`throws` của compiler |
| `throws` có hợp lệ? | Có; thể hiện ràng buộc compile-time | Có thể ghi để tài liệu hóa, nhưng không bắt buộc theo luật checked |
| Khi `throw e` | Có thể phải khai báo lại checked type | Không có yêu cầu checked declaration chỉ vì rethrow |
| Khi wrapper là `RuntimeException` | Không tự đòi `throws` ở boundary đó | Caller vẫn phải biết hợp đồng bằng tài liệu/test/thiết kế |

`throws` không có nghĩa là phương thức **luôn** ném ngoại lệ; nó là phần mô tả những checked exceptions **có thể thoát ra** theo luật kiểm tra kiểu. Ngược lại, một phương thức không khai báo checked exception vẫn có thể ném unchecked exception.

### 3.1. Lỗi compiler: ném lại nhưng không khai báo

Đây là **tệp cố ý sai**, tạo riêng thành `UnreportedRethrow.java` để thử lỗi:

```java
import java.io.IOException;

public final class UnreportedRethrow {
    static void run() {
        try {
            throw new IOException("offline");
        } catch (IOException e) {
            throw e; // CỐ Ý SAI: run() không throws IOException
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 UnreportedRethrow.java
```

**Kỳ vọng:** biên dịch thất bại vì `IOException` có thể thoát khỏi `run()` nhưng phương thức không bắt xử lý và không khai báo `throws IOException`. Thêm `throws IOException` vào `run()` chỉ giải quyết chữ ký của `run`; caller của `run` cũng cần bắt hoặc khai báo phù hợp. Thông điệp cụ thể của `javac` có thể khác theo phiên bản.

### 3.2. Hợp đồng đi qua một chuỗi phương thức

```java
static void repository() throws IOException {
    throw new IOException("source error");
}

static void service() throws IOException {
    repository();
}

static void controller() {
    try {
        service();
    } catch (IOException e) {
        // Quyết định tại boundary, ví dụ trả mã lỗi phù hợp.
    }
}
```

Đây là các **phương thức minh họa**, để đặt trong cùng một lớp có import `IOException`, không có `main` độc lập. `repository` và `service` đều để checked exception lan lên. `controller` nhận trách nhiệm bắt nên không cần khai báo `throws IOException` trên đường thực thi này.

Thêm một `catch (IOException e) { throw e; }` vào `service` mà không ghi nhận gì, không thêm ngữ cảnh, không quản lý cleanup thì thường **không mang lại giá trị**. Cho ngoại lệ tự lan lên đơn giản và ít gây log lặp hơn.

### 3.3. Kiểm tra hợp đồng public API và override

Một phương thức public dùng checked exceptions nên mô tả các lỗi có ý nghĩa cho caller, không chỉ tuyên bố `throws Exception` vì “cho tiện”. Khi override một phương thức, luật checked exception của Java còn giới hạn những checked exception nào override được phép khai báo: không thể tự ý mở rộng hợp đồng thành một loại checked exception không phù hợp với phương thức gốc.

Refactor exception trong phương thức đã được client sử dụng cần kiểm tra **mã caller biên dịch được hay không**, API documentation, và xử lý thực tế ở boundary. Đổi checked thành unchecked có thể không tạo lỗi biên dịch ở caller nhưng vẫn thay hành vi/hợp đồng quan trọng.

## 4. Precise rethrow từ Java 7: bắt rộng nhưng suy luận đường đi chính xác

Một tình huống thú vị: một `try` có thể ném `IOException` hoặc `ParseException`. Bạn bắt bằng `catch (Exception e)`, quan sát chung, rồi **ném lại chính biến `e`**. Từ Java 7, khi biến exception trong catch được xem là **effectively final** (không bị gán lại), compiler có thể xác định **các checked exception thực sự có thể được ném và được bắt bởi catch đó**, thay vì buộc phương thức khai báo `throws Exception` chỉ vì kiểu khai báo của `e` là `Exception`.

### Chương trình đầy đủ: `PreciseRethrowDemo.java`

```java
import java.io.IOException;
import java.text.ParseException;

public final class PreciseRethrowDemo {
    private static void process(String mode)
            throws IOException, ParseException {
        try {
            if ("io".equals(mode)) {
                throw new IOException("io");
            }
            if ("parse".equals(mode)) {
                throw new ParseException("parse", 0);
            }
            System.out.println("worker:ok");
        } catch (Exception e) {
            System.out.println("worker:observed=" + e.getClass().getSimpleName());
            throw e;
        }
    }

    public static void main(String[] args) {
        for (String mode : new String[]{"ok", "io", "parse"}) {
            System.out.println("caller:case=" + mode);
            try {
                process(mode);
                System.out.println("caller:success");
            } catch (IOException e) {
                System.out.println("caller:IOException");
            } catch (ParseException e) {
                System.out.println("caller:ParseException");
            }
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 PreciseRethrowDemo.java
java PreciseRethrowDemo
```

Output:

```text
caller:case=ok
worker:ok
caller:success
caller:case=io
worker:observed=IOException
caller:IOException
caller:case=parse
worker:observed=ParseException
caller:ParseException
```

### 4.1. Đọc hợp đồng theo đường đi

- `try` trong `process` có thể ném hai checked exceptions là `IOException` và `ParseException`.
- `catch (Exception e)` bắt các ngoại lệ phù hợp, log loại thực tế của đối tượng đã được ném, rồi `throw e`.
- `e` không bị gán lại, nên theo quy tắc precise rethrow, chữ ký `throws IOException, ParseException` là đủ cho **các checked exceptions được ném theo đường đi này**. Không cần đổi thành `throws Exception`.
- Caller dùng hai catch riêng và nhìn thấy loại lỗi gốc; không có exception mới được tạo khi `throw e`.
- Trường hợp `ok` không ném lỗi, chỉ in `worker:ok` rồi caller in `caller:success`.

Đây là minh họa cơ chế ngôn ngữ, **không phải khuyến nghị bắt `Exception` rộng ở mọi nơi**. Trong code mới, nếu thực sự muốn chỉ bắt hai kiểu này để xử lý chung, `catch (IOException | ParseException e)` thể hiện phạm vi hẹp và rõ hơn.

### 4.2. Điều kiện effectively final

`Exception e` trong catch đơn không bị khai báo `final` nhưng có thể **effectively final** nếu không hề có phép gán lại sau khi được khởi tạo lúc bắt lỗi.

**Ví dụ cố ý sai khi kỳ vọng precise rethrow:**

```java
import java.io.IOException;
import java.text.ParseException;

public final class ReassignedCatch {
    static void work() throws IOException, ParseException {
        try {
            if (System.nanoTime() > 0) {
                throw new IOException("offline");
            }
            throw new ParseException("bad", 0);
        } catch (Exception e) {
            e = new Exception("replacement");
            throw e; // CỐ Ý SAI: e không còn effectively final
        }
    }
}
```

Biên dịch tệp này bằng `javac --release 17 -encoding UTF-8 ReassignedCatch.java` sẽ **FAIL**: biến `e` đã bị gán lại, compiler không còn áp dụng precise rethrow để giới hạn checked type ở `IOException` và `ParseException`; giá trị mới có kiểu `Exception` rộng hơn hợp đồng `throws` hiện tại.

Đừng “sửa” bằng cách bắt `Throwable` hoặc mở rộng `throws Exception` ngay lập tức nếu mục tiêu là giữ chính xác hợp đồng. Hãy giữ nguyên đối tượng exception và ném lại, hoặc định nghĩa một wrapper/domain exception phù hợp khi **thật sự muốn** chuyển đổi.

### 4.3. Multi-catch và precise rethrow không giống hệt nhau

```java
catch (IOException | ParseException e) {
    throw e;
}
```

Ở multi-catch, tham số `e` **ngầm `final`**, không được gán lại. Hai loại được khai báo tường minh, không có quan hệ cha–con trực tiếp, và `throw e` có thể giữ hợp đồng checked exception ở hai loại này.

```java
catch (Exception e) {
    throw e;
}
```

Ở catch đơn kiểu rộng, precise rethrow cần compiler phân tích **những loại mà `try` thực tế có thể ném** và điều kiện effectively final; không thể suy rằng `throws Exception` luôn là cần thiết hoặc luôn là không cần thiết trong mọi ngữ cảnh. Nếu `try` có thêm đường ném checked exception khác, hợp đồng cũng có thể cần thay đổi.

Ví dụ gán lại biến multi-catch bên dưới **không hợp lệ ngay cả khi chữ ký khai báo rộng**, vì biến ngầm final:

```java
catch (IOException | ParseException e) {
    e = new IOException("replacement"); // CỐ Ý SAI
    throw e;
}
```

Các đoạn trong hai `catch` trên chỉ là **mảnh cú pháp minh họa**, không phải lớp độc lập.

## 5. Ném lại đối tượng gốc hay chuyển đổi ngoại lệ?

Trước khi viết `throw e;`, phải trả lời: **caller có nên xử lý loại ngoại lệ gốc không?**

- **Nên:** giữ nguyên checked exception nếu caller có cách xử lý, chữ ký method đã hứa cung cấp loại đó, hoặc log/metric bổ sung ở tầng hiện tại có ích.
- **Không nên:** khi tầng service muốn cung cấp một abstraction cấp nghiệp vụ, hãy chuyển đổi thành exception phù hợp với API và **giữ `cause`**.
- **Chưa cần làm gì:** nếu tầng hiện tại không có logic hữu ích, không thêm catch; để exception tự propagate.
- **Có thể khôi phục hoàn toàn:** nếu chính sách thực sự cho phép fallback và bảo toàn tính đúng, kết thúc bằng kết quả thường thay vì ném tiếp.

| Cách viết | Object ném tới caller | Kiểu checked/unchecked caller đối diện | Bảo toàn bằng chứng lỗi |
| --- | --- | --- | --- |
| `throw e;` | Chính object `e` gốc | Theo loại của `e` và checked exception analysis | Cùng exception và stack trace hiện có |
| `throw new QueryException("failed", e);` | Object `QueryException` mới | Theo `QueryException` (trong ví dụ là unchecked) | Cause giữ `e`, stack trace mới ở điểm bọc |
| `throw new QueryException("failed", null);` | Object mới không có cause | Theo wrapper | **Mất liên kết nguyên nhân gốc** |
| Không catch, để propagate | Exception từ callee | Như callee, theo hợp đồng | Không thay đổi object gốc |
| `return FALLBACK;` | Không có exception thoát ở đường này | Giá trị thường | Chỉ chấp nhận khi hợp đồng cho phép fallback |

**Không nên** lấy một message mơ hồ từ lỗi tầng thấp rồi tạo exception mới mà bỏ cause. Nếu exception nhiều tầng và mỗi tầng wrap thêm một lần, stack trace dài nhưng ý nghĩa tăng ít; hãy wrap tại ranh giới abstraction có lý do cụ thể.

### 5.1. Chương trình đầy đủ: `TranslationDemo.java`

```java
import java.io.IOException;
import java.text.ParseException;

public final class TranslationDemo {
    static final class QueryException extends RuntimeException {
        QueryException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    private static String fetch(String mode)
            throws IOException, ParseException {
        if ("io".equals(mode)) {
            throw new IOException("offline");
        }
        if ("parse".equals(mode)) {
            throw new ParseException("bad record", 0);
        }
        return "READY";
    }

    private static String query(String mode) {
        try {
            return fetch(mode);
        } catch (IOException | ParseException e) {
            throw new QueryException("query failed", e);
        }
    }

    public static void main(String[] args) {
        for (String mode : new String[]{"ok", "io", "parse"}) {
            try {
                System.out.println(mode + "=" + query(mode));
            } catch (QueryException e) {
                System.out.println(mode + "=" + e.getClass().getSimpleName()
                        + "; cause=" + e.getCause().getClass().getSimpleName());
            }
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 TranslationDemo.java
java TranslationDemo
```

Output:

```text
ok=READY
io=QueryException; cause=IOException
parse=QueryException; cause=ParseException
```

### 5.2. Đọc tầng nào chịu trách nhiệm điều gì?

- `fetch` có thể ném checked `IOException` hoặc `ParseException`; chữ ký ghi đúng hai loại.
- `query` bắt hai kiểu và chuyển thành `QueryException`; vì lớp domain này extends `RuntimeException`, `query` **không bắt buộc** khai báo `throws` theo kiểm tra checked exception. Tuy vậy, đây vẫn là một phần của **hợp đồng hành vi** cần được tài liệu hóa và test.
- Caller không cần import hoặc bắt hai loại checked exception tầng thấp; nó có thể bắt `QueryException` và truy `getCause()` khi cần chẩn đoán.
- `new QueryException("query failed", e)` **không phải rethrow cùng đối tượng**. Đây là tạo ngoại lệ mới, có cause là ngoại lệ gốc.
- Nếu một API công khai cần recovery cho hai kiểu lỗi khác nhau, dùng chung `QueryException` có thể làm mất tính phân biệt ở cấp API. Quyết định translation phải hợp với nhu cầu caller.

### 5.3. Khi nào chuyển thành checked domain exception?

Không có luật bắt mọi exception thành unchecked. Có thể tạo `RequestLoadException extends Exception` và khai báo `throws RequestLoadException` nếu caller theo thiết kế **phải cân nhắc** cách xử lý. Ở Java, chọn checked/unchecked là quyết định thiết kế API; compiler chỉ thực thi hợp đồng đã được định nghĩa, không tự đánh giá tính đúng đắn nghiệp vụ.

## 6. `finally`, đóng tài nguyên và suppressed exceptions trên đường lỗi

Truyền ngoại lệ không chỉ đi qua `catch`: cleanup cũng ảnh hưởng đường đi. Cần phân biệt ba khái niệm:

1. `finally` chạy khi rời một `try` trên các đường đi thông thường của Java, kể cả `return` hay `throw`.
2. Nếu một `finally` **tự ném exception hoặc return**, điều khiển có thể bị thay thế, làm thất lạc nguyên nhân ban đầu.
3. Với **try-with-resources** (cũng được giới thiệu từ Java 7 và vẫn được khuyến nghị khi dùng `AutoCloseable`), một lỗi từ `close()` có thể được giữ lại thành **suppressed exception** thay vì che lỗi chính trong thân `try`.

### 6.1. Chương trình đầy đủ: `SuppressedFlowDemo.java`

```java
import java.io.IOException;

public final class SuppressedFlowDemo {
    private static final class SampleResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("resource:close");
            throw new IOException("close failed");
        }
    }

    private static void run() throws IOException {
        try (SampleResource resource = new SampleResource()) {
            System.out.println("work:start");
            throw new IllegalStateException("work failed");
        }
    }

    public static void main(String[] args) {
        try {
            run();
        } catch (Exception e) {
            System.out.println("caught=" + e.getClass().getSimpleName()
                    + ":" + e.getMessage());
            System.out.println("suppressed=" + e.getSuppressed().length);
            for (Throwable t : e.getSuppressed()) {
                System.out.println("suppressedCause="
                        + t.getClass().getSimpleName() + ":" + t.getMessage());
            }
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 SuppressedFlowDemo.java
java SuppressedFlowDemo
```

Output:

```text
work:start
resource:close
caught=IllegalStateException:work failed
suppressed=1
suppressedCause=IOException:close failed
```

### 6.2. Lý giải luồng exception

- Trong `run`, thân `try` tạo `IllegalStateException("work failed")`.
- Khi rời `try`, try-with-resources gọi `close()`; việc đóng ném thêm `IOException("close failed")`.
- Java giữ lỗi **đang xảy ra trong thân try** làm exception chính ở tình huống này; lỗi đóng tài nguyên được đính vào `getSuppressed()` của exception chính.
- Caller bắt được `IllegalStateException` và thấy một suppressed exception kiểu `IOException`.
- `run` khai báo `throws IOException` vì `close()` có thể ném checked `IOException`, ngay cả nếu trong thí nghiệm đường chạy cụ thể đã có unchecked `IllegalStateException` từ thân `try`.
- **Suppressed exception khác cause:** `getCause()` mô tả mối quan hệ nguyên nhân (thường khi wrap), còn `getSuppressed()` giữ các lỗi phụ xảy ra trong quá trình xử lý/đóng tài nguyên. Đừng coi chúng là một.

Đối với file/stream/database resource là `AutoCloseable`, nên dùng try-with-resources thay vì viết cleanup thủ công trong `finally` khi phù hợp. Khi debug đường đi lỗi, kiểm tra cả exception chính, cause chain và suppressed exceptions.

### 6.3. Anti-pattern: ném/return từ `finally`

```java
try {
    throw new IllegalStateException("primary");
} finally {
    throw new IllegalArgumentException("cleanup");
}
```

Đoạn trên là **minh họa nguy hiểm**, không cần chạy trong ứng dụng. Do `finally` tự ném exception mới, exception `primary` có thể bị thay thế bởi `cleanup`. Dùng return trong finally cũng có thể làm mất một exception đang truyền ra hoặc thay đổi giá trị return. Hãy tránh việc để `finally` hoàn tất bất thường; dùng try-with-resources nơi có thể.

## 7. Kiểm tra đường đi bằng ma trận, không chỉ nhìn catch

Khi viết test cho rethrow, cần kiểm tra **giá trị thành công**, **loại ngoại lệ**, **thứ tự side effect**, **đối tượng/cause/suppressed**, và **khả năng compile của caller**.

| Đường đi | Điểm tạo / ném lỗi | Catch trong callee | Cleanup | Điều caller quan sát |
| --- | --- | --- | --- | --- |
| `RethrowTraceDemo` thành công | Không có lỗi | Không chạy | `service:finally` | `DATA` |
| `RethrowTraceDemo` lỗi | `new IOException("disk unavailable")` | `throw e` | `service:finally` | Bắt `IOException` cùng message |
| `PreciseRethrowDemo` / `io` | `IOException` | Catch rộng, rethrow | Không có cleanup riêng | Caller bắt `IOException` |
| `PreciseRethrowDemo` / `parse` | `ParseException` | Catch rộng, rethrow | Không có cleanup riêng | Caller bắt `ParseException` |
| `PreciseRethrowDemo` / `ok` | Không có lỗi | Không chạy | Không có cleanup riêng | `caller:success` |
| `TranslationDemo` / `io` | `IOException` | Bọc thành `QueryException` | Không có cleanup riêng | `QueryException` với cause `IOException` |
| `TranslationDemo` / `parse` | `ParseException` | Bọc thành `QueryException` | Không có cleanup riêng | `QueryException` với cause `ParseException` |
| `SuppressedFlowDemo` | `IllegalStateException` trong thân try | Không có catch trong `run` | `close()` ném `IOException` | Chính là `IllegalStateException`, suppressed là `IOException` |

Với dịch vụ thật, thêm test cho caller nào phải retry hoặc reject, caller nào được phép bỏ qua, và log/metric được ghi **một lần ở ranh giới phù hợp**. Nếu code có tác dụng phụ (ghi database, gửi email, cập nhật trạng thái), test rằng các side effect phía sau `throw` không vô tình chạy và retry không thực hiện một thao tác không idempotent nhiều lần.

### 7.1. Sơ đồ tìm handler

```text
Gặp throw X tại một điểm thực thi?
  |
  +-- Không --> chạy tiếp hoặc return (finally áp dụng khi rời try)
  |
  +-- Có --> tìm catch phù hợp ở try đang bao quanh điểm ném
                |
                +-- Có catch phù hợp
                |      |
                |      +-- Xử lý xong --> tiếp tục sau try/catch/finally
                |      |
                |      +-- throw e --> tiếp tục tìm handler ở phạm vi ngoài
                |      |
                |      +-- throw wrapper(e) --> loại mới đi lên; X nằm trong cause
                |
                +-- Không có catch phù hợp --> unwind sang phạm vi/caller ngoài
                            |
                            +-- thực hiện cleanup/finally áp dụng
                            +-- caller bắt hoặc tiếp tục propagate
```

Đây là sơ đồ định hướng. Quy tắc thực tế còn bao gồm thứ tự `try`/`catch`/`finally`/resource close và trường hợp cleanup thất bại. Vì vậy nên kết hợp sơ đồ với **output có trace** và kiểm chứng bằng `javac`.

### 7.2. Kiểm chứng “cùng đối tượng” ở rethrow

Nếu thật sự cần test rằng handler ở tầng ngoài nhận lại chính exception gốc, có thể giữ một tham chiếu tới exception trong bài test và so bằng `==`. `throw e` không tạo object mới. Ngược lại, khi wrap, exception đến caller là object mới; `e.getCause()` phải trỏ đúng exception gốc nếu constructor truyền cause.

Không dùng `getClass().getSimpleName()` để chứng minh **object identity**, vì hai exception khác object vẫn có cùng class. Mỗi loại kiểm tra trả lời một câu hỏi khác nhau:

- `getClass()`: loại runtime của exception là gì?
- `getMessage()`: thông tin ngữ cảnh của lỗi là gì?
- `getCause()`: lỗi được bọc xuất phát từ đâu?
- `getSuppressed()`: có lỗi phụ nào được giữ lại không?
- `==`: có phải cùng object đã ném lúc đầu không?

## 8. Kiểm chứng compiler: những trường hợp phải FAIL

Một bài về hợp đồng phương thức phải có **negative compile tests**, vì runtime test không thể chứng minh compiler đang bảo vệ đúng các checked exception.

### Ca A — `throw e` thoát hàm nhưng thiếu `throws`

Trong `UnreportedRethrow.java` ở mục 3, `run()` không khai báo `throws IOException` trong khi catch ném lại `e`. `javac` phải từ chối. Đây là lỗi **compile-time**, không phải lỗi xuất hiện sau khi chạy ứng dụng.

### Ca B — Catch rộng bị gán lại, mất precise rethrow

Trong `ReassignedCatch.java` ở mục 4, phép `e = new Exception("replacement")` làm biến catch không còn effectively final. Với chữ ký chỉ khai báo `IOException, ParseException`, compiler phải từ chối `throw e` do loại checked exception có thể thoát ra rộng hơn.

### Ca C — Biến multi-catch ngầm final

Thử file `MultiCatchReassign.java`:

```java
import java.io.IOException;
import java.text.ParseException;

public final class MultiCatchReassign {
    static void work() throws IOException, ParseException {
        try {
            if (System.nanoTime() > 0) {
                throw new IOException("offline");
            }
            throw new ParseException("bad", 0);
        } catch (IOException | ParseException e) {
            e = new IOException("new"); // CỐ Ý SAI
            throw e;
        }
    }
}
```

Kết quả `javac --release 17 -encoding UTF-8 MultiCatchReassign.java` là **FAIL** vì gán lại `e` không được phép trong multi-catch. Khác với catch đơn kiểu `Exception`, tham số multi-catch **ngầm final theo ngôn ngữ**; không thể “sửa” bằng cách mở rộng `throws`.

### Cách thực hành đúng

- Lưu **mỗi ví dụ cố ý sai trong tệp riêng**.
- Dùng `javac --release 17 -encoding UTF-8 <FileName>.java`.
- Quan sát **exit code khác 0** và nội dung chẩn đoán phù hợp. Câu chữ của thông báo có thể khác tùy JDK.
- Không gộp file cố ý sai với bốn chương trình chuẩn rồi nghĩ rằng các chương trình chuẩn không chạy được.
- Sau mỗi ca, sửa lỗi dựa trên hợp đồng: khai báo đúng checked type, không gán lại catch parameter, hoặc chuyển đổi có cause khi cần.

## 9. Những sai lầm thường gặp khi lần theo ngoại lệ

### 9.1. `catch` rồi chỉ `throw e` ở mọi tầng

```java
try {
    service();
} catch (IOException e) {
    throw e;
}
```

Đây là **mảnh minh họa**, giả định `service()` có thể ném `IOException`. Nếu handler không có bước quan sát, cleanup, translation hoặc chính sách mới, việc bắt rồi ném ngay thường **dư thừa**. Cho ngoại lệ propagate tự nhiên giúp đường đi rõ hơn.

### 9.2. “Cứ catch được thì caller đã an toàn”

Không đúng. `throw e` khiến method hoàn tất bất thường; caller vẫn phải xử lý hoặc tiếp tục propagate. Nếu caller cuối cùng không bắt, ngoại lệ có thể đến uncaught exception handler và luồng bị kết thúc theo quy tắc runtime. Test cần bao phủ boundary cuối cùng, không chỉ khối `catch` đầu tiên.

### 9.3. Mở rộng `throws Exception` để bỏ lỗi biên dịch

Một chữ ký quá rộng có thể buộc caller xử lý nhiều loại lỗi không cần thiết và che mất hợp đồng cụ thể. Nếu `try` chỉ ném `IOException`, `ParseException` và `throw e` đáp ứng precise rethrow, giữ chữ ký **hẹp, có ý nghĩa**. Chỉ khai báo loại khác nếu thiết kế và phân tích compiler thực sự yêu cầu.

### 9.4. Bắt `Exception` rồi nuốt lỗi

```java
catch (Exception e) {
    return "OK";
}
```

Nếu công việc thật sự thất bại thì trả `"OK"` làm sai trạng thái hệ thống. Ngay cả với precise rethrow, `catch (Exception e)` là một vùng bắt rộng; dùng có mục đích và biết rõ các exception của `try`. Đừng dùng nó để thay thế chính sách lỗi hoặc che bug.

### 9.5. Quên rằng `finally` có thể thay đổi ngoại lệ

Một `throw`/`return` từ `finally` có thể khiến caller không còn thấy lỗi gốc. Nếu đóng tài nguyên có thể ném exception, try-with-resources thường giữ được **primary exception** và đặt lỗi đóng vào `suppressed`. Đọc cả `getCause()` và `getSuppressed()` khi chẩn đoán.

### 9.6. Nhầm rethrow và wrap

`throw e` giữ đối tượng và loại đã bắt; `throw new IllegalStateException("...", e)` tạo loại mới với nguyên nhân gốc. Caller catch theo **loại wrapper** nếu đã translate; catch theo `IOException` sẽ không tự bắt một `QueryException` mới chỉ vì `getCause()` của nó là `IOException`.

### 9.7. Ghi log lặp ở service, controller và job runner

Một exception có thể đi qua nhiều tầng. Nếu mỗi tầng log đầy đủ stack trace rồi ném lại, log sinh ra nhiều bản ghi cho cùng một lỗi. Thiết kế quy ước: nơi nào thêm ngữ cảnh, nơi nào ghi metric, nơi nào log cuối cùng và nơi nào trả response. Tránh ghi thông tin nhạy cảm trong message.

### 9.8. Cho rằng mọi `IOException` đều retry được

Ngoại lệ checked hay unchecked không đủ xác định khả năng retry. Cần xem liệu thao tác có side effect, có idempotent không, có deadline/backoff/max-attempts không, và lỗi là tạm thời hay vĩnh viễn. Rethrow giữ thông tin nhưng không tự biến một lần chạy lại thành an toàn.

### 9.9. Chỉ test một input lỗi

Một code path có thể có các nhánh: không lỗi, lỗi từ body, lỗi từ cleanup, lỗi đã translate, ngoại lệ runtime ngoài dự kiến. Cần test các đường đi khác nhau và các dạng output/cause khác nhau thay vì chỉ xem một dòng log.

## 10. Quy trình review hợp đồng phương thức trong dự án

Để kiểm tra một phương thức có rethrow mà không đổi ngoài phạm vi:

1. **Viết chữ ký ban đầu:** tên, kiểu return, `throws`, public API, override/interface contract; ghi các caller chính.
2. **Lập đồ thị call chain nhỏ:** nơi tạo exception, nơi có `try`/`catch`, nơi có `finally`/resource, nơi callback/caller nhận lỗi.
3. **Phân loại đường đi:** success, checked failure từng loại, unchecked failure, cleanup failure, translation, recovery.
4. **Xác định chính sách từng tầng:** có xử lý được không? Chỉ quan sát rồi rethrow? Wrap thành domain exception? Hay không bắt?
5. **Đối chiếu chữ ký `throws`:** compiler phải thấy đầy đủ checked exceptions thoát ra; method override không tùy ý thêm checked exception.
6. **Nếu có precise rethrow:** kiểm tra catch parameter không bị gán lại; các checked exception của `try` có thể thoát ra đúng tập hợp đang khai báo.
7. **Kiểm tra resource cleanup:** try-with-resources thích hợp, không có `return`/`throw` vô tình từ `finally`; suppressed exceptions không bị bỏ qua khi debug.
8. **Viết test có trace:** kiểm tra thứ tự trước catch, trong catch, finally, caller; loại exception, message, cause, suppressed và side effect.
9. **Chạy negative compile tests:** bảo đảm compiler thực sự chặn trường hợp thiếu `throws`/gán lại catch.
10. **Review hành vi cuối cùng:** nếu refactor chỉ nhằm làm code ngắn hơn, không được vô tình đổi loại lỗi mà caller cần bắt, loại response, hoặc quyết định retry.

### Bảng quyết định hợp đồng

| Điều kiện | Hành động nên cân nhắc | Bằng chứng cần có |
| --- | --- | --- |
| Callee ném checked exception, caller hiểu và xử lý được | Propagate hoặc `throw e` khi có giá trị bổ sung | `throws`, caller catch, test lỗi |
| Callee ném checked exception, tầng hiện tại hoàn toàn xử lý được | Catch và trả kết quả phù hợp hợp đồng | Test success và fallback, dữ liệu không sai |
| Caller chỉ nên biết lỗi domain | Wrap/chuyển đổi có cause | Loại wrapper, `getCause()`, tài liệu API |
| Một catch rộng chỉ log rồi rethrow | Dùng precise rethrow nếu đúng quy tắc, hoặc thu hẹp catch | Chữ ký checked hẹp, compiler PASS |
| Cleanup cũng có thể thất bại | Try-with-resources, kiểm tra suppressed | Test lỗi thân try và lỗi close |
| Không có việc gì cần làm ở tầng trung gian | Bỏ catch dư, để propagate | Build/test và hợp đồng không đổi |

### Bài tập tự luyện

**Bài 1 — Trace:** Vẽ hai đường đi của `RethrowTraceDemo` trước khi chạy. Tại sao `service:finally` xuất hiện trước `caller:value=DATA` trên đường thành công và trước `caller:catch=...` trên đường lỗi?

**Bài 2 — Hợp đồng:** Bỏ `throws IOException` ở `load`. Dự đoán compiler báo lỗi ở đâu; thêm lại rồi thử thay `IOException` bằng `RuntimeException` trong một ví dụ riêng để quan sát khác biệt checked/unchecked.

**Bài 3 — Precise rethrow:** Sửa `PreciseRethrowDemo` từ `catch (Exception e)` thành `catch (IOException | ParseException e)`. Chữ ký `throws` và stdout có thay đổi không? Vì sao multi-catch thể hiện rõ phạm vi bắt hơn?

**Bài 4 — Catch reassignment:** Thử `ReassignedCatch.java`. Giải thích vì sao `e = new Exception(...)` làm compiler không còn suy luận precise rethrow như trước.

**Bài 5 — Identity và cause:** Trong `TranslationDemo`, kiểm tra `getCause()` có đúng class gốc. Tạo một thí nghiệm riêng cho `throw e` và so identity bằng `==`. Vì sao so class không đủ để kết luận có cùng object?

**Bài 6 — Suppressed:** Giữ nguyên `SuppressedFlowDemo` nhưng cho body hoàn tất bình thường, `close()` vẫn lỗi. Dự đoán loại exception chính lúc này và so với trường hợp body ném lỗi trước đó.

**Bài 7 — Boundary:** Một API public không muốn để lộ thông tin lưu trữ, nhưng caller có thể phân biệt “input sai” và “lỗi kết nối”. Thiết kế ít nhất hai loại domain exception hoặc mã lỗi phù hợp mà vẫn giữ cause. Vì sao gộp mọi lỗi vào một thông báo mơ hồ là thiếu hợp đồng?

### Checklist kết thúc

- [ ] Đã phân biệt rõ thành công, checked exception, unchecked exception và cleanup failure.
- [ ] Biết chính xác exception được ném ở đâu, catch nào bắt, tại đâu `throw e` và caller cuối cùng là ai.
- [ ] Mỗi phương thức cho checked exception thoát đều khai báo `throws` phù hợp hoặc xử lý theo luật Java.
- [ ] Khi dùng precise rethrow, biến catch không bị gán lại; không suy diễn `throws Exception` quá rộng.
- [ ] Khi chuyển đổi exception, wrapper có ngữ nghĩa domain và giữ `cause`.
- [ ] Không đặt `throw`/`return` gây che khuất lỗi gốc trong `finally`.
- [ ] Đã kiểm tra `getSuppressed()` nếu việc đóng tài nguyên cũng có thể thất bại.
- [ ] Không có catch dư thừa, catch rỗng, log lặp hoặc retry mù quáng.
- [ ] Bốn chương trình mẫu biên dịch và cho đúng output; các ca cố ý sai bị `javac` từ chối.
- [ ] Public API và các caller vẫn giữ được hợp đồng dự kiến sau thay đổi.

## Tài liệu chính thức, còn áp dụng trên Java hiện đại

- [Java Language Specification 17 — Chapter 11: Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): checked exception analysis, exception propagation và yêu cầu của phương thức.
- [Java Language Specification 17 — `14.20: `try`, `catch` và `finally`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): hành vi kiểm soát luồng và precise rethrow.
- [Java Language Specification 26 — `14.20: Try Statements](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-14.html#jls-14.20): đối chiếu quy tắc còn hiệu lực trong đặc tả mới.
- [Oracle Java Tutorial — Catching Multiple Exception Types and Rethrowing Exceptions](https://docs.oracle.com/javase/8/docs/technotes/guides/language/catch-multiple.html): nguồn mô tả cơ chế precise rethrow xuất hiện từ Java 7; xem JLS hiện hành để đối chiếu.
- [Java Platform API — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getCause()`, `getSuppressed()` và thông tin lỗi.

**Ghi nhớ:** `throw e` tiếp tục truyền **đúng đối tượng ngoại lệ đang được bắt**. Muốn kiểm tra đúng một phương thức, phải lần cả đường đi `try` → `catch` → `finally`/close → caller, xem **chữ ký `throws`**, loại exception, `cause` và `suppressed`. Precise rethrow của Java 7 giúp giữ chữ ký checked exception **đủ hẹp**, nhưng không thay thế việc thiết kế hợp đồng rõ ràng và kiểm thử đúng từng đường đi.