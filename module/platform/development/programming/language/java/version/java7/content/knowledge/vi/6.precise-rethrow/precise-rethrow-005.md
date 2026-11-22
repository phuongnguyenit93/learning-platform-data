# Ném lại ngoại lệ trong Java: Ảnh hưởng của việc thay đổi biến ngoại lệ

## 1. Vấn đề cần hiểu

Trong Java, biến khai báo tại `catch` là một **tham chiếu đến đối tượng exception vừa được bắt**. Khi ta dùng `throw e;`, Java ném đối tượng mà `e` đang tham chiếu tại thời điểm đó. Vì vậy, **việc gán lại biến ngoại lệ có thể thay đổi đối tượng thực sự được ném, làm mất hoặc thay đổi thông tin chẩn đoán và ảnh hưởng đến việc kiểm tra checked exception lúc biên dịch**.

Đặc biệt, từ **Java 7**, Java hỗ trợ **precise rethrow** (phân tích kiểu ngoại lệ chính xác khi ném lại). Tính năng này có liên hệ trực tiếp với việc biến `catch` có bị gán lại hay không.

Có ba tình huống khác nhau cần phân biệt:

1. `catch (Exception e)` và **không gán lại `e`**: `e` là *effectively final*. Trong điều kiện thích hợp, trình biên dịch phân tích `throw e;` dựa trên các checked exception có thể phát sinh từ `try` thay vì luôn coi nó là `Exception` chung chung.
2. `catch (Exception e)` và **gán lại `e`**: biến không còn *effectively final*. `throw e;` được xét theo kiểu khai báo của biến trong tình huống này; ví dụ, phương thức có thể phải khai báo `throws Exception` rộng hơn.
3. `catch (IOException | ParseException e)` (multi-catch): biến `e` **ngầm `final`**, nên **không được gán lại**. Có thể ném lại đối tượng gốc bằng `throw e;` hoặc tạo exception mới trong **biến khác**.

Các quy tắc này vẫn được Java hiện đại áp dụng, bao gồm Java 17+.

## 2. Đối tượng exception và biến tham chiếu là hai thứ khác nhau

Xét đoạn minh họa nằm bên trong một phương thức:

```java
try {
    readData();
} catch (IOException e) {
    IOException original = e;
    e = new IOException("another failure");

    System.out.println(e == original); // false
    throw e; // ném IOException mới, không còn ném original
}
```

Giả sử `readData()` có thể ném `IOException`. Khi một `IOException` bị bắt:

- `original` giữ tham chiếu đến **đối tượng exception gốc**.
- Phép gán `e = new IOException(...)` chỉ đổi **tham chiếu nằm trong biến `e`**; nó không tự chỉnh sửa đối tượng mà `original` đang giữ.
- Sau phép gán, `throw e;` ném **đối tượng mới**, có message và stack trace được tạo tại vị trí mới.
- Nếu đối tượng mới không được liên kết với `original` qua `cause`, chuỗi nguyên nhân gốc bị mất khỏi exception được truyền lên.

Đoạn trên là **minh họa**, không phải tệp Java độc lập. Trong ví dụ này, kiểu khai báo của `e` vẫn là `IOException`, nên bản thân việc gán lại **không buộc `throws` trở thành `Exception`**. Tuy nhiên, thay đổi đối tượng vẫn ảnh hưởng rõ rệt đến dữ liệu lỗi.

**Ghi nhớ:** “Thay đổi biến ngoại lệ” có ít nhất hai nghĩa cần tách bạch: **gán tham chiếu khác cho `e`** và **gọi phương thức làm thay đổi trạng thái của chính đối tượng exception**. Chúng là hai thao tác khác nhau.

## 3. Java 7 precise rethrow hoạt động thế nào?

### 3.1. Trước hết: checked exception và khai báo `throws`

Checked exception như `IOException` hoặc `ParseException` phải được bắt hoặc khai báo theo quy tắc kiểm tra ngoại lệ của Java. Một phương thức có thể khai báo nhiều kiểu cụ thể:

```java
static void load(boolean invalidFormat)
        throws IOException, ParseException {
    if (invalidFormat) {
        throw new ParseException("bad input", 3);
    }
    throw new IOException("disk unavailable");
}
```

