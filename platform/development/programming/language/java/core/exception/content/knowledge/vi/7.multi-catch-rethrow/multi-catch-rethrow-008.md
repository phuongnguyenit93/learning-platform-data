# So sánh multi-catch với `catch` kiểu cha quá rộng — Java Core Exception

> **Bối cảnh:** Java Core → Multi-catch và rethrow. Khi nhiều loại ngoại lệ cần cùng một hành động xử lý, `catch (IOException | SQLException e)` thường thể hiện ý định rõ hơn `catch (Exception e)`. Hai cách có thể bắt cùng những lỗi được dự kiến, nhưng **phạm vi bắt và hệ quả đối với lỗi không dự kiến rất khác nhau**. Bài này tập trung vào cách chọn handler, quy tắc biên dịch, biến multi-catch, ném lại ngoại lệ và cách quyết định handler nào là hợp lý.

## 1. Câu trả lời nhanh

Xét một lời gọi có thể phát sinh hai loại checked exception:

```java
// Minh họa trong method; performOperation() có thể ném
// IOException hoặc SQLException.
try {
    performOperation();
} catch (java.io.IOException | java.sql.SQLException e) {
    reportFailure(e);
}
```

So với:

```java
try {
    performOperation();
} catch (Exception e) {
    reportFailure(e);
}
```

Hai đoạn đều là **minh họa**, vì `performOperation()` và `reportFailure(e)` chưa được định nghĩa. Khác biệt quan trọng:

- **Multi-catch:** chỉ bắt `IOException`, `SQLException` **và các lớp con của chúng**. Một lỗi lập trình như `NullPointerException` hoặc `IllegalStateException` sẽ không bị handler này nuốt và có thể lan ra tầng cao hơn.
- **`catch (Exception)`:** cũng bắt `IOException` và `SQLException`, nhưng còn bắt **mọi lớp con của `Exception`**, bao gồm phần lớn unchecked exceptions như `NullPointerException`, `NumberFormatException` và `IllegalStateException`.
- **Cả hai đều không mặc nhiên bắt `Error`.** `Error` là nhánh khác của `Throwable`; nếu viết `catch (Throwable)` thì phạm vi còn rộng hơn, thường không phù hợp cho ứng dụng thông thường.
- **Độ rõ ràng của hợp đồng:** multi-catch nói chính xác những nhóm thất bại mà handler dự định xử lý giống nhau. `catch (Exception)` không cho người đọc biết nhóm lỗi nào đã được cân nhắc.
- **Về checked exception:** Java có quy tắc **precise rethrow**; không nên nói rằng `catch (Exception)` *luôn* buộc phải khai báo `throws Exception` khi ném lại. Phần sau có ví dụ để phân biệt chính xác.

### 1.1. Bảng so sánh

| Tiêu chí | `catch (IOException \| SQLException e)` | `catch (Exception e)` |
| --- | --- | --- |
| Phạm vi theo kiểu | Hai nhánh được nêu và các subtype | Toàn bộ nhánh `Exception` |
| Bắt lỗi I/O được dự kiến | Có | Có |
| Bắt lỗi SQL được dự kiến | Có | Có |
| Bắt `NullPointerException` | Không | **Có** |
| Bắt `IllegalStateException` | Không | **Có** |
| Bắt `AssertionError` | Không | Không |
| Nói rõ ý định xử lý | Có | Ít rõ hơn |
| Có thể nuốt lỗi lập trình không dự kiến | Ít hơn; những lỗi ngoài tập khai báo lan tiếp | **Có**, nếu handler xử lý chung/nuốt lỗi |
| Biến `e` được gán lại? | **Không**; implicitly final | Có thể gán lại về mặt cú pháp, nhưng làm mất một số ưu điểm phân tích chính xác khi rethrow |
| Có thể ném lại? | Có | Có; xem precise rethrow |
| Khi nào nên dùng? | Những exception cụ thể cần cùng logic | Ranh giới ứng dụng có chính sách xử lý tổng quát thật sự |

**Kết luận thiết kế:** lựa chọn handler nên bắt đầu từ “tầng này thực sự biết xử lý loại lỗi nào?”, không phải “viết cái nào ít ký tự hơn?”.

## 2. Vì sao multi-catch là một lựa chọn có chủ đích?

Trước Java 7, nếu hai loại exception cần cùng logic, người viết thường lặp:

```java
try {
    work();
} catch (java.io.IOException e) {
    log(e);
    markFailed();
} catch (java.sql.SQLException e) {
    log(e);
    markFailed();
}
```

Đây là đoạn minh họa; các method chưa được định nghĩa. Logic `log` và `markFailed` bị lặp. Từ Java 7, có thể dùng multi-catch:

```java
try {
    work();
} catch (java.io.IOException | java.sql.SQLException e) {
    log(e);
    markFailed();
}
```

Lợi ích là **gom phần xử lý giống nhau mà không mở rộng nhóm ngoại lệ**. Về ý nghĩa, multi-catch là một cách biểu diễn ngắn cho cùng một hành động xử lý áp dụng cho **nhiều kiểu độc lập**, thay vì giả định mọi `Exception` đều có thể xử lý như nhau.

