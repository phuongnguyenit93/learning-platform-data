# Kết hợp kiểu ngoại lệ bằng dấu `|` trong multi-catch (Java 7+)

> **Trọng tâm:** Cú pháp `catch (A | B exception)`, ý nghĩa của dấu `|`, các quy tắc mà trình biên dịch kiểm tra, kiểu của biến ngoại lệ và cách dùng đúng trong code Java hiện đại. Đây là tính năng được giới thiệu ở Java 7, vẫn hợp lệ và hữu ích trên Java 17, 21 và các JDK mới. Bài không dùng các API đã lỗi thời; ví dụ độc lập được thiết kế cho JDK 17+.

## 1. Vì sao Java cho phép kết hợp kiểu ngoại lệ?

Một khối `try` có thể gây ra nhiều loại ngoại lệ. Đôi khi, dù nguyên nhân kỹ thuật khác nhau, tầng gọi cần phản ứng **giống nhau** với một số loại lỗi. Viết những nhánh `catch` giống hệt nhau làm lặp logic, khiến chúng dễ lệch khi sửa đổi.

Trước khi gộp, ta có thể thấy:

```java
try {
    // Phân tích dữ liệu đầu vào.
} catch (NumberFormatException error) {
    return "INVALID_INPUT";
} catch (DateTimeParseException error) {
    return "INVALID_INPUT";
}
```

Với cùng chính sách từ chối dữ liệu:

```java
try {
    // Phân tích dữ liệu đầu vào.
} catch (NumberFormatException | DateTimeParseException error) {
    return "INVALID_INPUT";
}
```

Hai đoạn này là **minh họa đặt trong method trả `String`**, cần khối `try` và các thao tác thực tế phù hợp. `DateTimeParseException` nằm trong `java.time.format` (API Java 8); việc dùng nó bên trong cú pháp multi-catch Java 7 là hoàn toàn bình thường trên JDK hiện đại.

Điều cần ghi nhớ: **dấu `|` cho phép liệt kê nhiều kiểu ngoại lệ trong cùng một khai báo `catch`**. Khi một trong các loại đó được ném từ phần `try`, cùng một thân `catch` được thực thi. Dấu này không tự xử lý lỗi, không biến các lớp thành một lớp mới và không khiến ngoại lệ gốc mất đi.

## 2. Cú pháp chính xác

Cấu trúc tổng quát:

```java
try {
    riskyOperation();
} catch (FirstException | SecondException error) {
    handle(error);
}
```

Đây là **mã minh họa cú pháp**: các class exception và method `riskyOperation`/`handle` cần được thay bằng thành phần thực tế của ứng dụng.

| Thành phần | Ý nghĩa |
| --- | --- |
| `try` | Phạm vi chứa các phép toán có thể phát sinh ngoại lệ |
| `FirstException`, `SecondException` | Các kiểu ngoại lệ cần cùng một khối xử lý |
| Dấu `\|` giữa các kiểu | Ký hiệu phân tách *alternative* trong khai báo `catch` |
| `error` | **Một** biến tham số catch, tham chiếu đến **đối tượng ngoại lệ đã xảy ra** |
| Thân `catch` | Chạy khi ngoại lệ phù hợp với bất kỳ alternative nào |
| Các khối `catch` đứng sau | Có thể xử lý những loại lỗi khác theo quy tắc reachability/thứ tự |

### 2.1. `|` không phải `||`

Trong `catch (A | B e)`, `|` là ký hiệu ngữ pháp để phân tách các kiểu. Nó không được đánh giá như phép toán bitwise OR và cũng không phải biểu thức boolean.

Viết `catch (IOException || SQLException e)` là **sai cú pháp**. `||` dùng cho biểu thức boolean như `if (ready || retryAllowed)`, không dùng giữa các tên lớp exception.

### 2.2. Có thể kết hợp hơn hai kiểu

Không bị giới hạn ở hai alternative:

```java
catch (IOException | SQLException | ParseException error) {
    reportFailure(error);
}
```

Đây là **snippet minh họa**, với `reportFailure` do ứng dụng định nghĩa và một khối `try` có thể ném ba checked exceptions đó. Cần import:

```java
import java.io.IOException;
import java.sql.SQLException;
import java.text.ParseException;
```