Đây là **phương thức minh họa nằm trong một lớp** có import `java.io.IOException` và `java.text.ParseException`. Khi biên dịch, Java biết rằng thao tác `load(...)` có thể ném hai checked exception nêu trong chữ ký.

### 3.2. Single-catch với biến *effectively final*

Đoạn sau hợp lệ trên Java hiện đại:

```java
static void precise(boolean invalidFormat)
        throws IOException, ParseException {
    try {
        load(invalidFormat);
    } catch (Exception e) {
        System.out.println("captured="
                + e.getClass().getSimpleName());
        throw e;
    }
}
```

Mặc dù biến `e` được **khai báo là `Exception`** (rộng hơn `IOException` và `ParseException`), phương thức **không cần** `throws Exception`. Lý do:

- Phân tích checked exception của khối `try` cho thấy `load(...)` có thể ném `IOException` và `ParseException`.
- `catch (Exception e)` bắt cả hai loại.
- `e` **không bị gán lại** trong thân `catch`, nên nó là biến **effectively final**.
- `throw e;` đủ điều kiện cho **precise rethrow**; trình biên dịch phân tích các kiểu ngoại lệ có thể thực sự được ném từ khối `try`, phù hợp với `throws IOException, ParseException`.

Việc đọc `e.getMessage()`, truyền `e` vào hàm ghi log hoặc tạo biến khác tham chiếu tới `e` **không tự làm mất effectively final**, miễn bản thân `e` không được gán lại.

**Không hiểu sai:** Precise rethrow là quy tắc **phân tích tại lúc biên dịch**. Ở runtime, `throw e;` vẫn ném **chính đối tượng đang được tham chiếu**, với loại, message, cause và stack trace thực tế của nó.

### 3.3. Vì sao “effectively final” quan trọng?

Một biến local/parameter được coi là *effectively final* khi theo quy tắc ngôn ngữ nó không bị gán lại sau khi được khởi tạo. Với biến `catch (Exception e)`, chỉ cần để nguyên tham chiếu là được; **không bắt buộc viết từ khóa `final`**.

```java
try {
    load(true);
} catch (Exception e) {
    Exception same = e;              // hợp lệ; e không bị gán lại
    System.out.println(same.getMessage());
    throw e;                         // vẫn đủ điều kiện precise rethrow
}
```

Đoạn trên là minh họa trong một phương thức có `throws` phù hợp. Biến `same` được tạo mới, còn `e` giữ nguyên. Ngược lại, phép gán dù trông “vô hại” như `e = e;` cũng khiến `e` không còn thỏa điều kiện *effectively final*.

## 4. Điều gì xảy ra khi gán lại `e` trong một single-catch?

Trong **single-catch** như `catch (Exception e)`, Java **cho phép** gán lại biến nếu không khai báo `final`. Nhưng khi đã gán lại, compiler không thể áp dụng quy tắc precise rethrow như ở mục trước.

### 4.1. Ví dụ lỗi biên dịch vì mất precise rethrow

```java
// Minh họa CỐ Ý KHÔNG BIÊN DỊCH:
static void invalid(boolean invalidFormat)
        throws IOException, ParseException {
    try {
        load(invalidFormat);
    } catch (Exception e) {
        e = new Exception("translated failure", e);
        throw e; // lỗi: Exception rộng hơn throws đã khai báo
    }
}
```

Điểm quyết định nằm ở dòng **`e = new Exception(...)`**. Vì `e` đã bị gán lại, kiểu checked exception được xét tại `throw e;` là kiểu khai báo `Exception`, không còn bộ kiểu chính xác `IOException`/`ParseException` từ `try`.

Nếu khai báo chỉ `throws IOException, ParseException`, `javac` báo lỗi checked exception `Exception` chưa được xử lý hoặc khai báo, thường có dạng `unreported exception java.lang.Exception; must be caught or declared to be thrown`.

**Đây là lỗi compile-time**, ngay cả khi điều kiện chạy thực tế của chương trình có vẻ chỉ phát sinh hai exception ban đầu. Java không suy luận lại precise rethrow từ giá trị sau phép gán.