Không nên thay hai `catch` cụ thể bằng một `catch (Exception)` chỉ để tránh lặp code. Một handler tổng quát sẽ thay đổi tập lỗi bị giữ lại, không chỉ thay đổi cách trình bày.

### 2.1. Multi-catch không phải cơ chế bắt “tất cả các exception”

Cú pháp:

```java
catch (TypeA | TypeB | TypeC e) {
    // Cùng một hành động xử lý cho từng loại.
}
```

`TypeA`, `TypeB`, `TypeC` phải là các kiểu exception hợp lệ thuộc hệ `Throwable` và thỏa điều kiện ngôn ngữ về các lựa chọn trong multi-catch. Dấu ngăn cách là một dấu **`|`**, không phải `||`. Đây không phải cú pháp kiểm tra boolean trong `if`.

Khi ngoại lệ được ném, Java chọn multi-catch nếu đối tượng runtime tương thích với **ít nhất một** kiểu được liệt kê. Handler chạy **một lần**, không chạy lần lượt theo số lượng lựa chọn.

### 2.2. Phạm vi bắt được xác định bằng quan hệ kế thừa

```text
Throwable
├── Error
│   └── AssertionError
└── Exception
    ├── IOException
    │   ├── FileNotFoundException
    │   └── EOFException
    ├── SQLException
    └── RuntimeException
        ├── IllegalStateException
        ├── NullPointerException
        └── IllegalArgumentException
            └── NumberFormatException
```

Cây này chỉ có các lớp tiêu biểu.

Với `catch (IOException | SQLException e)`:

- `new FileNotFoundException(...)` được bắt vì là subtype của `IOException`.
- `new SQLException(...)` được bắt trực tiếp.
- `new NumberFormatException(...)` **không** được bắt vì nằm dưới `RuntimeException`, ngoài hai nhánh đã chọn.
- `new AssertionError(...)` cũng không được bắt.

Với `catch (Exception e)`, ba trường hợp đầu đều được bắt (vì `IOException`, `SQLException` và `RuntimeException` đều là subtype của `Exception`). `AssertionError` vẫn không được bắt.

## 3. Chương trình Java 17: khác biệt nhìn thấy được khi lỗi lập trình xuất hiện

Để so sánh công bằng, hai phương thức sau gọi **cùng một** hoạt động. Handler multi-catch chỉ nhận hai loại lỗi hạ tầng đã dự kiến; handler tổng quát bắt cả lỗi trạng thái nằm ngoài kế hoạch xử lý.

Tạo tệp `CatchScopeDemo.java`:

```java
import java.io.IOException;
import java.sql.SQLException;

public class CatchScopeDemo {
    static void execute(String mode) throws IOException, SQLException {
        switch (mode) {
            case "io" -> throw new IOException("Nguồn đọc lỗi");
            case "db" -> throw new SQLException("Truy vấn lỗi");
            case "bug" -> throw new IllegalStateException("Trạng thái sai");
            default -> System.out.println("Thao tác thành công");
        }
    }

    static void targeted(String mode) {
        try {
            execute(mode);
        } catch (IOException | SQLException e) {
            System.out.println("multi: "
                    + e.getClass().getSimpleName());
        }
    }

    static void broad(String mode) {
        try {
            execute(mode);
        } catch (Exception e) {
            System.out.println("broad: "
                    + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        targeted("io");
        targeted("db");

        try {
            targeted("bug");
        } catch (IllegalStateException e) {
            System.out.println("caller: "
                    + e.getClass().getSimpleName());
        }

        broad("bug");
        targeted("ok");
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac -encoding UTF-8 CatchScopeDemo.java
java CatchScopeDemo
```

Stdout:

```text
multi: IOException
multi: SQLException
caller: IllegalStateException
broad: IllegalStateException
Thao tác thành công
```

Giải thích:

1. `targeted("io")` ném `IOException`, multi-catch nhận và in `multi: IOException`.
2. `targeted("db")` ném `SQLException`, handler đó cũng nhận vì đã nêu rõ lựa chọn thứ hai.
3. `targeted("bug")` ném unchecked `IllegalStateException`. Nó **không** thuộc `IOException` hoặc `SQLException` nên lan ra `main`, nơi có handler riêng.
4. `broad("bug")` bắt cùng lỗi đó bằng `catch (Exception)`. Ở ví dụ này ta cố ý in ra để quan sát; trong hệ thống thật, nếu handler chung đánh dấu “đã xử lý xong”, lỗi lập trình có thể bị che.
5. `targeted("ok")` kết thúc bình thường và in `Thao tác thành công`.

**Đây là khác biệt quan trọng nhất:** khi danh sách lỗi cần xử lý đã biết, multi-catch thường bảo vệ việc phân biệt “lỗi đã có phương án xử lý” với “lỗi không dự kiến cần được đẩy lên”. Nó không tự động khôi phục hệ thống, nhưng tránh thu gom vô tình các nhánh không thuộc hợp đồng.