Ba exception trên không kế thừa lẫn nhau. Việc có thể viết chung về mặt cú pháp **không đồng nghĩa nên gộp**: chỉ gộp nếu ba loại lỗi có cùng chính sách xử lý trong ngữ cảnh đang xét.

### 2.3. Một đối tượng lỗi, một lần xử lý

Khi `SQLException` xảy ra, Java chọn khối `catch (IOException | SQLException e)`, biến `e` tham chiếu đúng đối tượng `SQLException` đó. Nếu `IOException` xảy ra, `e` tham chiếu đối tượng `IOException`. Không có hai khối chạy liên tiếp, không tạo exception tổng hợp và không thay đổi `getCause()` hay stack trace chỉ vì dùng `|`.

## 3. Ví dụ chạy được: kết hợp hai lỗi parse

Ví dụ xử lý bản ghi có định dạng `yyyy-MM-dd,quantity`. Ngày sai và số lượng không phải số đều cùng chính sách `INVALID`.

Lưu thành `PipeParseDemo.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;

public class PipeParseDemo {
    static String parse(String raw) {
        String[] fields = raw.split(",", -1);
        if (fields.length != 2) {
            return "INVALID";
        }

        try {
            LocalDate date = LocalDate.parse(fields[0]);
            int quantity = Integer.parseInt(fields[1]);

            if (quantity < 0) {
                return "INVALID";
            }
            return "OK " + date + " " + quantity;
        } catch (DateTimeParseException | NumberFormatException error) {
            return "INVALID";
        }
    }

    public static void main(String[] args) {
        System.out.println(parse("2026-11-04,3"));
        System.out.println(parse("wrong,3"));
        System.out.println(parse("2026-11-04,abc"));
        System.out.println(parse("2026-11-04,-1"));
    }
}
```

Biên dịch/chạy trên JDK 17+:

```bash
javac -encoding UTF-8 --release 17 PipeParseDemo.java
java PipeParseDemo
```

Stdout:

```text
OK 2026-11-04 3
INVALID
INVALID
INVALID
```

**Diễn giải từng đường đi:**

1. `2026-11-04,3`: parse ngày và số thành công, không vào `catch`.
2. `wrong,3`: `LocalDate.parse` phát sinh `DateTimeParseException`, khối multi-catch chạy.
3. `2026-11-04,abc`: `Integer.parseInt` phát sinh `NumberFormatException`, cũng đi vào **cùng** khối catch.
4. `2026-11-04,-1`: số parse hợp lệ nhưng vi phạm điều kiện `quantity < 0`; method trả `INVALID` bằng điều kiện thông thường, không cần cố tình ném exception.

Dữ liệu `raw == null` gây `NullPointerException` tại `split` nằm ngoài `try`; ví dụ này cố ý không biến lỗi gọi API sai thành lỗi parse. Nếu API cần chấp nhận null, thêm kiểm tra đầu vào riêng theo hợp đồng.

**Phiên bản:** `catch (A | B e)` xuất hiện từ Java 7. `LocalDate` và `DateTimeParseException` xuất hiện ở Java 8. Đây là ví dụ hiện đại dùng tính năng Java 7, không phải tuyên bố mọi API trong ví dụ đều tồn tại ở Java 7.

## 4. Luật bắt buộc: các alternative không được kế thừa lẫn nhau

Điều kiện quan trọng nhất của multi-catch là **không alternative nào được là subtype của alternative khác** trong cùng danh sách.

Ví dụ **không thể biên dịch**:

```java
// FileNotFoundException extends IOException:
catch (FileNotFoundException | IOException error) {
    report(error);
}

// NumberFormatException extends IllegalArgumentException:
catch (NumberFormatException | IllegalArgumentException error) {
    report(error);
}
```

Các đoạn trên chỉ minh họa lỗi; `report` là helper giả định. Lý do: kiểu cha đã bao trùm kiểu con, nên đặt cả hai trong danh sách alternative là dư thừa và bị Java Language Specification cấm.

Nếu muốn **cùng xử lý toàn bộ nhóm `IOException`**, dùng một catch kiểu cha:

```java
catch (IOException error) {
    report(error);
}
```

Nếu chỉ muốn **xử lý riêng `FileNotFoundException`**, rồi bắt những `IOException` còn lại, viết hai catch theo thứ tự cụ thể → tổng quát:

```java
catch (FileNotFoundException error) {
    reportMissingFile(error);
} catch (IOException error) {
    reportOtherIoFailure(error);
}
```

