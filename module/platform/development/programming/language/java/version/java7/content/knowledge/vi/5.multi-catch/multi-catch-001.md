# Nhận diện các nhánh catch có cách xử lý giống nhau (Multi-catch)

> **Bài học thuộc Java 7 – Multi-catch.** Java 7 bổ sung cú pháp `catch (A | B e)` để nhiều loại ngoại lệ dùng chung một khối xử lý. Giá trị lâu dài của tính năng này trong Java hiện đại là diễn đạt rõ **khi nào các lỗi khác loại có cùng chính sách xử lý**, tránh lặp code mà vẫn giữ nguyên ngữ nghĩa, kiểu ngoại lệ và khả năng chẩn đoán. Các ví dụ dùng Java 17+ và ghi rõ API xuất hiện sau Java 7 nếu có.

## 1. Vấn đề cần giải quyết: các nhánh catch trùng hành vi

Một khối `try` có thể phát sinh nhiều loại exception. Khi xử lý từng loại, ta có thể vô tình lặp lại cùng một quyết định:

```java
try {
    // Đọc và phân tích dữ liệu đầu vào.
} catch (NumberFormatException error) {
    return "INVALID_INPUT";
} catch (DateTimeParseException error) {
    return "INVALID_INPUT";
}
```

Hai nhánh có cùng hành vi: trả về một mã lỗi dữ liệu đầu vào không hợp lệ. Nếu đây là **hợp đồng thực sự của tầng validation**, có thể gộp:

```java
try {
    // Đọc và phân tích dữ liệu đầu vào.
} catch (NumberFormatException | DateTimeParseException error) {
    return "INVALID_INPUT";
}
```

Hai khối trên là **mã minh họa trong một method trả `String`**, không phải chương trình Java độc lập. `NumberFormatException` có từ lâu; `DateTimeParseException` thuộc `java.time` (Java 8). Cú pháp `catch (A | B e)` được đưa vào từ Java 7 và vẫn sử dụng đầy đủ trong Java 17+.

**Quy tắc cốt lõi:** chỉ gộp khi cả hai ngoại lệ cần **cùng một chính sách xử lý** ở tầng hiện tại. Multi-catch không có nhiệm vụ tự suy ra rằng hai lỗi là tương đương; việc đánh giá thuộc về người thiết kế ứng dụng.

## 2. Thế nào là “xử lý giống nhau”?

Hai nhánh catch được xem là tương đương khi, đối với **cùng một tầng xử lý**, chúng có cùng quyết định và cùng các tác động quan trọng.

| Khía cạnh cần so sánh | Có thể gộp khi | Nên giữ riêng khi |
| --- | --- | --- |
| Phân loại lỗi | Cùng một nhóm lỗi tại ranh giới hiện tại | Một lỗi do người dùng, một lỗi do hạ tầng |
| Kết quả với caller | Cùng response, cùng trạng thái hoặc cùng kiểu lỗi domain | Mã HTTP, thông điệp hoặc hợp đồng trả về khác nhau |
| Phục hồi | Cùng fallback, quyết định retry và giới hạn retry | Chỉ một lỗi cần retry/backoff |
| Giao dịch | Cùng quyết định rollback/bù trừ | Một lỗi cần rollback, lỗi kia có thể tiếp tục |
| Quan sát | Cùng severity, metric, audit policy | Một loại cần cảnh báo vận hành riêng |
| Thông tin subtype | Không cần method riêng của từng exception | Phải đọc `SQLException.getSQLState()` hoặc thuộc tính riêng |
| Quan hệ kế thừa | Các alternative không là subtype của nhau | Một exception kế thừa exception kia |

**Chỉ có các dòng code giống nhau vẫn chưa đủ.** Hai nhánh cùng ghi `log.error(...)` nhưng một nhánh retry và nhánh kia trả lỗi vĩnh viễn thì không cùng chính sách. Ngược lại, hai exception khác nguồn có thể hợp nhất nếu tại ranh giới hiện tại chúng đều đại diện cho “bản ghi nhập vào không hợp lệ” và có cùng cách xử lý.