### 3.1. Phân biệt lỗi không dự kiến với lỗi luôn phải dừng

Không được suy ra rằng mọi `RuntimeException` đều là bug và không bao giờ cần xử lý. `NumberFormatException` từ dữ liệu nhập người dùng có thể được bắt ở tầng UI để yêu cầu nhập lại; `IllegalArgumentException` trong code nghiệp vụ có thể biểu thị vi phạm hợp đồng caller. Vấn đề của `catch (Exception)` là nó **không phân loại**: bắt cả những tình huống cần khôi phục và những bug mà tầng hiện tại không biết cách xử lý.

Ngược lại, cũng không khẳng định mọi checked `IOException` hoặc `SQLException` đều phục hồi được. Bắt một exception đúng kiểu chưa chứng minh trạng thái dữ liệu còn hợp lệ, giao dịch đã rollback hay thao tác có thể thử lại an toàn.

## 4. Những ràng buộc compile-time của multi-catch

Một union như `catch (IOException | SQLException ex)` cần các alternative không có quan hệ subtype và những checked exception hợp lệ với các đường ném của `try`. Hai phản ví dụ:

```java
// Sai: FileNotFoundException là subtype của IOException.
catch (IOException | java.io.FileNotFoundException ex) {
    reportFailure(ex);
}
```

```java
// Sai: parseInt không phát sinh checked IOException.
try {
    Integer.parseInt("abc");
} catch (java.io.IOException | NumberFormatException ex) {
    reportFailure(ex);
}
```

Hai đoạn chỉ minh họa lỗi biên dịch, không phải chương trình độc lập. Với `parseInt`, bắt riêng `NumberFormatException`; với cặp cha–con, dùng `catch (IOException ex)` hoặc tách các handler theo thứ tự con trước cha. Những giới hạn cú pháp này đáng kiểm tra, nhưng lựa chọn **multi-catch hay `catch (Exception)`** còn quan trọng hơn: handler chung có được phép **tiêu thụ lỗi ngoài phạm vi dự kiến** hay không?

## 5. Biến `e` trong multi-catch có đặc điểm gì?

`catch (IOException | SQLException e)` khai báo **một** biến tham chiếu ngoại lệ, ngầm `final`. Kiểu tĩnh của `e` được suy luận theo **least upper bound** của các alternative: có thể dùng `getMessage()`, `getCause()`, `printStackTrace()` chung, nhưng không thể gọi trực tiếp `SQLException.getSQLState()` mà không thu hẹp kiểu.

```java
catch (java.io.IOException | java.sql.SQLException e) {
    System.out.println(e.getClass().getSimpleName());
    if (e instanceof java.sql.SQLException sql) {
        System.out.println(sql.getSQLState());
    }
}
```

Đây là nhánh minh họa trong `try` hợp lệ. Trong một handler rộng như `catch (Exception e)`, kiểu tĩnh chỉ là `Exception`, nhưng đối tượng runtime cũng không bị đổi loại. **Khác biệt quyết định giữa hai handler nằm ở tập lỗi bị bắt**, không phải việc dùng được `getMessage()` hay không.

## 6. Multi-catch và rethrow: chỉ khai báo các checked exception phù hợp

Multi-catch vẫn có thể **ném lại đúng đối tượng** đang bắt:

```java
static void forward() throws java.io.IOException, java.sql.SQLException {
    try {
        fetch();
    } catch (java.io.IOException | java.sql.SQLException e) {
        throw e;
    }
}
```

Đây là phương thức minh họa, yêu cầu `fetch()` được định nghĩa và có thể ném hai loại checked exception. Nếu caller cần phân biệt `IOException` và `SQLException`, `throw e` giữ nguyên loại runtime. Nhưng ưu điểm trung tâm của handler hẹp trong bài này là **không bắt nhầm lỗi lập trình `IllegalStateException`**; lỗi đó tiếp tục đi tới ranh giới giám sát, thay vì bị handler rộng coi như một thất bại hạ tầng đã phục hồi.

## 7. Điểm tinh tế: `catch (Exception)` cũng có thể precise rethrow

**Không đúng** nếu khẳng định `catch (Exception e) { throw e; }` luôn bắt buộc `throws Exception`. Java 7+ có **precise rethrow**: nếu `e` là tham số `catch` *effectively final* và compiler xác định `try` chỉ có thể ném `IOException`, `SQLException` trong nhóm checked exception đang xét, thì hai loại đó có thể đủ cho chữ ký:

```java
static void withBroadCatch()
        throws java.io.IOException, java.sql.SQLException {
    try {
        fetch();
    } catch (Exception e) {
        throw e;
    }
}
```