Những snippet này phải đặt sau một khối `try` có thể phát sinh các exception tương ứng. **Không đảo thứ tự:** `catch (IOException)` đứng trước sẽ bắt cả `FileNotFoundException`, làm catch con sau đó không thể đến và gây lỗi biên dịch.

### 4.1. Cùng cha chưa chắc là cha–con của nhau

`SocketTimeoutException` và `FileNotFoundException` đều là subtype của `IOException`, nhưng không subtype nào là cha của subtype kia. Vì vậy, về quan hệ kiểu, cách kết hợp:

```java
catch (SocketTimeoutException | FileNotFoundException error) {
    // Cùng xử lý khi có chủ đích.
}
```

có thể hợp lệ nếu `try` thực sự có thể ném các checked exception đó. Chỉ dùng khi ứng dụng thực sự cần cùng phản ứng. Ví dụ timeout thường có thể retry, còn không tìm thấy file thường cần sửa đường dẫn; nếu chính sách khác nhau thì giữ riêng, dù cú pháp cho phép.

### 4.2. Không có toán tử “phủ định ngoại lệ” trong catch

Multi-catch có thể liệt kê những loại cần bắt; không có cú pháp kiểu `catch (IOException | !FileNotFoundException e)` để tự trừ subtype. Nếu cần chính sách theo subtype, hãy viết các catch cụ thể phù hợp và sắp xếp đúng thứ tự.

## 5. Checked exception và khả năng xảy ra trong `try`

Java kiểm tra tính hợp lệ của các alternative **khi biên dịch**. Với checked exceptions như `IOException`, `SQLException`, `ParseException`:

- Khối `try` phải có khả năng phát sinh checked exception phù hợp với từng alternative, theo phân tích tĩnh của compiler.
- Nếu đưa vào một checked exception không thể phát sinh từ khối `try`, compiler có thể báo lỗi *exception is never thrown in body of corresponding try statement*.
- Với unchecked exceptions (`RuntimeException` và các subtype), không yêu cầu được khai báo trong `throws`, nhưng vẫn phải tuân thủ luật alternative và thứ tự catch.

Ví dụ này **cố ý không biên dịch**:

```java
try {
    throw new IOException("file error");
} catch (IOException | SQLException error) {
    System.out.println(error.getMessage());
}
```

Nếu khối `try` không có hoạt động nào có thể ném `SQLException`, alternative checked đó là dư và không hợp lệ theo kiểm tra compile-time.

Không có nghĩa một exception phải chắc chắn được ném **mỗi lần chạy**. Chỉ cần luồng code hoặc method được gọi có khả năng phát sinh loại checked exception đó. Đây là phân tích tĩnh của ngôn ngữ, không phải kết quả phụ thuộc vào dữ liệu runtime cụ thể.

## 6. Ví dụ chạy được: `IOException | SQLException`

Hai ngoại lệ checked thường gặp ở tầng nhập dữ liệu là `IOException` và `SQLException`. Chương trình sau mô phỏng ba trường hợp có thể dự đoán, giúp quan sát rằng multi-catch không làm mất loại exception gốc.

Lưu thành `CheckedAlternativesDemo.java`:

```java
import java.io.IOException;
import java.sql.SQLException;

public class CheckedAlternativesDemo {
    static void run(int scenario) throws IOException, SQLException {
        if (scenario == 1) {
            throw new IOException("disk");
        }
        if (scenario == 2) {
            throw new SQLException("db");
        }
    }

    public static void main(String[] args) {
        for (int scenario = 0; scenario < 3; scenario++) {
            try {
                run(scenario);
                System.out.println("case " + scenario + ": OK");
            } catch (IOException | SQLException error) {
                System.out.println(
                    "case " + scenario + ": "
                    + error.getClass().getSimpleName()
                    + ", " + error.getMessage()
                );
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 CheckedAlternativesDemo.java
java CheckedAlternativesDemo
```

Stdout:

```text
case 0: OK
case 1: IOException, disk
case 2: SQLException, db
```

**Điều ví dụ xác nhận:**

- `run` khai báo có thể ném cả hai checked exceptions, nên hai alternative được compiler chấp nhận.
- Khi lỗi là `IOException`, `error.getClass().getSimpleName()` vẫn trả `IOException`.
- Khi lỗi là `SQLException`, vẫn nhận diện được `SQLException`. Java không thay thế hai loại bằng một class tổng hợp tên `IOException|SQLException`.
- Cả hai dùng chung method `getMessage()`, nên khối catch biên dịch và in chính xác.