### 4.2. Có thể khai báo `throws Exception`, nhưng phải hiểu hệ quả

```java
static void changed(boolean invalidFormat) throws Exception {
    try {
        load(invalidFormat);
    } catch (Exception e) {
        e = new Exception("translated failure", e);
        throw e;
    }
}
```

Đoạn này hợp lệ vì phương thức khai báo `throws Exception`. Tuy nhiên:

- API của phương thức nay khai báo một loại checked exception **rộng hơn**, nên caller có thể phải xử lý `Exception` thay vì chỉ hai loại gốc.
- Đối tượng được ném ra là **`Exception` mới**, không còn đối tượng gốc.
- Vì constructor được gọi bằng `new Exception(message, e)`, exception gốc **được giữ làm cause**, nên vẫn có thể truy cập qua `getCause()`.
- Stack trace của exception mới đánh dấu **vị trí tạo wrapper**; stack trace của cause vẫn cho biết điểm phát sinh lỗi cũ.

Nếu viết `e = new Exception("translated failure");` mà **không truyền `e` làm cause**, bạn sẽ đánh mất quan hệ nguyên nhân trên exception được ném ra.

Đôi khi hợp đồng API có lý do chính đáng để khai báo một exception chung. Tuy nhiên, **gán lại biến catch không phải cách cần thiết để bọc exception**.

### 4.3. Tình huống tinh tế: kiểu catch đã hẹp sẵn

```java
static void handleIo() throws IOException {
    try {
        throw new IOException("disk unavailable");
    } catch (IOException e) {
        e = new IOException("replacement");
        throw e;
    }
}
```

Đoạn này vẫn biên dịch với `throws IOException` bởi vì kiểu khai báo của `e` **đã là `IOException`**. Điều mất đi ở đây là **đối tượng lỗi gốc**, không phải tính hợp lệ của chữ ký `throws`. Do đó không thể nói “cứ gán lại exception là chương trình không biên dịch”: **tác động đến kiểm tra kiểu phụ thuộc kiểu khai báo và các exception được ném**.

## 5. Multi-catch: không thể gán lại biến ngoại lệ

Từ Java 7, một multi-catch gom các kiểu exception có chính sách xử lý chung:

```java
static void handleBoth(boolean invalidFormat)
        throws IOException, ParseException {
    try {
        load(invalidFormat);
    } catch (IOException | ParseException e) {
        System.out.println(e.getMessage());
        throw e;
    }
}
```

Ở đây, `e` được **ngầm khai báo `final`**. Điều đó có nghĩa:

```java
// Minh họa CỐ Ý KHÔNG BIÊN DỊCH:
static void invalidMulti(boolean invalidFormat)
        throws IOException, ParseException {
    try {
        load(invalidFormat);
    } catch (IOException | ParseException e) {
        e = new IOException("replacement"); // lỗi biên dịch
        throw e;
    }
}
```

Trình biên dịch sẽ báo đại ý **`multi-catch parameter e may not be assigned`**. Điều cấm này áp dụng cho **mọi phép gán lại biến `e`**, kể cả `e = e;`; không phụ thuộc việc exception mới có cùng loại hay không.

Lý do cần phân biệt:

- **Single-catch `catch (Exception e)`:** biến **không tự động `final`**, có thể gán lại nhưng mất *effectively final*.
- **Multi-catch `catch (IOException | ParseException e)`:** biến **ngầm `final`**, gán lại là lỗi biên dịch.
- Trong cả hai trường hợp, `throw e;` khi `e` chưa bị gán lại vẫn có thể giữ nguyên đối tượng lỗi.
- Không nên dùng từ “effectively final” để mô tả chính xác bản chất khai báo của biến multi-catch: theo đặc tả nó là **implicitly final**.

Bên trong multi-catch, có thể **tạo biến khác** để lưu wrapper:

```java
try {
    load(invalidFormat);
} catch (IOException | ParseException e) {
    IllegalStateException wrapped =
            new IllegalStateException("load failed", e);
    throw wrapped;
}
```