Đây là minh họa với `fetch()` được khai báo `throws IOException, SQLException`. **Kiểu được phép khai báo trong `throws`** và **tập exception bị handler bắt tại runtime** là hai khía cạnh khác nhau. Multi-catch chỉ bắt những nhánh được chỉ danh; `catch (Exception)` còn bắt nhiều `RuntimeException` chưa dự kiến. Nếu gán lại `e` trong single-catch, khả năng precise rethrow có thể mất. Vì vậy hãy chọn handler theo **trách nhiệm phục hồi**, không theo giả định sai rằng `catch (Exception)` luôn khiến chữ ký rộng hơn.

## 8. Khi nào dùng các `catch` riêng thay vì multi-catch?

Multi-catch chỉ nên gộp các loại exception khi **cùng chiến lược xử lý** thực sự phù hợp. Nếu phương án khắc phục khác nhau, tách handler rõ ràng hơn:

- `IOException`: có thể chọn nguồn dữ liệu khác hoặc báo file không đọc được.
- `SQLException`: có thể ghi nhận lỗi truy cập database, đánh dấu tác vụ cần kiểm tra giao dịch, quyết định dừng.
- `NumberFormatException`: có thể yêu cầu người dùng sửa chuỗi nhập.

Một multi-catch rồi phân nhánh bằng nhiều `instanceof` có thể trở thành phiên bản vòng vo của các handler riêng.

### 8.1. Chương trình Java 17: hai cách phục hồi khác nhau

Tạo `SeparateCatchPoliciesDemo.java`:

```java
import java.io.IOException;
import java.sql.SQLException;

public class SeparateCatchPoliciesDemo {
    static String load(String source) throws IOException, SQLException {
        if ("file".equals(source)) {
            throw new IOException("Tệp tạm không đọc được");
        }
        if ("db".equals(source)) {
            throw new SQLException("Database không sẵn sàng");
        }
        return "Dữ liệu mới";
    }

    static void run(String source) {
        try {
            System.out.println("Kết quả: " + load(source));
        } catch (IOException e) {
            System.out.println("I/O: dùng bản sao lưu");
        } catch (SQLException e) {
            System.out.println("DB: dừng yêu cầu");
        }
    }

    public static void main(String[] args) {
        run("file");
        run("db");
        run("memory");
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 SeparateCatchPoliciesDemo.java
java SeparateCatchPoliciesDemo
```

Stdout:

```text
I/O: dùng bản sao lưu
DB: dừng yêu cầu
Kết quả: Dữ liệu mới
```

Ở đây mỗi exception cần **một hành động khác nhau**. Ép cả hai vào multi-catch rồi kiểm tra `instanceof` trong handler sẽ làm mã dài và khó theo dõi hơn. `catch (Exception)` còn ít phù hợp hơn vì nó cũng nhận các lỗi ngoài hai nhóm này.

**Lưu ý:** thông điệp “dùng bản sao lưu” chỉ mô phỏng quyết định; ví dụ không chứa triển khai backup thật. Trong chương trình thực tế phải bảo đảm fallback thực sự có dữ liệu và phù hợp tính nhất quán của hệ thống.

## 9. Khi nào `catch (Exception)` lại là lựa chọn hợp lý?

Không nên tuyệt đối hóa quy tắc “luôn dùng multi-catch, không bao giờ catch Exception”. Có những **ranh giới cấp cao** mà mục đích chính là ngăn thất bại của một tác vụ làm hỏng luồng điều phối những tác vụ khác. Ví dụ:

- một worker xử lý job, mỗi job có phạm vi trạng thái độc lập và được đánh dấu `FAILED` nếu exception thoát ra;
- một CLI command cần chuyển exception không dự kiến thành thông báo lỗi tổng quát và exit code khác 0;
- một request boundary có cơ chế log và chuyển lỗi thành phản hồi lỗi thích hợp, đồng thời không xem request thất bại là thành công;
- một bộ giám sát cần thu thập chẩn đoán cho mọi `Exception` thoát khỏi một thao tác.

Với các trường hợp ấy, `catch (Exception)` có thể phù hợp **nếu có chính sách rõ ràng**: ghi nhận/đánh dấu failure, dọn tài nguyên, không dùng tiếp trạng thái không đáng tin, có giám sát và không nuốt lỗi.

### 9.1. Ví dụ Java 17: bắt rộng đúng tại boundary và báo thất bại

Lưu `BoundaryCatchDemo.java`:

```java
import java.io.IOException;

public class BoundaryCatchDemo {
    static void execute(String kind) throws IOException {
        switch (kind) {
            case "io" -> throw new IOException("Không thể đọc");
            case "bug" -> throw new IllegalStateException("Sai trạng thái");
            default -> System.out.println("Nội dung đã xử lý");
        }
    }

    static boolean runJob(String kind) {
        try {
            execute(kind);
            return true;
        } catch (Exception e) {
            System.out.println("Job thất bại: "
                    + e.getClass().getSimpleName());
            return false;
        }
    }

    public static void main(String[] args) {
        System.out.println("io success=" + runJob("io"));
        System.out.println("bug success=" + runJob("bug"));
        System.out.println("ok success=" + runJob("ok"));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 BoundaryCatchDemo.java
java BoundaryCatchDemo
```