Trong dự án thật, chỉ đặt `IOException` và `SQLException` chung một catch khi chính sách xử lý ở tầng đó giống nhau. Tầng bên dưới vẫn có thể phân biệt các nguyên nhân để chẩn đoán qua class, cause và stack trace.

## 7. Kiểu của biến `error` trong multi-catch

Một điều dễ nhầm là cho rằng `error` có thể tự động gọi mọi method của tất cả alternative. **Không đúng.**

Về mặt kiểm tra kiểu, Java xác định **kiểu chung phù hợp** từ các alternative, theo các quy tắc của hệ thống generic/type inference và *least upper bound*. Biến `error` là **một biến tham số duy nhất**. Các thao tác trong thân catch phải hợp lệ với kiểu tĩnh chung đó.

Ví dụ:

```java
catch (IOException | SQLException error) {
    String message = error.getMessage();  // Hợp lệ: Throwable có getMessage
    Throwable cause = error.getCause();   // Hợp lệ: Throwable có getCause
}
```

Các nhánh có thể cần method chỉ có ở subtype. Trường hợp **không biên dịch**:

```java
catch (IOException | SQLException error) {
    System.out.println(error.getSQLState());
    // ERROR: kiểu tĩnh chung không bảo đảm getSQLState().
}
```

`SQLException.getSQLState()` là method chuyên biệt của SQL exception. Nếu thật sự cần kiểm tra `SQLState` để xác định retry hoặc mapping lỗi, hãy dùng `catch (SQLException e)` riêng. Trên JDK mới, có thể kiểm tra kiểu runtime với `instanceof` trước khi gọi method riêng, nhưng nếu các phương án xử lý đã khác, **hai catch tách biệt thường thể hiện ý định rõ hơn**.

### 7.1. Biến trong multi-catch là implicitly final

Java không cho gán lại biến `error` của multi-catch:

```java
catch (IOException | SQLException error) {
    error = new IOException("other"); // ERROR: không được gán lại
}
```

Đó là lỗi compile-time **có chủ đích**. Nếu muốn tạo một exception ở tầng nghiệp vụ, tạo một đối tượng mới và giữ cause gốc:

```java
catch (IOException | SQLException error) {
    throw new ImportFailureException("Không thể nhập dữ liệu", error);
}
```

Đây là snippet dùng class `ImportFailureException` giả định do ứng dụng định nghĩa với constructor `(String, Throwable)`. Không gán lại biến catch để “thay” exception; việc truyền nguyên nhân gốc vào constructor giúp giữ thông tin phục vụ truy vết.

## 8. Multi-catch và ném lại exception

Bắt được exception **không bắt buộc phải nuốt hoặc đổi exception**. Nếu tầng hiện tại chỉ bổ sung thông tin rồi ném lại, cùng đối tượng lỗi ban đầu có thể tiếp tục được truyền lên caller. Java 7 còn bổ sung *precise rethrow*: compiler có thể suy luận các checked exception cụ thể phát sinh từ khối `try` khi catch variable không bị gán lại.

Lưu thành `RethrowAlternativesDemo.java`:

```java
import java.io.IOException;
import java.sql.SQLException;

public class RethrowAlternativesDemo {
    static void operation(int scenario) throws IOException, SQLException {
        try {
            if (scenario == 1) {
                throw new IOException("file failed");
            }
            if (scenario == 2) {
                throw new SQLException("sql failed");
            }
        } catch (IOException | SQLException error) {
            System.out.println("observed=" + error.getClass().getSimpleName());
            throw error;
        }
    }

    public static void main(String[] args) {
        for (int scenario = 1; scenario <= 3; scenario++) {
            try {
                operation(scenario);
                System.out.println("completed");
            } catch (IOException | SQLException error) {
                System.out.println("caller=" + error.getClass().getSimpleName());
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 RethrowAlternativesDemo.java
java RethrowAlternativesDemo
```

Stdout:

```text
observed=IOException
caller=IOException
observed=SQLException
caller=SQLException
completed
```