Đây là minh họa trong một phương thức có `load(...)` và các import phù hợp. `e` không bị gán lại; cause của `wrapped` giữ thông tin gốc. Vì `IllegalStateException` là unchecked exception, phương thức không bắt buộc thêm `throws` chỉ để ném wrapper này.

## 6. So sánh ba chiến lược ném lại

| Cách xử lý | Đối tượng đi lên caller | Thông tin lỗi gốc | Ảnh hưởng đến checked exception |
| --- | --- | --- | --- |
| `throw e;`, `e` không bị gán lại | Chính đối tượng đã bắt | Giữ đầy đủ object/cause/stack trace ban đầu | Có thể dùng precise rethrow nếu đủ điều kiện |
| `e = new Exception("context", e); throw e;` | Exception mới | Giữ qua `getCause()` do đã truyền `e` cũ làm cause | Mất precise rethrow với catch `Exception`; có thể cần `throws Exception` |
| `throw new IllegalStateException("context", e);` | Wrapper unchecked mới | Giữ qua `getCause()` | Không cần khai báo wrapper unchecked; các exception trong `try` vẫn cần xử lý đúng |
| `throw new Exception("context");` | Exception mới | **Mất cause** nếu không liên kết lỗi cũ | Checked exception mới cần `throws`/`catch` thích hợp |
| `catch (A | B e) { e = ...; }` | Không có kết quả runtime | Không chạy vì lỗi biên dịch | Biến multi-catch ngầm final nên không gán được |

**Lời khuyên:** Với mục đích giữ nguyên lỗi, dùng `throw e;`. Nếu tầng hiện tại cần diễn đạt lại lỗi dưới khái niệm khác, tạo **wrapper mới** bằng constructor nhận `cause`, chẳng hạn `new ServiceException("...", e)`. Không cần sửa tham chiếu `e` chỉ để đổi loại exception.

## 7. Ví dụ Java 17+ đầy đủ: chính xác khi ném lại và thay biến

Chương trình sau cho thấy sự khác biệt giữa hai hàm:

- `precise` dùng `catch (Exception error)` nhưng **không gán lại** `error`; phương thức chỉ cần khai báo hai checked exception cụ thể.
- `changed` **gán lại** `error` thành một đối tượng `Exception` mới nên có chữ ký `throws Exception`. Constructor wrapper vẫn giữ nguyên lỗi ban đầu làm `cause`.

Tạo tệp **`RethrowVariableDemo.java`**:

```java
import java.io.IOException;
import java.text.ParseException;

public final class RethrowVariableDemo {

    static void load(boolean invalidFormat)
            throws IOException, ParseException {
        if (invalidFormat) {
            throw new ParseException("bad input", 3);
        }
        throw new IOException("disk unavailable");
    }

    static void precise(boolean invalidFormat)
            throws IOException, ParseException {
        try {
            load(invalidFormat);
        } catch (Exception error) {
            System.out.println("captured="
                    + error.getClass().getSimpleName());
            throw error;
        }
    }

    static void changed(boolean invalidFormat) throws Exception {
        try {
            load(invalidFormat);
        } catch (Exception error) {
            error = new Exception("translated failure", error);
            throw error;
        }
    }

    public static void main(String[] args) throws Exception {
        try {
            precise(false);
        } catch (IOException | ParseException error) {
            System.out.println("rethrown="
                    + error.getClass().getSimpleName());
            System.out.println("message=" + error.getMessage());
        }

        try {
            precise(true);
        } catch (IOException | ParseException error) {
            System.out.println("rethrown="
                    + error.getClass().getSimpleName());
        }

        try {
            changed(true);
        } catch (Exception error) {
            System.out.println("changed="
                    + error.getClass().getSimpleName());
            System.out.println("cause="
                    + error.getCause().getClass().getSimpleName());
            System.out.println("causeMessage="
                    + error.getCause().getMessage());
        }
    }
}
```

Biên dịch, chạy với JDK 17 trở lên:

```bash
javac RethrowVariableDemo.java
java RethrowVariableDemo
```

**Stdout chính xác:**

```text
captured=IOException
rethrown=IOException
message=disk unavailable
captured=ParseException
rethrown=ParseException
changed=Exception
cause=ParseException
causeMessage=bad input
```

**Giải thích:**