Stdout:

```text
Job thất bại: IOException
io success=false
Job thất bại: IllegalStateException
bug success=false
Nội dung đã xử lý
ok success=true
```

Khác với một handler nuốt lỗi, `runJob` trả `false` để thông báo rõ thất bại của tác vụ. Ví dụ **không** bảo đảm an toàn với mọi môi trường: công việc có side effect cần transaction/compensation nếu muốn khôi phục; tác vụ nhiều luồng cần cơ chế đồng bộ; handler còn cần chính sách log và phân loại nguyên nhân khi triển khai thật.

Điểm quyết định là **vị trí đặt `catch`**: `catch (Exception)` ở ranh giới giám sát/điều phối có thể có chủ đích, trong khi `catch (Exception)` ở mọi method cấp thấp thường che mất những lỗi không thuộc trách nhiệm của method đó.

### 9.2. Vì sao không thay hết bằng `catch (Throwable)`?

`Throwable` còn bao gồm nhánh `Error`, như `OutOfMemoryError`, `StackOverflowError`, `LinkageError` và `AssertionError`. Với nhiều lỗi nghiêm trọng, trạng thái JVM/tài nguyên có thể không cho phép tiếp tục an toàn.

`catch (Exception)` **không** bắt `Error`. `catch (Throwable)` về mặt kiểu có thể bắt, nhưng không biến JVM thành “không bao giờ sập”. Trong ứng dụng bình thường, tránh dùng `catch (Throwable)` làm handler phục hồi tổng quát.

## 10. Anti-pattern: gom mọi lỗi thành “đã xử lý thành công”

Xem đoạn minh họa:

```java
try {
    saveOrder();
} catch (Exception ignored) {
    // Không làm gì.
}
return true;
```

Đây là đoạn không độc lập; `saveOrder()` chưa được định nghĩa. Vấn đề là nếu lỗi xảy ra, caller vẫn nhận `true`. Có thể đơn hàng chưa được lưu, đã lưu một phần hoặc đã thực hiện side effect trước khi exception phát sinh.

Khi đó `catch (Exception)` tạo ảo giác thành công và **che mọi nguyên nhân**. Một multi-catch cũng có thể sai nếu xử lý như thế này. Cần thiết kế hợp đồng trước:

- Nếu có thể phục hồi: thực hiện biện pháp phục hồi có kiểm chứng, rồi trả kết quả đúng.
- Nếu không thể phục hồi: trả failure có cấu trúc, hoặc ném lại/chuyển đổi exception, giữ `cause`.
- Nếu trạng thái bên ngoài chưa xác định: dùng API xác nhận trạng thái, idempotency key hay transaction/compensation phù hợp; đừng suy luận “ném lỗi thì chưa ghi gì”.

**Chọn kiểu `catch` không tự tạo rollback.** Nó chỉ quyết định những đối tượng exception nào đi vào handler.

## 11. Thứ tự handler khi kết hợp multi-catch và kiểu cha

Có thể đặt multi-catch trước handler tổng quát:

```java
try {
    executeTask();
} catch (java.io.IOException | java.sql.SQLException e) {
    System.out.println("Lỗi nghiệp vụ hạ tầng đã dự kiến");
} catch (Exception e) {
    System.out.println("Lỗi không dự kiến");
}
```

Đoạn minh họa giả định `executeTask()` có thể ném `IOException`, `SQLException`. Đây là cấu trúc hợp lệ: handler đầu bắt hai loại được nêu, handler thứ hai bắt các `Exception` còn lại.

Nhưng thứ tự ngược lại **không hợp lệ**:

```java
// CỐ Ý SAI: handler multi-catch phía sau đã bị Exception bao phủ.
try {
    executeTask();
} catch (Exception e) {
    System.out.println("Rộng");
} catch (java.io.IOException | java.sql.SQLException e) {
    System.out.println("Cụ thể");
}
```

Java từ chối handler không thể tới được vì mọi `IOException`/`SQLException` đều là `Exception` và sẽ bị nhánh đầu giữ lại.

Nếu muốn tránh handler tổng quát, có thể bỏ `catch (Exception)` và để các lỗi không dự kiến truyền lên. Đây thường là thiết kế tốt ở tầng thư viện/domain, nơi không có đủ thông tin để sửa tất cả lỗi.

### 11.1. Một multi-catch không cho “ưu tiên” một loại ở bên trong nó

`catch (IOException | SQLException e)` có **một phần thân duy nhất**. Java không chạy một nửa của handler cho IOException và nửa kia cho SQLException. Nếu thật sự có logic khác nhau, tách `catch(IOException)` và `catch(SQLException)`; không dùng union catch để thay thế một switch trên loại exception.

## 12. Multi-catch, checked và unchecked: chọn tập lỗi đúng

Ví dụ multi-catch kết hợp checked và unchecked:

```java
try {
    parseFromFile();
} catch (java.io.IOException | NumberFormatException e) {
    System.out.println("Dữ liệu nguồn không hợp lệ");
}
```