Ở đây, một catch xử lý hai alternative và dùng `throw error` để truyền **cùng đối tượng** lên caller. `throws IOException, SQLException` vẫn là hợp đồng checked exception của method `operation`. Code không biến lỗi thành `Exception` chung chỉ vì hai kiểu đứng cạnh dấu `|`.

**Đừng dùng `throw new RuntimeException(error)` chỉ để tránh khai báo `throws`** nếu điều đó không phù hợp hợp đồng exception của hệ thống. Nếu cần exception translation, đặt tên loại lỗi ở tầng domain, giữ cause và cân nhắc tác động lên caller/test.

## 9. Multi-catch, nhiều catch riêng và catch kiểu cha khác nhau ra sao?

Ba hình thức sau có thể rất khác nhau về phạm vi:

**Nhiều catch riêng:**

```java
catch (IOException error) {
    handleIo(error);
} catch (SQLException error) {
    handleSql(error);
}
```

Có thể gắn chính sách khác nhau. Hai helper giả định dùng type chuyên biệt tương ứng.

**Một multi-catch:**

```java
catch (IOException | SQLException error) {
    handleSharedFailure(error);
}
```

Thực thi một chính sách chung cho **hai loại được liệt kê** (và các subtype tương ứng) nếu được ném từ try. Helper phải chấp nhận kiểu tham số chung phù hợp, chẳng hạn `Throwable`.

**Một catch kiểu cha rộng:**

```java
catch (Exception error) {
    handleSharedFailure(error);
}
```

Bắt một tập exception rộng hơn nhiều, bao gồm cả các loại **không dự định gộp**. Nó có thể che lỗi lập trình và làm sai phân loại của tầng API. Chỉ dùng catch rộng khi phạm vi trách nhiệm thực sự đòi hỏi, không dùng như lối tắt để thay multi-catch.

Các snippet này là ba phương án **thay thế nhau** sau một khối try và các helper giả định, không đặt cả ba liên tiếp với thứ tự khiến nhánh sau không thể tới.

**So sánh quan trọng:** `catch (IOException | SQLException e)` có thể bắt subtype của hai loại đó, nhưng không mặc định bắt `NumberFormatException` hay `NullPointerException`. `catch (Exception e)` thường bắt cả những exception runtime này. Độ rộng bắt lỗi là một phần của hợp đồng hành vi.

## 10. Trường hợp không nên kết hợp bằng dấu `|`

Đúng cú pháp vẫn chưa đủ để đảm bảo đúng thiết kế.

### 10.1. Lỗi cần phản ứng khác nhau

Giả sử:

```java
catch (NumberFormatException error) {
    return "INVALID_CONFIG";
} catch (IOException error) {
    return "FILE_UNAVAILABLE";
}
```

Đây là snippet trong method trả `String`. Hai loại exception **không có quan hệ cha–con** nên có thể liệt kê trong một multi-catch, nhưng **không nên** nếu một lỗi yêu cầu sửa cấu hình và lỗi khác yêu cầu kiểm tra filesystem. Gộp sẽ làm mất trạng thái có ý nghĩa với caller.

Tương tự, nếu `SQLException` cần đánh giá SQL state để quyết định retry nhưng `IOException` cần cảnh báo vận hành, nên tách nhánh. Multi-catch không tự chọn retry/backoff phù hợp.

### 10.2. Chỉ có một vài dòng chung

Hai catch cùng gọi logger không đồng nghĩa toàn bộ hành vi giống nhau. Có thể trích mã log thành helper nhưng giữ riêng `return`/`throw` và side effect:

```java
catch (IOException error) {
    recordError(error);
    return "STORAGE_ERROR";
} catch (NumberFormatException error) {
    recordError(error);
    return "BAD_INPUT";
}
```

Đây là đoạn minh họa; `recordError` do ứng dụng định nghĩa. Phần chung có thể tái sử dụng nhưng hai kết quả khác nhau.

### 10.3. Bắt loại lỗi quá tổng quát

`catch (RuntimeException | IOException e)` có thể hợp lệ nếu `try` có khả năng phát sinh `IOException`, nhưng bắt toàn bộ `RuntimeException` có nguy cơ xếp cả lỗi lập trình, trạng thái sai hoặc dữ liệu không hợp lệ vào một nhóm. Hãy dùng các exception cụ thể mà tầng hiện tại **thật sự biết xử lý**.

### 10.4. Chỉ muốn bỏ qua một subtype