### 2.1. Quy trình review một chuỗi catch

1. Đọc toàn bộ khối `try` và xác định lời gọi nào có thể ném từng loại ngoại lệ.
2. Đọc **toàn bộ** nội dung từng nhánh `catch`: có `return`, `throw`, retry, rollback, ghi log/metric hay thay đổi trạng thái nào?
3. So sánh tác động đối với caller và hệ thống. Không chỉ so sánh văn bản dòng code.
4. Kiểm tra hệ phân cấp exception: cặp cha–con không thể cùng xuất hiện trong multi-catch.
5. Xác nhận mã trong thân catch chỉ dùng các method chung của những loại lỗi đã gộp.
6. Refactor thành `catch (A | B e)` nếu hợp lệ, rồi chạy test cho **từng đường lỗi**.

Nếu một điều kiện không đạt, giữ riêng các nhánh hoặc chỉ trích phần code chung thành helper.

## 3. Ví dụ thực tế: cùng từ chối bản ghi có dữ liệu sai

Giả sử nhận chuỗi `yyyy-MM-dd,quantity`. Một bản ghi bị từ chối khi ngày không parse được hoặc số lượng không parse được. Tại tầng validation này, hai lỗi cùng mang ý nghĩa **bản ghi không hợp lệ**, vì vậy có thể gộp.

Lưu thành `RecordValidationDemo.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;

public class RecordValidationDemo {
    static String validateRecord(String raw) {
        String[] parts = raw.split(",", -1);
        if (parts.length != 2) {
            return "REJECTED";
        }

        try {
            LocalDate day = LocalDate.parse(parts[0]);
            int quantity = Integer.parseInt(parts[1]);

            if (quantity < 0) {
                return "REJECTED";
            }
            return "ACCEPTED: " + day + " / " + quantity;
        } catch (DateTimeParseException | NumberFormatException error) {
            return "REJECTED";
        }
    }

    public static void main(String[] args) {
        System.out.println(validateRecord("2026-11-04,3"));
        System.out.println(validateRecord("not-a-date,3"));
        System.out.println(validateRecord("2026-11-04,oops"));
        System.out.println(validateRecord("2026-11-04,-2"));
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac -encoding UTF-8 --release 17 RecordValidationDemo.java
java RecordValidationDemo
```

Stdout:

```text
ACCEPTED: 2026-11-04 / 3
REJECTED
REJECTED
REJECTED
```

**Phân tích cơ chế:**

- `LocalDate.parse` ném `DateTimeParseException` khi chuỗi ngày không hợp lệ; `Integer.parseInt` ném `NumberFormatException` khi chuỗi không phải số nguyên hợp lệ.
- Đây là hai lớp ngoại lệ **không có quan hệ cha–con**, nên hợp lệ khi dùng `DateTimeParseException | NumberFormatException`.
- Cả hai cùng trả `REJECTED`. Đây là chính sách cụ thể của ví dụ, không phải quy tắc rằng mọi lỗi parse đều luôn phải gộp.
- Số lượng âm được kiểm tra trực tiếp, không cần ném ngoại lệ để mô tả một điều kiện nghiệp vụ dự đoán được.
- `raw.split` nằm ngoài khối `try`; truyền `null` vẫn ném `NullPointerException`. Việc không bắt lỗi lập trình đó trong multi-catch là có chủ đích.
- `LocalDate`/`DateTimeParseException` là API Java 8, còn cách khai báo multi-catch xuất hiện từ Java 7. Sự kết hợp này vẫn là cách viết phù hợp trong dự án hiện đại.