Đoạn chỉ là minh họa, `parseFromFile()` cần thực sự có khả năng ném checked `IOException` trong chữ ký/hoạt động. Khi đó handler có thể hợp lệ vì hai kiểu không bao phủ nhau.

Tuy vậy, trước khi gộp, phải hỏi: lỗi đọc file và lỗi chuỗi số có cần cùng một hành động không? Nếu lỗi parse cần yêu cầu người dùng sửa nội dung, còn lỗi I/O cần cho chọn nguồn khác, hai handler riêng là hợp lý hơn.

**Không có quy tắc:** “checked luôn cần multi-catch”, “unchecked luôn cần catch cha” hoặc “mỗi checked exception phải có một `catch` riêng”. Java cho phép nhiều cách sắp xếp; lựa chọn phải dựa trên khả năng xử lý, hợp đồng và bảo toàn dữ liệu.

## 13. Thiết kế helper chung thay vì mở rộng handler

Nếu hai handler khác nhau ở phần đầu nhưng có bước cuối giống nhau, không bắt buộc phải dùng multi-catch. Ta có thể tách hàm chung:

```java
try {
    performOperation();
} catch (java.io.IOException e) {
    logFailure("I/O", e);
    recoverFile();
} catch (java.sql.SQLException e) {
    logFailure("SQL", e);
    haltDatabaseRequest();
}
```

Đây là đoạn minh họa phụ thuộc các method được định nghĩa ở lớp bao quanh. Hai handler có chính sách khác nhau nhưng vẫn chia sẻ `logFailure(...)`. Cách này thường rõ hơn một multi-catch chứa phân nhánh bằng `instanceof`.

Đối với API cần đóng tài nguyên, dùng try-with-resources tại nơi phù hợp. Mọi handler — multi-catch hay catch cha — đều không tự động tạo cơ chế dọn dẹp/rollback. Nếu có ngoại lệ khi đóng tài nguyên, cần hiểu primary và suppressed exceptions thay vì nuốt cả hai.

## 14. Lựa chọn theo từng tầng kiến trúc

| Tầng | Ví dụ công việc | Xu hướng phù hợp | Lý do |
| --- | --- | --- | --- |
| Parse dữ liệu đầu vào | Chuyển chuỗi thành số | `catch (NumberFormatException)` | Có thể yêu cầu nhập lại đúng trường. |
| Tầng đọc lưu trữ | Đọc file hoặc truy vấn SQL | Multi-catch nếu cùng chính sách, hoặc hai catch riêng | Không xử lý vô tình những bug thuộc `RuntimeException`. |
| Service nghiệp vụ | Tạo đơn, cập nhật tồn kho | Những exception nghiệp vụ cụ thể và hợp đồng trạng thái rõ ràng | Caller cần biết loại thất bại và mức thay đổi state. |
| CLI / request boundary | Trả lỗi người dùng, đánh dấu request thất bại | `catch (Exception)` có thể hợp lý | Là nơi có trách nhiệm gom failure thành phản hồi/trạng thái. |
| Test framework / runtime chuyên biệt | Thu thập failure của tác vụ | Handler rộng theo chính sách framework | Phải có cách ly, báo cáo, không che `Error` nghiêm trọng. |

Không nên áp dụng máy móc theo tên tầng. Một service có thể thực sự xử lý `Exception` tổng quát ở một boundary cụ thể, hoặc một request handler cần phân loại từng lỗi. Quan trọng là **có chính sách chứng minh được** cho các lỗi bị bắt.

## 15. Tình huống thực tế: vì sao `catch (Exception)` có thể phá hợp đồng?

Giả sử `saveInvoice()` hứa rằng khi không tạo được hóa đơn, caller sẽ nhận failure rõ ràng. Bên trong method vừa có thể ném `IOException`/`SQLException`, vừa có thể có bug `NullPointerException`.

Nếu viết:

```java
try {
    saveInvoice();
} catch (Exception e) {
    System.out.println("Không lưu được hóa đơn");
}
// Tiếp tục như thể hóa đơn đã tạo.
sendConfirmation();
```

Đây là đoạn minh họa, không độc lập; các method chưa được định nghĩa. Handler này bắt cả lỗi hạ tầng và bug; hơn nữa **sau catch vẫn gửi xác nhận**, làm sai hợp đồng. Thay bằng multi-catch có thể giảm phạm vi lỗi bị bắt nhưng **không tự khắc phục** vấn đề tiếp tục sau thất bại:

```java
try {
    saveInvoice();
} catch (java.io.IOException | java.sql.SQLException e) {
    throw new IllegalStateException("Không tạo được hóa đơn", e);
}
sendConfirmation();
```

Mẫu thứ hai minh họa việc **không tiếp tục đường thành công** khi lỗi hạ tầng xảy ra; wrapper giữ nguyên `cause`. Nhưng còn phải thiết kế tác động ngoài hệ thống: nếu hóa đơn đã được lưu một phần trước khi lỗi, gửi lại yêu cầu có thể tạo bản ghi trùng. Transaction, idempotency, kiểm tra trạng thái và phục hồi là những mối quan tâm bổ sung.