Không dùng multi-catch để “bắt mọi IOException trừ một subtype”. Thay vào đó, bắt subtype cần xử lý riêng trước, rồi catch kiểu cha khi cần. Chính sách rõ ràng hơn và tránh lỗi quan hệ kế thừa.

## 11. Kết hợp với try-with-resources mà không nhầm trách nhiệm

Multi-catch và try-with-resources đều là tính năng từ Java 7 nhưng phục vụ hai mục tiêu khác nhau:

- `try-with-resources` quản lý vòng đời tài nguyên implements `AutoCloseable`.
- `catch (A | B e)` quyết định những kiểu ngoại lệ nào chia sẻ một hành động khi lỗi phát sinh.

Mã minh họa:

```java
try (java.io.BufferedReader reader =
         java.nio.file.Files.newBufferedReader(path, java.nio.charset.StandardCharsets.UTF_8)) {
    int count = Integer.parseInt(reader.readLine());
    useCount(count);
} catch (java.io.IOException | NumberFormatException error) {
    reportInvalidInput(error);
}
```

Đây là snippet trong method đã có `Path path`, `useCount` và `reportInvalidInput` được định nghĩa. Phần `try` có thể sinh `IOException` khi mở/đọc/đóng file và `NumberFormatException` khi parse số. Chỉ gộp nếu yêu cầu thật sự coi cả hai là cùng kết quả xử lý; nếu I/O và format cần phân biệt, giữ catch riêng.

**Một chi tiết quan trọng:** nếu thân try ném exception rồi `close()` cũng ném exception, try-with-resources giữ lỗi đóng trong `getSuppressed()` trên lỗi chính. Multi-catch không xóa suppressed exceptions. Khi kiểm tra lỗi, nên giữ thông tin này thay vì nuốt hoặc thay exception thiếu cause.

## 12. Những lỗi cú pháp và lỗi suy luận thường gặp

| Viết hoặc hiểu sai | Lý do | Cách làm đúng |
| --- | --- | --- |
| `catch (A \|\| B e)` | `\|\|` là boolean OR, không phải dấu phân tách kiểu | `catch (A \| B e)` |
| `catch (IOException \| FileNotFoundException e)` | Quan hệ cha–con | Catch `IOException`, hoặc tách nhánh con trước |
| `catch (NumberFormatException \| IllegalArgumentException e)` | `NumberFormatException` là subtype của `IllegalArgumentException` | Chọn kiểu cha hoặc xử lý riêng đúng thứ tự |
| `catch (IOException \| SQLException e)` khi try không thể ném SQL exception | Checked alternative không thể phát sinh | Bỏ alternative dư hoặc sửa phạm vi try đúng trách nhiệm |
| `e.getSQLState()` trong catch `IOException \| SQLException` | Biến e có kiểu tĩnh chung | Giữ catch SQL riêng nếu cần method đặc thù |
| `e = new IOException(...)` trong multi-catch | Biến e implicitly final | Tạo exception mới và `throw` khi cần |
| Coi `\|` là tạo một class mới | Đối tượng vẫn có class gốc | Dùng `getClass()`/`getCause()` để chẩn đoán |
| Dùng `catch (Exception e)` thay multi-catch | Bắt quá nhiều loại lỗi ngoài chủ đích | Liệt kê đúng những exception cần chung policy |
| Gộp vì hai nhánh có cùng một dòng log | Chính sách trả kết quả, retry, rollback có thể khác | So sánh hành vi đầy đủ |
| Bỏ kiểm thử sau khi refactor | Có thể làm mất nhánh cần xử lý riêng | Kiểm thử mỗi loại exception |

Trong bảng, `A` và `B` là tên kiểu tượng trưng; cần thay bằng các class exception cụ thể khi viết Java source thực tế.

## 13. Checklist khi thêm dấu `|` vào code hiện đại

1. **Loại exception:** những kiểu nào thực sự phát sinh từ các lời gọi trong khối try?
2. **Chính sách:** tất cả có cùng kết quả, retry, rollback và log/metric không?
3. **Quan hệ kiểu:** có alternative nào là cha hoặc con của alternative khác không?
4. **Checked exception:** compiler có thể chứng minh từng checked alternative có thể được ném không?
5. **Biến catch:** thân xử lý chỉ dùng những method hợp lệ với kiểu tĩnh chung chứ?
6. **Nguyên nhân:** việc wrap/rethrow có giữ cause và suppressed exceptions cần thiết không?
7. **Kiểm thử:** đã tạo trường hợp ném từng loại exception để xác nhận chính sách chung chưa?
8. **Phiên bản:** phần cú pháp `|` dùng được từ Java 7; API phụ trợ từ Java 8, 11, 17... được dùng đúng phiên bản mục tiêu chưa?