Nếu ứng dụng cần trả lỗi **theo từng trường** như `INVALID_DATE` và `INVALID_QUANTITY`, chính sách đã khác; lúc đó nên bắt riêng hoặc biểu diễn thông tin lỗi chi tiết hơn.

## 4. Ví dụ ngược lại: hai catch không thể gộp về mặt nghiệp vụ

Một thao tác đọc port từ file cấu hình có hai nhóm lỗi:

- `NumberFormatException`: đọc được dữ liệu, nhưng nội dung không biểu diễn được số nguyên → cấu hình sai.
- `IOException`: file không đọc được → filesystem hoặc quyền truy cập có vấn đề.

Hai tình huống đòi hỏi hành động khác nhau. Nếu gộp thành một trạng thái lỗi chung, caller mất khả năng phân biệt **sửa dữ liệu cấu hình** với **khắc phục môi trường**.

Lưu thành `ConfigPolicyDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ConfigPolicyDemo {
    static String readPort(Path file) {
        try {
            String text = Files.readString(file, StandardCharsets.UTF_8);
            int port = Integer.parseInt(text.trim());

            if (port < 1 || port > 65535) {
                return "INVALID_CONFIG";
            }
            return "PORT=" + port;
        } catch (NumberFormatException error) {
            return "INVALID_CONFIG";
        } catch (IOException error) {
            return "UNAVAILABLE";
        }
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("port-config-", ".txt");
        try {
            Files.writeString(file, "8080", StandardCharsets.UTF_8);
            System.out.println(readPort(file));

            Files.writeString(file, "not-a-number", StandardCharsets.UTF_8);
            System.out.println(readPort(file));
        } finally {
            Files.deleteIfExists(file);
        }
        System.out.println(readPort(file));
    }
}
```

```bash
javac -encoding UTF-8 --release 17 ConfigPolicyDemo.java
java ConfigPolicyDemo
```

```text
PORT=8080
INVALID_CONFIG
UNAVAILABLE
```

`Files.readString` và `Files.writeString` có từ **Java 11**, dựa trên nền `Path`/`Files` của Java 7. Trong ví dụ, file tạm được xóa ở `finally`, rồi lần đọc cuối đi qua nhánh `IOException`. Dòng in không phụ thuộc tên file tạm.

Cặp `NumberFormatException | IOException` **hợp lệ về cú pháp**, nhưng không nên dùng multi-catch ở đây vì kết quả khác nhau. Nếu một tác vụ thử nghiệm thật sự cho phép bỏ qua cả file không có lẫn dữ liệu sai, đó là **chính sách mới cần được xác nhận**, không thể suy ra chỉ từ danh sách ngoại lệ.

## 5. Luật cú pháp của multi-catch trong Java 7+

Cú pháp:

```java
try {
    // Những thao tác có thể ném nhiều loại exception.
} catch (FirstException | SecondException error) {
    // Cùng một chính sách xử lý cho mọi alternative.
}
```

Trong khai báo catch dùng **`|`**, không dùng `||`. Có thể khai báo hơn hai alternative, miễn là hợp lệ và các kiểu exception **không kế thừa lẫn nhau**.

### 5.1. Hai kiểu ngang hàng: hợp lệ về cú pháp

```java
try {
    executeImport();
} catch (IOException | SQLException error) {
    reportImportFailure(error);
}
```

Đây là **snippet minh họa**, giả định `executeImport` có thể ném hai loại checked exception và `reportImportFailure` đã được định nghĩa. Cần import `java.io.IOException` và `java.sql.SQLException`. Hai kiểu này không có quan hệ subtype. Tuy nhiên, chúng chỉ nên gộp khi cả lỗi file và lỗi SQL được xử lý giống nhau tại ranh giới nhập dữ liệu.

### 5.2. Hai kiểu cha–con: không hợp lệ

Ví dụ **cố ý không biên dịch**:

```java
// FileNotFoundException là subtype của IOException:
catch (FileNotFoundException | IOException error) {
    // ERROR: alternative kế thừa lẫn nhau.
}

// NumberFormatException là subtype của IllegalArgumentException:
catch (NumberFormatException | IllegalArgumentException error) {
    // ERROR: alternative kế thừa lẫn nhau.
}
```

Nếu toàn bộ `IOException` có cùng chính sách, một catch kiểu cha đủ dùng:

```java
catch (IOException error) {
    // Bắt IOException và các subtype, gồm FileNotFoundException.
}
```

Nếu `FileNotFoundException` cần phản ứng riêng, đặt nhánh cụ thể trước nhánh tổng quát:

```java
catch (FileNotFoundException error) {
    // Phân loại thiếu file.
} catch (IOException error) {
    // Các lỗi I/O khác.
}
```

Đây là các đoạn catch minh họa cần đặt sau khối `try` phù hợp. Đặt `catch (IOException)` trước `catch (FileNotFoundException)` khiến nhánh con phía sau không thể tới và là lỗi biên dịch.

**Kết luận của bước này:** cần phân biệt **tương đương về chính sách** với **quan hệ kế thừa**. Khi hai subtype có cùng cha và cùng chính sách cho mọi subtype thuộc nhóm đó, catch kiểu cha có thể hợp lý. Nếu chỉ muốn bắt một vài subtype, có thể dùng multi-catch giữa các subtype **không có quan hệ cha–con** để tránh bắt những lỗi ngoài dự kiến.

## 6. Biến exception trong multi-catch và giới hạn truy cập method

Với `catch (IOException | SQLException error)`, compiler suy luận một **kiểu chung** cho biến `error`. Mã xử lý bên trong có thể gọi các method có trên kiểu chung, ví dụ `getMessage()`, `getCause()`, `getSuppressed()` của `Throwable`.

Không thể mặc định gọi `error.getSQLState()` vì method đó thuộc `SQLException`, không thuộc `IOException`. Nếu SQL state quyết định retry hoặc mapping lỗi, nên giữ catch riêng để truy cập subtype phù hợp.

**Biến multi-catch là implicitly final:** không được gán lại:

```java
catch (IOException | SQLException error) {
    error = new IOException("replacement"); // ERROR: không thể gán lại
}
```

Đây là lỗi compile-time có chủ đích, không phải đoạn code để chạy. Nếu muốn tạo lỗi ở tầng nghiệp vụ, hãy ném exception mới và **giữ nguyên cause**:

```java
catch (IOException | SQLException error) {
    throw new ImportFailureException("Import không thành công", error);
}
```

Đoạn thứ hai là snippet, giả định ứng dụng có `ImportFailureException(String, Throwable)`. Nếu cùng một lỗi domain được sử dụng cho hai nguyên nhân này theo hợp đồng caller, dùng multi-catch giúp tránh lặp translation. Khi debug, `getCause()` của exception mới vẫn dẫn đến loại lỗi gốc.

## 7. Các nhánh có đoạn code chung nhưng hành vi khác nhau

Không phải mọi đoạn lặp đều nên xóa bằng multi-catch.

**Ví dụ A: cùng log nhưng khác kết quả.**

```java
catch (NumberFormatException error) {
    logFailure(error);
    return BAD_REQUEST;
} catch (IOException error) {
    logFailure(error);
    return SERVICE_UNAVAILABLE;
}
```

Đây là snippet với helper/hằng trạng thái do ứng dụng định nghĩa. Dù cùng gọi `logFailure`, một lỗi phải trả bad request, lỗi còn lại báo service unavailable. Nên giữ riêng catch; việc gọi một helper chung đã giải quyết sự lặp lại của log.

**Ví dụ B: cùng trạng thái nhưng khác side effect.**

```java
catch (SocketTimeoutException error) {
    scheduleRetry(error);
    return TEMPORARY_FAILURE;
} catch (AccessDeniedException error) {
    alertOperator(error);
    return TEMPORARY_FAILURE;
}
```