**Bài học:** catch chọn phạm vi lỗi; phần thân handler quyết định xử lý có đúng hợp đồng hay không. Cả hai đều cần được đánh giá.

## 16. Các lỗi biên dịch và hiểu nhầm phổ biến

| Lỗi/quan niệm | Giải thích và cách sửa |
| --- | --- |
| “Multi-catch chỉ là `catch(Exception)` viết dài hơn.” | Sai: multi-catch chỉ bao phủ các nhánh được liệt kê; không nhận toàn bộ `RuntimeException`. |
| “`catch(Exception)` chỉ bắt checked exceptions.” | Sai: `RuntimeException extends Exception`, nên handler này còn bắt nhiều unchecked exceptions. |
| “Multi-catch bắt cả `Error` nếu cùng tên thông điệp.” | Sai: chọn handler dựa trên kiểu kế thừa, không dựa vào message. |
| “Có thể viết `IOException \| FileNotFoundException`.” | Sai: hai loại có quan hệ subtype; chỉ chọn cha hoặc dùng handler riêng. |
| “Có thể viết `IOException || SQLException`.” | Sai cú pháp: multi-catch dùng `|` một dấu. |
| “Thêm `IOException` vào multi-catch là luôn hợp lệ.” | Sai: checked exception cụ thể phải phù hợp với khả năng ném từ vùng `try`. |
| “Multi-catch `e` có thể được gán lại như biến thường.” | Sai: tham số multi-catch implicitly final. |
| “`e` trong union catch dùng trực tiếp mọi method của `SQLException`.” | Sai: chỉ những thành viên hợp lệ với kiểu tĩnh chung mới gọi trực tiếp được. |
| “`catch(Exception)` rethrow luôn buộc `throws Exception`.” | Sai trong trường hợp precise rethrow áp dụng và biến catch không bị gán lại. |
| “Bắt được lỗi tức là đã rollback.” | Sai: try/catch không tự hoàn tác các side effect trước đó. |
| “Thêm `catch(Throwable)` sẽ làm chương trình không bao giờ sập.” | Sai: còn nhiều lỗi VM/process và khả năng khôi phục không bảo đảm; còn có thể nuốt `Error`. |
| “Một multi-catch luôn tốt hơn hai catch riêng.” | Sai: khi hai loại lỗi cần xử lý khác nhau, handler riêng diễn đạt đúng ý định hơn. |
| “Chỉ cần in log ở catch là lỗi đã xử lý.” | Chưa đủ nếu trạng thái thất bại không được truyền lên hoặc phục hồi không diễn ra. |
| “Trong cùng `try`, handler sau sẽ chạy tiếp sau handler đầu.” | Sai: một exception đang lan truyền được handler phù hợp đầu tiên xử lý; các nhánh cùng cấp không chạy tuần tự. |

## 17. Cách kiểm thử sự khác nhau

Một bộ kiểm thử tốt không chỉ xác nhận dòng log, mà còn xác nhận những lỗi nào **được xử lý** và lỗi nào **được phép thoát**.

Với `CatchScopeDemo`, thử:

1. Input `"io"`: multi-catch xử lý và không ném ra `main`.
2. Input `"db"`: multi-catch xử lý và không ném ra `main`.
3. Input `"bug"`: `targeted` để `IllegalStateException` thoát; caller quan sát được.
4. Input `"bug"` với `broad`: `catch (Exception)` xử lý và không ném tiếp, dù lỗi lập trình chưa chắc đã được sửa.
5. Input `"ok"`: không handler nào được thực hiện.