Với một thay đổi nhỏ từ hai catch riêng sang một catch có `|`, chạy compiler và test là cách kiểm tra trực tiếp nhất. Tránh “sửa cho hết lỗi compile” bằng cách bắt `Exception` rộng hoặc bỏ nguyên nhân lỗi.

## 14. Bài tập thực hành có đáp án

**Bài 1.** Phân biệt `|` trong `catch (IOException | SQLException e)` và `||` trong `if (a || b)`.  
**Đáp án:** `|` ở catch phân tách alternative *kiểu exception*; `||` là toán tử OR boolean trong biểu thức điều kiện.

**Bài 2.** Một exception thực tế là `SQLException`, được bắt bằng `catch (IOException | SQLException e)`. Runtime class của `e` là gì?  
**Đáp án:** Vẫn là `SQLException`, không phải kiểu kết hợp mới.

**Bài 3.** `catch (IOException | FileNotFoundException e)` hợp lệ không?  
**Đáp án:** Không, vì `FileNotFoundException` kế thừa `IOException`.

**Bài 4.** `catch (IOException | SQLException | ParseException e)` có hợp lệ không?  
**Đáp án:** Có thể hợp lệ nếu khối try có khả năng ném cả ba checked exceptions, các kiểu không kế thừa lẫn nhau và các nhánh phía trước không làm chúng unreachable. Về nghiệp vụ, chỉ nên gộp khi cần cùng cách xử lý.

**Bài 5.** Có thể gán lại tham số `e` của multi-catch không?  
**Đáp án:** Không; nó implicitly final.

**Bài 6.** Vì sao `catch (IOException | SQLException e)` không cho gọi thẳng `e.getSQLState()`?  
**Đáp án:** Vì compiler kiểm tra theo kiểu chung; `IOException` không có method đó. Tách nhánh SQL nếu cần logic riêng.

**Bài 7.** Chạy `PipeParseDemo` với ngày sai và số lượng sai. Hai trường hợp có đi vào cùng thân catch không?  
**Đáp án:** Có. Mỗi lần chỉ có một exception được ném, rồi một thân catch tương ứng với danh sách alternative chạy.

**Bài 8.** Chạy `CheckedAlternativesDemo` với ba `scenario`, quan sát `getClass().getSimpleName()`.  
**Đáp án:** `case 0` không có lỗi; `case 1` là `IOException`; `case 2` là `SQLException`. Multi-catch không thay loại exception.

**Bài 9.** Giả sử một nhánh cần retry, nhánh khác cần từ chối vĩnh viễn. Có nên dùng chung dấu `|` không?  
**Đáp án:** Không, vì cùng cú pháp bắt lỗi không có nghĩa cùng chính sách xử lý.

**Bài 10.** Viết hàm có `try` gọi hai method khai báo lần lượt `throws IOException` và `throws SQLException`. Bắt bằng multi-catch, in `getClass().getSimpleName()`, rồi ném lại `e` hoặc chuyển sang exception domain có cause. Kiểm tra hợp đồng `throws` và phản ứng ở caller.

## 15. Tài liệu chuẩn

- [Java Language Specification 17 — `14.20, `try` Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): cú pháp catch alternatives, luật subtype, biến exception và precise rethrow.
- [Java Language Specification 17 — `11.2, Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): checked exception và điều kiện có thể được ném.
- [Java Language Specification 17 — `4.10.4, Least Upper Bound](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.10.4): kiểu chung được dùng trong phân tích kiểu.
- [Java SE 17 — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getMessage()`, `getCause()` và `getSuppressed()`.

**Ghi nhớ:** Viết `catch (A | B e)` để **liệt kê những loại ngoại lệ độc lập có thể dùng chung một hành động**; dấu `|` không phải `||`, không tạo kiểu exception runtime mới và không cho phép alternative cha–con. Trong Java hiện đại, vẫn dùng multi-catch với kiểu cụ thể, giữ nguyên nguyên nhân lỗi và xác nhận mỗi đường xử lý bằng test.