1. `precise(false)` bắt một `IOException`. Biến `error` không bị gán lại, nên `throw error;` ném chính exception gốc, và caller bắt được bằng `IOException | ParseException`.
2. `precise(true)` bắt `ParseException`, cũng giữ đúng loại runtime khi ném lại.
3. `changed(true)` ban đầu bắt `ParseException`, nhưng sau `error = new Exception(...)` thì `error` chỉ đến wrapper mới. Caller nhận đối tượng có loại runtime là `Exception`.
4. Vì wrapper được tạo bằng `new Exception("translated failure", error)`, `getCause()` trả `ParseException` gốc và `getMessage()` của cause vẫn là `"bad input"`.
5. `throws Exception` của `changed` là hệ quả của cách khai báo/ném lại biến rộng; nó không nói rằng exception gốc đã mất. Cause và kiểu kiểm tra compile-time là **hai trục độc lập**.

Chương trình này cho đầu ra ổn định, không cần thư viện ngoài, và minh họa riêng hành vi của **việc đổi tham chiếu `catch`**.

## 8. Đổi biến và chỉnh sửa chính đối tượng exception không giống nhau

### 8.1. Gán lại tham chiếu `e`

```java
Exception original = e;
e = new Exception("new error", original);
```

Dòng thứ hai làm `e` tham chiếu exception **khác**. Đối tượng cũ vẫn có thể truy cập qua `original` hoặc `e.getCause()` nếu wrapper được tạo đúng.

### 8.2. Đọc thông tin không làm mất effectively final

```java
String message = e.getMessage();
Throwable cause = e.getCause();
StackTraceElement[] frames = e.getStackTrace();
```

Các dòng này không gán lại `e`, nên **không tự vô hiệu hóa precise rethrow**. Chúng chỉ đọc thông tin. Tuy nhiên, đọc một số trường chẩn đoán khác với đảm bảo chúng luôn khác `null`: chẳng hạn `getCause()` có thể `null`, stack trace có thể rỗng.

### 8.3. Gọi phương thức làm thay đổi trạng thái Throwable

Một số phương thức có thể tác động đến **chính đối tượng exception**:

- `e.addSuppressed(another)` gắn thêm exception phụ nếu được phép; không đổi tham chiếu `e`, nhưng thay đổi thông tin được báo cáo.
- `e.fillInStackTrace()` ghi lại stack trace theo điểm gọi hiện tại, có thể che đi vị trí exception ban đầu; cần tránh khi mục tiêu là giữ nguyên chẩn đoán.
- `e.initCause(cause)` cố thiết lập cause và có ràng buộc nghiêm ngặt; nếu cause đã được khởi tạo, có thể ném `IllegalStateException`. Thay vì sửa cause trên exception gốc, thường nên tạo wrapper mới bằng constructor nhận `cause`.

**Điểm then chốt:** Precise rethrow chủ yếu phụ thuộc điều kiện **biến bắt lỗi có bị gán lại hay không**. Việc gọi method trên `e` có thể không làm biến mất *effectively final*, nhưng vẫn có thể **làm thay đổi chẩn đoán runtime**. Đừng đồng nhất hai vấn đề.

## 9. Giữ nguyên nguyên nhân khi chuyển đổi lỗi theo tầng

Ở ranh giới giữa các tầng (ví dụ đọc dữ liệu → xử lý nghiệp vụ), đôi khi cần đổi loại exception để API không phụ thuộc vào chi tiết của thư viện bên dưới. Hãy tạo loại exception nghiệp vụ rõ nghĩa:

```java
final class ImportFailure extends RuntimeException {
    ImportFailure(String message, Throwable cause) {
        super(message, cause);
    }
}

static void importFile(boolean invalidFormat) {
    try {
        load(invalidFormat);
    } catch (IOException | ParseException e) {
        throw new ImportFailure("Cannot import document", e);
    }
}
```

Đây là **đoạn minh họa trong cùng một lớp** có phương thức `load(...)` đã giới thiệu. Cách viết này:

- Không gán lại biến multi-catch `e` nên không vi phạm quy tắc ngầm final.
- Tạo lỗi tầng nghiệp vụ chứa **ngữ cảnh mới** và vẫn giữ cause là exception gốc.
- Cho phép công cụ log in được cả stack trace của wrapper và cause.
- Không cần nới chữ ký `throws` của `importFile` chỉ vì `ImportFailure` là unchecked exception.

Nếu chính sách API yêu cầu exception checked riêng, có thể thiết kế `ImportFailure extends Exception` rồi khai báo `throws ImportFailure` phù hợp. **Đừng chọn checked hay unchecked chỉ để né quy tắc ngôn ngữ; hãy dựa trên hợp đồng xử lý lỗi của tầng gọi.**

### 9.1. Không nên log rồi ném lại ở mọi tầng

```java
catch (IOException | ParseException e) {
    LOG.log(System.Logger.Level.ERROR, "Import failed", e);
    throw e;
}
```

Đoạn này hợp lệ trong phương thức có chữ ký `throws` phù hợp, nhưng nếu caller cũng ghi log cùng exception, bạn có thể tạo nhiều log trùng. Thường nên giữ exception/cause trong các tầng trung gian và ghi log đầy đủ tại ranh giới nơi lỗi được xử lý cuối cùng.

Với logger, truyền **đối tượng `Throwable`** quan trọng hơn việc chỉ ghi `e.getMessage()`. Đồng thời tránh đưa secret, token, mật khẩu hoặc dữ liệu nhạy cảm vào message khi thêm ngữ cảnh.

## 10. Bảng quy tắc kiểm tra lúc biên dịch

| Trường hợp | Có thể gán lại biến `catch`? | `throw e;` có thể precise rethrow? |
| --- | --- | --- |
| `catch (Exception e)` không gán lại | **Có thể** theo cú pháp, nhưng thực tế **không gán** | **Có**, khi đủ điều kiện phân tích các kiểu ném từ `try` |
| `catch (Exception e)` đã có `e = ...` | **Có**, vì single-catch không ngầm final | **Không** theo điều kiện biến effectively final; xét kiểu khai báo của `e` |
| `catch (final Exception e)` | **Không** | **Có**, nếu điều kiện về các kiểu trong `try` phù hợp |
| `catch (IOException e)` với `e = new IOException(...)` | **Có** nếu không `final` | Không áp dụng precise rethrow theo cùng điều kiện, nhưng `throws IOException` vẫn đủ nếu ném lại một `IOException` |
| `catch (IOException | ParseException e)` | **Không**, biến ngầm final | **Có**, với các checked exception thực sự có thể được ném |
| `catch (IOException | ParseException e)` với `e = ...` | **Không hợp lệ khi biên dịch** | Không có hành vi runtime để đánh giá |

Một lỗi thực tế là nhìn thấy `throws Exception` xuất hiện sau khi sửa code rồi nghĩ rằng “compiler phân tích ngoại lệ kém hơn phiên bản cũ”. Thực ra **việc gán lại biến** đã thay đổi cơ sở để compiler sử dụng precise rethrow.

## 11. Những nhầm lẫn thường gặp

1. **“Biến `catch` luôn là final.”** Sai: single-catch thông thường không ngầm final; multi-catch có nhiều lựa chọn kiểu `A | B` mới ngầm final.
2. **“Không viết `final` thì không thể precise rethrow.”** Sai: single-catch biến **effectively final** cũng được áp dụng.
3. **“Gán lại exception chỉ là thay message, không ảnh hưởng gì khác.”** Sai: khi gán đối tượng mới, kiểu runtime, stack trace, cause và yêu cầu checked exception có thể thay đổi.
4. **“Gán lại biến trong multi-catch được nếu cùng loại.”** Sai: biến multi-catch ngầm final, cấm mọi phép gán.
5. **“`throw e;` luôn yêu cầu `throws Exception` khi `e` khai báo `Exception`.”** Sai: precise rethrow có thể giới hạn các checked exception theo `try` nếu biến đủ điều kiện.
6. **“Nếu `e = new Exception("failed", e)` thì chắc chắn mất lỗi gốc.”** Sai: lỗi gốc vẫn có trong `getCause()`. Nó chỉ mất khi không được giữ lại qua cause hoặc cơ chế tương đương.
7. **“`e.addSuppressed(x)` giống `e = x`.”** Sai: lời gọi thứ nhất thay đổi đối tượng; câu lệnh thứ hai thay tham chiếu của biến.
8. **“`e.fillInStackTrace()` vô hại khi cần giữ dấu vết ban đầu.”** Không đúng: nó có thể ghi lại stack trace tại vị trí khác.
9. **“Bọc exception luôn cần gán `e = new ...`.”** Sai: có thể `throw new ServiceException("context", e);` trực tiếp.
10. **“Chỉ cần lưu `e.getMessage()` là đủ để điều tra.”** Sai: thông điệp có thể thiếu loại lỗi, stack trace, nguyên nhân và suppressed exceptions.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Với `catch (Exception e) { throw e; }`, phương thức có bắt buộc phải khai báo `throws Exception` không?  
**Đáp án:** Không nhất thiết. Nếu `e` không bị gán lại và khối `try` chỉ có thể ném những checked exception cụ thể được phân tích, precise rethrow có thể cho phép khai báo đúng các loại đó.