Đây là snippet có helper/hằng giả định. Nhánh timeout cần retry; nhánh thiếu quyền cần cảnh báo vận hành. Trả cùng một trạng thái chưa đủ để coi hai hành vi là giống nhau. `SocketTimeoutException` và `AccessDeniedException` đều kế thừa `IOException` nhưng không kế thừa lẫn nhau; có thể gộp về cú pháp, song làm vậy sẽ mất sự khác biệt quan trọng.

**Ví dụ C: cùng kết quả, cùng side effect.**

```java
catch (NumberFormatException error) {
    rejectedCount++;
    return false;
} catch (DateTimeParseException error) {
    rejectedCount++;
    return false;
}
```

Nếu cả hai thực sự cùng nghĩa “bản ghi bị từ chối”, có thể thay bằng:

```java
catch (NumberFormatException | DateTimeParseException error) {
    rejectedCount++;
    return false;
}
```

Hai đoạn ở ví dụ C là snippet trong method trả boolean, với biến `rejectedCount` đã được khai báo. Sau refactor, việc tăng bộ đếm đúng **một lần** cho mỗi lỗi không thay đổi. Nếu biến được chia sẻ giữa nhiều thread, cần xử lý an toàn luồng riêng; multi-catch không tự bảo đảm atomicity.

## 8. Khi nào nên tách phạm vi try thay vì gộp catch?

Một method đôi khi thực hiện nhiều giai đoạn: parse input, mở file, gọi database. Nếu bao quanh tất cả bằng một khối `try` rất lớn rồi `catch (Exception e)`, tầng xử lý có thể nhầm lỗi do code nội bộ với lỗi đầu vào người dùng.

Một giải pháp là đặt ranh giới xử lý theo trách nhiệm:

```java
int quantity;
try {
    quantity = Integer.parseInt(rawQuantity);
} catch (NumberFormatException error) {
    throw new IllegalArgumentException("Số lượng không hợp lệ", error);
}

// Chỉ sau khi parse thành công mới đi đến thao tác file/database.
```

Snippet này nằm trong method có biến `rawQuantity` và các lệnh I/O tiếp theo. Nó tách lỗi parse dữ liệu người dùng khỏi các lỗi hạ tầng có chính sách khác.

Nếu một khối `try` mở tài nguyên (file stream, JDBC connection, reader...), hãy dùng `try-with-resources` khi phù hợp để đóng chúng. Multi-catch quyết định **xử lý loại ngoại lệ nào**, còn try-with-resources giải quyết **vòng đời tài nguyên**. Hai cơ chế đều có từ Java 7 và tiếp tục được dùng trong Java hiện đại.

Không nên gộp các nhánh vào `catch (Exception error)` chỉ để làm code ngắn. Một catch quá rộng có thể che lỗi lập trình như `NullPointerException` hoặc phân loại sai lỗi hạ tầng thành lỗi dữ liệu.

## 9. Xử lý exception gốc và việc truyền lỗi

Có ba chiến lược phổ biến, nhưng chỉ gộp khi cùng chiến lược áp dụng cho mọi alternative:

1. **Fallback có nghĩa:** trả giá trị thay thế khi cả hai tình huống đều được phép sử dụng fallback đó.
2. **Error result:** trả mã/đối tượng thất bại theo hợp đồng, ví dụ `REJECTED` hoặc `INVALID_INPUT`.
3. **Exception translation:** ném exception domain mới nhưng giữ `cause` để truy vết.

Ví dụ translation trước khi gộp:

```java
catch (IOException error) {
    throw new ImportException("Không nhập được dữ liệu", error);
} catch (SQLException error) {
    throw new ImportException("Không nhập được dữ liệu", error);
}
```

Nếu mọi loại lỗi trên đều cần cùng một `ImportException`:

```java
catch (IOException | SQLException error) {
    throw new ImportException("Không nhập được dữ liệu", error);
}
```

Đây là minh họa hai phiên bản thay thế của chuỗi catch; `ImportException` là lớp ứng dụng cần định nghĩa riêng. **Không bỏ `error` khỏi constructor** nếu cần truy tìm nguyên nhân ban đầu.

Java 7 còn có cải tiến *precise rethrow* giúp compiler suy luận tập checked exceptions hợp lý khi bắt rồi ném lại chính biến exception không bị gán lại. Tuy vậy, điều đó không thay thế việc quyết định chính sách: caller vẫn phải hiểu những lỗi nào có thể được truyền lên.

### 9.1. Logging và metric

Khi gộp hai nhánh, mức log và thông điệp cho người dùng có thể giống nhau, nhưng vẫn nên giữ thông tin loại exception thực tế cho việc điều tra. Không nên ghi nguyên message từ dữ liệu đầu vào không tin cậy vào các kênh công khai; log/audit theo chuẩn bảo vệ dữ liệu của hệ thống.

Nếu hai lỗi cần **mức độ nghiêm trọng hoặc nhãn metric khác nhau**, có thể giữ riêng catch rồi gọi helper chung. Đừng thay mọi lỗi thành một chuỗi `"error"` vì điều đó làm mất khả năng phân tích vận hành.

## 10. Kiểm thử refactor multi-catch

Refactor chỉ hoàn tất khi đã kiểm tra từng đường lỗi, thay vì chỉ chạy happy path:

- Cố ý tạo **ngoại lệ A** và xác nhận response, exception trả lên, retry, rollback, side effects.
- Cố ý tạo **ngoại lệ B** và xác nhận cùng các thuộc tính.
- Xác nhận exception không nằm trong danh sách bắt **không bị nuốt nhầm**.
- Xác nhận việc giữ cause và đóng tài nguyên đúng như trước.
- Với refactor từ hai catch riêng sang một catch chung, so sánh hành vi quan sát được trước/sau ở caller.

Hai chương trình ở trên tạo bài test đối chiếu cụ thể: `RecordValidationDemo` chứng minh cả lỗi ngày và số đều `REJECTED`; `ConfigPolicyDemo` chứng minh lỗi nội dung và lỗi filesystem phải đi theo hai kết quả khác nhau.

Không nhất thiết kiểm thử bằng cách so từng dòng log. Hãy kiểm tra những gì hợp đồng công bố: loại lỗi/domain status, dữ liệu trả về, quyết định retry và side effect thiết yếu.

## 11. Các lỗi phổ biến

| Lỗi thường gặp | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Gộp chỉ vì hai nhánh cùng log | Mất khác biệt về retry/status/rollback | So sánh chính sách đầy đủ |
| Dùng `catch (Exception e)` để thay mọi catch | Bắt lỗi ngoài trách nhiệm của tầng hiện tại | Bắt đúng các loại lỗi đã biết cách xử lý |
| Viết `IOException \| FileNotFoundException` | Lỗi compile do quan hệ cha–con | Dùng kiểu cha nếu cùng policy; tách catch con trước nếu khác |
| Đặt catch kiểu cha trước kiểu con | Nhánh kiểu con không thể đến | Đặt specific catch trước |
| Gọi method riêng subtype trên biến multi-catch | Không bảo đảm method tồn tại | Tách nhánh khi cần xử lý đặc thù |
| Gán lại biến `error` | Biến multi-catch implicitly final | Tạo exception mới khi cần translation |
| Chỉ test trường hợp thành công | Không phát hiện thay đổi đường lỗi | Test từng loại exception được gộp |
| Nuốt mọi ngoại lệ rồi trả thành công | Che lỗi và phá hợp đồng | Trả lỗi rõ ràng hoặc truyền exception |
| Quên giữ exception gốc | Khó chẩn đoán nguyên nhân | Giữ `cause` khi wrap |
| Nhầm dấu `|` với `||` | Không đúng cú pháp khai báo catch | Dùng `catch (A \| B e)` |