Có thể viết JUnit 5 để kiểm tra trực tiếp:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class CatchScopeDemoTest {
    @Test
    void targetedLetsUnexpectedExceptionEscape() {
        assertThrows(IllegalStateException.class,
                () -> CatchScopeDemo.targeted("bug"));
    }

    @Test
    void broadSwallowsUnexpectedExceptionInThisDemo() {
        assertDoesNotThrow(() -> CatchScopeDemo.broad("bug"));
    }

    @Test
    void targetedHandlesExpectedCheckedExceptions() {
        assertDoesNotThrow(() -> CatchScopeDemo.targeted("io"));
        assertDoesNotThrow(() -> CatchScopeDemo.targeted("db"));
    }
}
```

**Đây là file test minh họa**, cần một dự án đã có JUnit Jupiter; không phải chương trình `javac` độc lập. `CatchScopeDemo` và test phải nằm trong package tương thích; ví dụ dùng default package. Kết quả kiểm thử “`broad` không ném ra ngoài” **không chứng minh `broad` an toàn**, chỉ xác nhận hành vi bắt rộng mà chương trình này thể hiện.

Khi test dự án thật, nên xác nhận thêm trạng thái của các đối tượng, dữ liệu đã ghi và kết quả tác vụ, đặc biệt sau exception.

## 18. Bài tập tự luyện

### Bài 1 — Dự đoán handler

Một method công bố `throws IOException, SQLException` và đôi khi ném `IllegalArgumentException`. Nếu caller dùng:

```java
try {
    call();
} catch (java.io.IOException | java.sql.SQLException e) {
    System.out.println("Đã dự kiến");
}
```

Đoạn minh họa giả định `call()` tồn tại. Với `IllegalArgumentException`, handler có chạy không? **Không.** Loại này nằm dưới `RuntimeException`, không thuộc hai nhánh checked đã liệt kê.

### Bài 2 — Sửa multi-catch sai

Vì sao `catch (IOException | FileNotFoundException e)` không biên dịch? Viết hai phiên bản sửa: (a) chỉ dùng `catch (IOException e)` cho một chính sách chung; (b) hai handler riêng, `FileNotFoundException` trước `IOException`, khi cần hành động khác nhau.

### Bài 3 — Biến `e` có thể gán lại không?

Thử thêm `e = new IOException("another");` trong `catch (IOException | SQLException e)`. Giải thích lỗi compiler. So sánh với `catch (Exception e)` thường có thể gán lại, và tại sao việc gán lại làm thay đổi phân tích precise rethrow.

### Bài 4 — Kiểu tĩnh chung của union catch

Trong `catch (IOException | SQLException e)`, gọi `e.getMessage()` hợp lệ, còn `e.getErrorCode()` không trực tiếp hợp lệ. Tại sao? Nếu thực sự cần vendor error code từ `SQLException`, thiết kế với handler riêng sẽ rõ ràng ra sao?

### Bài 5 — Rethrow chính xác

Chạy `MultiCatchRethrowDemo`. Thêm một method `forwardBroad` dùng `catch (Exception e) { throw e; }` quanh `fetch(...)`. Kiểm chứng rằng Java 17 có thể chấp nhận `throws IOException, SQLException` nhờ precise rethrow, miễn `e` không được gán lại. Sau đó thử gán lại `e` và dự đoán thông báo compiler.

### Bài 6 — Chọn chính sách xử lý

Một ứng dụng nhập dữ liệu có thể gặp: file thiếu, SQL timeout, chuỗi số không hợp lệ, `NullPointerException` do bug. Hãy xác định tầng nào thực sự xử lý từng loại, khi nào nên dùng multi-catch, khi nào dùng catch riêng, và boundary nào có thể catch rộng mà vẫn **báo failure rõ ràng**.

### Bài 7 — Đánh giá hợp đồng

Nếu một phương thức đã ghi một nửa dữ liệu rồi ném `SQLException`, liệu thay `catch (Exception)` bằng `catch (IOException | SQLException)` có tự khôi phục dữ liệu không? **Không.** Liệt kê cơ chế transaction hoặc compensation cần thiết để khôi phục trạng thái, và cách caller biết thao tác đã thất bại.

## 19. Checklist chọn handler trước khi commit

- [ ] Tôi có biết chính xác **những loại ngoại lệ mà tầng này xử lý được** không?
- [ ] Các loại đó có cùng một hành động xử lý không? Nếu không, nên tách thành handler riêng.
- [ ] Các lựa chọn của multi-catch có quan hệ cha–con gây lỗi biên dịch không?
- [ ] Mọi lựa chọn checked trong multi-catch có thực sự có nguồn khả năng ném từ `try` không?
- [ ] Handler có vô tình bắt `RuntimeException` không dự kiến và che bug không?
- [ ] Tôi có cần bắt `Exception` ở boundary giám sát thay vì ở tầng nghiệp vụ thấp không?
- [ ] Nếu bắt rộng, liệu kết quả có được đánh dấu thất bại thay vì giả thành công không?
- [ ] Nếu dùng `throw e;`, có giữ nguyên đối tượng và cause cần chẩn đoán không?
- [ ] Tôi có phân biệt precise rethrow với phạm vi handler runtime không?
- [ ] Biến multi-catch `e` có được giữ nguyên theo quy tắc implicitly final không?
- [ ] Các handler đã theo thứ tự hợp lệ, không có catch unreachable chưa?
- [ ] Tài nguyên và trạng thái khi xảy ra exception có được dọn dẹp/rollback theo cơ chế thật, không phải theo giả định không?
- [ ] Kiểm thử có bao gồm cả checked exception dự kiến và unchecked exception ngoài kế hoạch chưa?

**Kết luận:** **Multi-catch gom các ngoại lệ được chỉ đích danh khi chúng cần cùng một cách xử lý; `catch (Exception)` nhận toàn bộ nhánh `Exception`, gồm cả những lỗi lập trình chưa được dự kiến.** Ở tầng ứng dụng có khả năng xử lý cụ thể, ưu tiên handler đúng phạm vi; ở boundary giám sát, bắt rộng có thể phù hợp nếu luôn báo thất bại và bảo toàn chẩn đoán. Cả hai lựa chọn không thay cho thiết kế hợp đồng trạng thái, dọn dẹp tài nguyên và kiểm thử đường lỗi.