**Câu 2.** Nếu thêm `e = new Exception("context", e);` ngay trước `throw e;` thì điều gì đổi?  
**Đáp án:** Biến `e` mất trạng thái effectively final, precise rethrow không còn áp dụng; đối tượng được ném là wrapper mới, và có thể cần khai báo `throws Exception`. Nếu đã truyền `e` cũ làm cause, thông tin gốc vẫn được giữ.

**Câu 3.** Có thể dùng `catch (IOException | ParseException e) { e = new IOException(); }` không?  
**Đáp án:** Không. Biến của multi-catch được ngầm khai báo `final`; phép gán trực tiếp là lỗi biên dịch.

**Câu 4.** Tại sao `catch (IOException e) { e = new IOException("x"); throw e; }` có thể hợp lệ với `throws IOException`?  
**Đáp án:** Vì kiểu tĩnh của `e` vẫn là `IOException`, nhưng exception gốc không còn là đối tượng được ném.

**Câu 5.** Nếu cần thêm ngữ cảnh nghiệp vụ và bảo tồn nguyên nhân, viết thế nào?  
**Đáp án:** Tạo exception mới bằng constructor nhận cause, ví dụ `throw new ServiceException("Cannot import record", e);`, thay vì thay đổi biến `e` và đánh mất precise rethrow.

**Câu 6.** Gọi `e.getMessage()` và `logger.log(..., e)` có làm `e` không còn effectively final không?  
**Đáp án:** Không, các lệnh đó không gán lại biến `e`. Việc biến được dùng làm đối số của phương thức không đồng nghĩa gán lại.

## 13. Tóm tắt và tài liệu chính thức

**Kết luận thực hành:**

- **Để nguyên tham chiếu của biến `catch`** khi muốn ném lại exception gốc. Với single-catch đủ điều kiện, Java 7+ có thể phân tích precise rethrow và giữ chữ ký `throws` cụ thể.
- **Không gán lại biến trong multi-catch**: Java ngầm coi nó là `final`.
- **Chọn wrapper có cause** khi cần dịch ngoại lệ qua ranh giới nghiệp vụ; điều đó giữ stack trace và thông tin nguyên nhân trong exception chain.
- **Hiểu rõ sự khác nhau giữa compile-time và runtime**: phân tích checked exception không quyết định nội dung của đối tượng Throwable, còn đổi tham chiếu thì có thể đổi đối tượng thực sự được ném.
- **Tránh thao tác phá hủy chẩn đoán** như chỉ lưu message, tạo exception mới không có cause hoặc ghi lại stack trace gốc khi không cần.

Tài liệu chính thức còn hiệu lực:

- [Java Language Specification, `11.2.2 — Exception Analysis of Statements and Constructor Invocations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-11.html#jls-11.2.2): cách phân tích kiểu ngoại lệ của `throw` và precise rethrow.
- [Java Language Specification, `14.20 — The `try` Statement](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.20): single-catch, multi-catch, biến ngoại lệ ngầm final và effectively final.
- [Java SE 17 API — `Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getCause`, `getStackTrace`, `addSuppressed`, `fillInStackTrace`.