## 12. Bài tập thực hành có đáp án

**Bài 1.** Có nên gộp hai nhánh này không?

```java
catch (NumberFormatException error) {
    return "INVALID";
} catch (DateTimeParseException error) {
    return "INVALID";
}
```

**Đáp án:** Có, nếu cả hai là lỗi dữ liệu cùng một hợp đồng validation. Dùng `catch (NumberFormatException | DateTimeParseException error)` rồi `return "INVALID";`.

**Bài 2.** Hai catch đều gọi `logFailure(error)` nhưng lần lượt trả `BAD_REQUEST` và `SERVICE_UNAVAILABLE`.  
**Đáp án:** Giữ hai nhánh vì khác hành vi với caller; helper log đã có thể dùng chung.

**Bài 3.** Có thể dùng `catch (IOException | FileNotFoundException e)` không?  
**Đáp án:** Không. `FileNotFoundException` kế thừa `IOException`. Dùng catch kiểu cha nếu mọi IOException cùng policy.

**Bài 4.** Khi cần đọc `SQLException.getSQLState()` cho riêng lỗi SQL, nên gộp với `IOException` không?  
**Đáp án:** Thường không. Nên xử lý `SQLException` riêng để truy cập thuộc tính và quyết định retry/mapping đúng.

**Bài 5.** Có thể gán lại `error` bên trong `catch (IOException | SQLException error)` không?  
**Đáp án:** Không. Tham số multi-catch implicitly final. Khi cần exception domain mới, khởi tạo đối tượng khác và truyền `error` làm cause.

**Bài 6.** Hai nhánh trả cùng `FAILED`, nhưng một nhánh lên lịch retry còn nhánh kia gửi cảnh báo.  
**Đáp án:** Không nên gộp, vì side effect và mục đích phục hồi khác nhau.

**Bài 7 – Thực hành.** Viết hàm nhận `yyyy-MM-dd,quantity`, gộp hai lỗi parse thành `REJECTED`, kiểm thử ngày sai và số sai. Sau đó đổi yêu cầu thành trả `INVALID_DATE` hoặc `INVALID_QUANTITY` để xác định khi nào phải tách catch.

**Bài 8 – Thực hành.** Viết hàm đọc file cấu hình và parse port. Thiết kế hai chính sách: (a) công cụ import thử cho phép bỏ qua cả lỗi đọc lẫn lỗi format; (b) server production phân biệt “cấu hình hỏng” với “không đọc được file”. Giải thích lý do gộp hoặc tách.

**Bài 9 – Thực hành.** Đặt `catch (FileNotFoundException)` và `catch (IOException)` đúng thứ tự, rồi thử đảo thứ tự để đọc lỗi compiler. Giải thích dựa trên quan hệ kế thừa.

## 13. Tài liệu chuẩn

- [Java Language Specification 17 — `14.20, The `try` Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): quy tắc bắt ngoại lệ, nhiều alternative và biến exception.
- [Java Language Specification 17 — `11, Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): checked exceptions và các quy tắc xử lý/lan truyền lỗi.
- [Oracle Java Tutorials — Catching and Handling Exceptions](https://docs.oracle.com/javase/tutorial/essential/exceptions/catch.html): tổng quan catch và multi-catch.

**Ghi nhớ:** Hãy gộp `catch` khi nhiều loại exception thực sự cần **cùng kết quả, cùng cách phục hồi và cùng tác động** tại tầng đang xét. Khi chính sách khác nhau, giữ nhánh riêng; khi kiểu có quan hệ cha–con, tuân thủ luật catch theo thứ tự và kiểu cha. Java 7 đã cung cấp công cụ này, và những nguyên tắc đó vẫn hoàn toàn áp dụng cho Java hiện đại.
