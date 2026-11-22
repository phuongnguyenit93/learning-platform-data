# Cú pháp `try-catch` và phạm vi được bảo vệ trong Java

`try-catch` là cấu trúc kiểm soát luồng dùng để **xử lý ngoại lệ phát sinh khi chạy một đoạn mã**. Khối `try` xác định các thao tác được bảo vệ; các nhánh `catch` xác định **loại ngoại lệ nào được tiếp nhận** và **phải làm gì sau khi thao tác thất bại**. Hiểu chính xác phạm vi này quan trọng hơn việc chỉ nhớ cú pháp: đặt một lời gọi ở ngoài `try` thì handler tương ứng có thể không bảo vệ được lời gọi đó; gom quá nhiều thao tác không liên quan trong một `try` cũng dễ bắt nhầm lỗi.

Một nhận định cơ bản:

> `catch` đi kèm một `try` chỉ xem xét ngoại lệ **thoát ra trong lúc thực thi phần thân `try` đó** (bao gồm các phương thức được gọi từ trong khối). Nó không tự động bảo vệ mọi câu lệnh trong phương thức, những câu lệnh nằm bên ngoài `try`, hoặc công việc chạy trên một thread khác.

## 1. Cú pháp đầy đủ và các thành phần

Cấu trúc phổ biến:

```java
try {
    // Những thao tác cần được bảo vệ.
} catch (IllegalArgumentException ex) {
    // Xử lý ngoại lệ phù hợp với IllegalArgumentException.
} catch (IllegalStateException ex) {
    // Xử lý ngoại lệ phù hợp với IllegalStateException.
} finally {
    // Dọn dẹp/kết thúc theo quy tắc của finally.
}
```

Đây là **cấu trúc minh họa**, chưa có thao tác thực tế trong `try`. Ý nghĩa:

- **`try`:** phần thân được thực thi theo thứ tự bình thường cho tới khi hoàn thành hoặc có ngoại lệ làm dừng đường thực thi ấy.
- **`catch (ExceptionType variable)`:** nhánh được xét khi ngoại lệ thoát ra từ `try`. `ExceptionType` phải là `Throwable` hoặc một lớp con; tên `variable` là tham chiếu tới đối tượng lỗi đã bắt.
- **`finally` (tùy chọn):** một phần xử lý kết thúc hoặc dọn dẹp, thường chạy sau `try`/`catch` dù thành công, thất bại hay có `return`. Có những trường hợp JVM kết thúc bất thường khiến `finally` không được bảo đảm thực thi.
- **Câu lệnh phía sau cấu trúc:** được thực thi nếu toàn bộ cấu trúc `try-catch-finally` hoàn tất bình thường; không tự động chạy nếu ngoại lệ vẫn chưa được xử lý.

Với `try` thông thường, phải có **ít nhất một `catch` hoặc `finally`**. Các biến thể hợp lệ:

```java
try {
    operation();
} catch (RuntimeException ex) {
    handle(ex);
}
```

```java
try {
    operation();
} finally {
    cleanup();
}
```

```java
try {
    operation();
} catch (RuntimeException ex) {
    handle(ex);
} finally {
    cleanup();
}
```

Các đoạn này là **khung minh họa**, giả định `operation`, `handle`, `cleanup` được định nghĩa. Trường hợp `try-finally` không có `catch` **không tự bắt ngoại lệ**; `finally` chạy theo quy tắc rồi lỗi tiếp tục lan ra nếu chưa được xử lý.

`try-with-resources` là một dạng `try` đặc biệt dùng cho tài nguyên `AutoCloseable`, có thể viết không có `catch` và `finally` riêng vì bản thân cú pháp quản lý việc đóng tài nguyên. Phần cuối bài có ví dụ để phân biệt.

## 2. Phạm vi được bảo vệ là phần thân `try` và những lời gọi thực thi từ đó

Xem đoạn mã:

```java
prepare();
try {
    parse();
    save();
} catch (IllegalArgumentException ex) {
    report(ex);
}
finish();
```

Đây là đoạn **giả mã Java minh họa**: các phương thức cần được định nghĩa, và mã phải nằm trong một phương thức/lớp thực tế.

- `prepare()` đứng **trước `try`**: ngoại lệ nó ném không đi vào `catch` đang xét.
- `parse()` và `save()` được gọi **bên trong `try`**: nếu chúng hoặc các hàm con của chúng ném `IllegalArgumentException` chưa được bắt ở tầng trong, handler ở đây có thể nhận lỗi.
- `report(ex)` chạy **bên trong nhánh `catch`**, không nằm trong thân `try` vừa nêu. Nếu chính `report` ném ngoại lệ, các nhánh `catch` còn lại của cùng cấu trúc không tự bắt lỗi mới đó.
- `finish()` đứng **sau cấu trúc `try-catch`**: ngoại lệ tại đây không thuộc phạm vi bảo vệ của `try` phía trên.
- Nếu `parse()` ném ngoại lệ được bắt, `save()` sẽ bị bỏ qua ở lần thực thi này. Java chuyển tới handler, không quay lại vị trí sau `parse()` để tiếp tục `save()`.

“Phạm vi bảo vệ” có hai mặt:

1. **Phạm vi câu lệnh:** phần thân `try` chứa những lệnh nào?
2. **Phạm vi chuỗi gọi động:** khi một lệnh trong `try` gọi một phương thức khác, ngoại lệ chưa được xử lý ở sâu trong phương thức đó có thoát về điểm gọi trong `try` hay không?

Không cần đặt `try-catch` vào từng phương thức trong chuỗi A → B → C nếu tầng A có trách nhiệm xử lý lỗi từ C. Chỉ cần lời gọi B nằm trong `try` của A và lỗi đi qua B mà không bị bắt ở dưới, `catch` của A có thể xử lý.

### Phân biệt phạm vi của `try` và phạm vi của biến

Biến cục bộ được khai báo **bên trong phần thân `try`** không thể được tham chiếu trực tiếp từ `catch` hoặc câu lệnh sau `try`:

```java
try {
    int result = Integer.parseInt("42");
    System.out.println(result);
} catch (NumberFormatException ex) {
    // Không thể sử dụng biến result ở đây.
}
```

Ngược lại, một biến được khai báo ngoài `try` vẫn chịu quy tắc **definite assignment** trước khi đọc. Ví dụ sau là hợp lệ:

```java
int result;
try {
    result = Integer.parseInt("42");
} catch (NumberFormatException ex) {
    result = 0;
}
System.out.println(result);
```

Vì cả đường thành công và đường xử lý lỗi đều gán `result`, Java chứng minh biến đã được gán trước khi in. Điều này không có nghĩa **luôn** nên trả `0` khi parse thất bại: phải xác định rõ `0` có phải giá trị dự phòng hợp lệ theo hợp đồng hay không. Nếu không, ném lại hoặc chuyển lỗi thành kết quả tường minh sẽ đúng hơn.

## 3. Ba đường đi chính của một cấu trúc `try-catch`

### Trường hợp A — không có ngoại lệ

```text
Vào try
  → chạy các câu lệnh trong try
  → không chạy catch
  → chạy finally nếu có
  → tiếp tục sau try-catch-finally
```

### Trường hợp B — ngoại lệ phù hợp được ném trong `try`

```text
Vào try
  → chạy đến câu lệnh gây lỗi
  → bỏ qua phần còn lại của try
  → tìm catch phù hợp đầu tiên
  → chạy catch được chọn
  → chạy finally nếu có
  → tiếp tục sau cấu trúc nếu catch hoàn tất bình thường
```

Một ngoại lệ cụ thể chỉ được xử lý bởi **một handler được chọn** của cùng cấu trúc `try`; Java không chạy tuần tự mọi `catch` phù hợp.

### Trường hợp C — không có `catch` nào phù hợp

```text
Vào try
  → phát sinh ngoại lệ
  → không có catch nào phù hợp
  → chạy finally nếu có
  → ngoại lệ tiếp tục lan ra caller hoặc try ở ngoài
```

Lưu ý: kết quả còn phụ thuộc `finally`, bởi `finally` có thể ném ngoại lệ khác hoặc dùng `return`; một thiết kế tốt nên tránh làm mất lỗi gốc bằng các thao tác thay đổi luồng trong `finally`.

## 4. Ví dụ Java 17+ hoàn chỉnh: xác định câu lệnh nào chạy

Lưu toàn bộ đoạn dưới đây vào tệp **`TryCatchScopeDemo.java`**:

```java
public class TryCatchScopeDemo {

    static int parsePositive(String raw) {
        int number = Integer.parseInt(raw);
        if (number <= 0) {
            throw new IllegalArgumentException(
                    "number must be positive");
        }
        return number;
    }

    static void handle(String raw) {
        System.out.println("CASE " + raw);
        System.out.println("outside-before: ready");

        try {
            System.out.println("inside: begin");
            int result = parsePositive(raw);
            System.out.println("inside: result=" + result);
        } catch (NumberFormatException ex) {
            System.out.println("catch-format: invalid integer");
        } catch (IllegalArgumentException ex) {
            System.out.println("catch-rule: " + ex.getMessage());
        } finally {
            System.out.println("finally: done");
        }

        System.out.println("outside-after: continue");
    }

    static void nested() {
        System.out.println("NESTED");

        try {
            try {
                System.out.println("inner: begin");
                throw new IllegalStateException("inner failed");
            } catch (NumberFormatException ex) {
                System.out.println("inner-catch");
            } finally {
                System.out.println("inner-finally");
            }
        } catch (IllegalStateException ex) {
            System.out.println("outer-catch: " + ex.getMessage());
        }

        System.out.println("nested: continue");
    }

    public static void main(String[] args) {
        handle("3");
        handle("0");
        handle("abc");
        nested();
    }
}
```

Lệnh biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 TryCatchScopeDemo.java
java TryCatchScopeDemo
```

**Stdout chính xác:**

```text
CASE 3
outside-before: ready
inside: begin
inside: result=3
finally: done
outside-after: continue
CASE 0
outside-before: ready
inside: begin
catch-rule: number must be positive
finally: done
outside-after: continue
CASE abc
outside-before: ready
inside: begin
catch-format: invalid integer
finally: done
outside-after: continue
NESTED
inner: begin
inner-finally
outer-catch: inner failed
nested: continue
```

### Đọc từng nhánh

**`handle("3")`:** `parsePositive` trả về `3`. Toàn bộ phần `try` chạy, không có `catch` nào được chọn; `finally` vẫn chạy. Sau đó phương thức thực hiện câu lệnh `outside-after`.

**`handle("0")`:** parse thành công, nhưng số không dương nên `parsePositive` ném `IllegalArgumentException`. Chương trình **không in** dòng `inside: result=...`. Handler `NumberFormatException` không phù hợp, handler `IllegalArgumentException` được chọn, rồi `finally` và phần sau cấu trúc chạy.

**`handle("abc")`:** `Integer.parseInt` ném `NumberFormatException`. Vì lớp này kế thừa `IllegalArgumentException`, cả hai handler có quan hệ kiểu phù hợp, nhưng Java chọn **nhánh đầu tiên** `catch (NumberFormatException)`. Nhánh `catch (IllegalArgumentException)` không chạy thêm lần nữa.

**`nested()`:** ngoại lệ `IllegalStateException` phát sinh trong `try` bên trong. `catch (NumberFormatException)` bên trong không phù hợp; `finally` bên trong chạy. Ngoại lệ tiếp tục lan tới handler `IllegalStateException` của `try` bên ngoài, rồi phương thức tiếp tục bình thường.

Từ chương trình này có thể thấy **phạm vi đang bảo vệ thực sự dựa vào chỗ đặt câu lệnh** và **quan hệ khớp kiểu**. Khi xử lý xong một ngoại lệ, JVM không chạy tiếp những lệnh trong `try` đã bị bỏ qua.

## 5. Java chọn nhánh `catch` nào?

Đối với cùng một cấu trúc `try`, các nhánh `catch` được xem xét **theo thứ tự viết từ trên xuống**. Một handler khớp khi đối tượng ngoại lệ thuộc kiểu được khai báo hoặc một **lớp con** của nó.

Ví dụ:

```java
try {
    Integer.parseInt("x");
} catch (NumberFormatException ex) {
    System.out.println("number format");
} catch (IllegalArgumentException ex) {
    System.out.println("other illegal argument");
}
```

Kết quả:

```text
number format
```

`NumberFormatException extends IllegalArgumentException` nên phải đặt `catch` cụ thể trước `catch` tổng quát. Nếu đảo thứ tự:

```java
// Cố ý không biên dịch:
try {
    Integer.parseInt("x");
} catch (IllegalArgumentException ex) {
    System.out.println("general");
} catch (NumberFormatException ex) {
    System.out.println("specific");
}
```

Trình biên dịch báo nhánh `NumberFormatException` không thể tới được, bởi handler `IllegalArgumentException` phía trước đã bao phủ mọi đối tượng thuộc subtype đó.

Những ghi nhớ cần thiết:

- `catch (Exception ex)` bắt những ngoại lệ thuộc `Exception`, gồm `RuntimeException`, nhưng **không bắt `Error`**.
- `catch (RuntimeException ex)` không bắt checked `IOException`.
- `catch (IOException ex)` có thể bắt `FileNotFoundException`, nhưng không bắt `IllegalArgumentException`.
- `catch (Throwable ex)` bắt cả `Error`, song thường không thích hợp cho xử lý lỗi nghiệp vụ.
- Handler dành riêng cho nhiều nhánh có phản ứng khác nhau giúp mã dễ bảo trì; không cần bắt rộng rồi kiểm tra chuỗi message để phân loại.

### `catch` dành cho checked exception phải có cơ sở

Một đoạn như sau **cố ý không biên dịch**:

```java
try {
    System.out.println("hello");
} catch (java.io.IOException ex) {
    System.out.println("I/O failed");
}
```

Phần `try` không thể phát sinh checked `IOException` theo phân tích của trình biên dịch, nên handler ấy bị coi là không thể tới được. Đừng thêm `catch (IOException)` một cách máy móc chỉ vì đang viết mã Java; hãy đặt nó quanh lời gọi thực sự có thể ném loại checked exception này.

Ngoại lệ unchecked có quy tắc kiểm tra khác: trình biên dịch không buộc mọi đường ném `RuntimeException` phải được khai báo trước.

## 6. Ngoại lệ trong `catch` có được các `catch` “anh em” bắt không?

**Không.** Những nhánh `catch` xuất hiện sau không phải mạng lưới bảo vệ phần thân của nhau. Ví dụ:

```java
try {
    throw new NumberFormatException("bad number");
} catch (NumberFormatException ex) {
    throw new IllegalStateException("handler failed", ex);
} catch (IllegalStateException ex) {
    System.out.println("This line is not reached");
}
```

Đây là **đoạn minh họa**, cần đặt trong phương thức hợp lệ. Nó có thể biên dịch, nhưng nhánh `catch (IllegalStateException)` phía sau **không bắt** lỗi mới ném từ handler trước. `IllegalStateException` lan ra vùng xử lý bên ngoài; nếu không có handler ngoài, nó có thể trở thành ngoại lệ chưa được bắt.

Nếu mục tiêu là bắt luôn lỗi phát sinh từ handler đầu tiên, cần một cấu trúc `try-catch` **bao ngoài**, hoặc thiết kế lại handler cho an toàn.

Mô hình đúng:

```java
try {
    try {
        throw new NumberFormatException("bad number");
    } catch (NumberFormatException ex) {
        throw new IllegalStateException("converted", ex);
    }
} catch (IllegalStateException ex) {
    System.out.println("outer catch: " + ex.getMessage());
}
```

Đầu ra:

```text
outer catch: converted
```

Ở đây `catch` ngoài bảo vệ **toàn bộ cấu trúc `try-catch` trong**, nên nó nhận được ngoại lệ do handler trong ném. Đây cũng là lý do một `try-catch` nằm trong phương thức gọi có thể xử lý lỗi từ phương thức con dù con đã bắt một lỗi rồi ném một loại lỗi mới.

## 7. `try-catch` bảo vệ được những lời gọi sâu đến đâu?

Giả sử:

```java
static void stepC() {
    throw new IllegalStateException("error at C");
}

static void stepB() {
    stepC();
}

static void stepA() {
    try {
        stepB();
    } catch (IllegalStateException ex) {
        System.out.println("A handles: " + ex.getMessage());
    }
}
```

Đây là **ba phương thức minh họa**, cần đặt trong cùng một lớp. Mặc dù `throw` xảy ra ở `stepC`, handler `catch` của `stepA` vẫn bắt được vì:

1. `stepA` gọi `stepB` **khi đang ở trong `try`**.
2. `stepB` gọi `stepC`, và `stepC` ném lỗi.
3. Không có handler phù hợp trong `stepC` hay `stepB`, nên ngoại lệ quay lên điểm gọi `stepB()` thuộc `try` của `stepA`.
4. `catch (IllegalStateException)` của A phù hợp và được chạy.

Nếu thay `stepB()` bằng một thao tác bất đồng bộ khởi chạy thread riêng, quy tắc này **không còn tương đương**: `try-catch` quanh lệnh `thread.start()` không tự động bắt ngoại lệ phát sinh sau đó trong thread mới. Với tác vụ submit tới `ExecutorService`, lỗi có thể được quan sát qua `Future.get()`/`ExecutionException` tùy API.

## 8. `try-catch` lồng nhau: handler gần phạm vi thực thi hơn được xét trước

Xét:

```java
try {
    try {
        throw new NumberFormatException("abc");
    } catch (IllegalArgumentException ex) {
        System.out.println("inner handles");
    }
} catch (NumberFormatException ex) {
    System.out.println("outer handles");
}
```

Đầu ra:

```text
inner handles
```

Handler **bên trong** đã bắt `NumberFormatException` qua kiểu cha `IllegalArgumentException`. Handler bên ngoài dù khai báo kiểu con cụ thể hơn **không nhận lỗi** vì ngoại lệ đã được xử lý.

Nếu bên trong không có `catch` khớp, ngoại lệ mới lan ra ngoài. JVM không chọn “handler có kiểu cụ thể nhất trên toàn bộ mã nguồn”; nó tìm handler phù hợp trong các vùng đang có hiệu lực, xét từ vùng trong ra vùng ngoài.

Bài học thiết kế: một `catch (Exception ex)` đặt quá thấp và nuốt lỗi có thể khiến tầng gọi bên ngoài không bao giờ nhận được ngoại lệ nghiệp vụ cụ thể. Đừng bắt lỗi ở tầng không có hành động xử lý có ý nghĩa.

## 9. `finally` có nằm trong phạm vi `catch` không?

Một `finally` gắn với `try-catch` thường thực thi khi rời cấu trúc, kể cả khi có `return` hoặc ngoại lệ cần lan truyền. Nhưng **ngoại lệ phát sinh từ `finally` không được những `catch` anh em của cùng cấu trúc bắt**.

Ví dụ:

```java
try {
    System.out.println("try success");
} catch (IllegalArgumentException ex) {
    System.out.println("catch argument");
} finally {
    throw new IllegalStateException("cleanup failed");
}
```

Đoạn minh họa trên in `"try success"` rồi ném `IllegalStateException`. `catch (IllegalArgumentException)` không xử lý ngoại lệ phát sinh sau đó trong `finally`; người gọi/`try` bên ngoài phải xử lý nếu cần.

Đặc biệt, `return` hoặc `throw` trong `finally` có thể **thay đổi đường hoàn tất** và che mất lỗi đang lan truyền từ `try`/`catch`. Do đó nên dùng `finally` cho dọn dẹp có kiểm soát; không lạm dụng `return` trong `finally`.

### Quản lý tài nguyên: ưu tiên `try-with-resources`

Với đối tượng triển khai `AutoCloseable`, dùng:

```java
static String firstLine(java.nio.file.Path path)
        throws java.io.IOException {
    try (var reader = java.nio.file.Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
```

Đây là **một phương thức minh họa**, cần một `Path` hợp lệ khi gọi và có thể ném `IOException`. Reader sẽ được đóng khi rời phần thân `try`, kể cả khi việc đọc gặp ngoại lệ. Nếu thao tác chính và thao tác đóng cùng lỗi, Java có cơ chế **suppressed exceptions** giúp giữ lỗi đóng cùng ngoại lệ chính.

Các lưu ý:

- `try-with-resources` không bảo đảm tài nguyên ngoài process (chẳng hạn giao dịch cơ sở dữ liệu) tự rollback trong mọi trường hợp; điều đó phụ thuộc API và giao dịch.
- Nếu tài nguyên `close()` ném ngoại lệ, loại checked exception của việc đóng cũng có thể cần được bắt/khai báo theo hợp đồng.
- Không phải tài nguyên nào cũng cho phép tái sử dụng sau khi đóng.
- Có thể kết hợp `try-with-resources` với `catch` và `finally` để xử lý lỗi và hoàn tất công việc.

## 10. Multi-catch và phạm vi một handler

Khi nhiều kiểu ngoại lệ **không có quan hệ cha/con** được xử lý theo cách giống nhau, có thể viết:

```java
try {
    operation();
} catch (java.io.IOException | NumberFormatException ex) {
    System.out.println("Operation failed: "
            + ex.getClass().getSimpleName());
}
```

Đây là một cấu trúc minh họa; `operation()` cần là phương thức có khả năng ném checked `IOException` nếu dùng đoạn này như mã hoàn chỉnh. Biến `ex` của multi-catch được xem là **ngầm `final`**, không được gán lại. Các kiểu lựa chọn phải không nằm trong quan hệ kế thừa trực tiếp hoặc gián tiếp.

Không hợp lệ:

```java
// Cố ý không biên dịch: NumberFormatException là subclass.
catch (NumberFormatException | IllegalArgumentException ex) {
    // ...
}
```

Dùng `catch (IllegalArgumentException)` nếu hành động xử lý là như nhau; nếu khác nhau, dùng các `catch` riêng với subclass trước. `multi-catch` không làm rộng phạm vi các câu lệnh được bảo vệ: nó vẫn chỉ thuộc về **phần `try` tương ứng**.

## 11. Đặt `try` hẹp hay rộng?

### `try` quá rộng

```java
try {
    parseInput();
    updateAccount();
    sendNotification();
} catch (IllegalArgumentException ex) {
    showInputError();
}
```

Các phương thức là **tên minh họa**. Nếu `updateAccount` cũng ném `IllegalArgumentException` do một sai lệch lập trình hoặc trạng thái, handler `showInputError` có thể báo nhầm thành “người dùng nhập sai”. Một handler xử lý một loại lỗi nhưng phần `try` chứa nhiều thao tác không liên quan làm **nguồn lỗi không rõ**.

### `try` quá hẹp

```java
try {
    prepareInput();
} catch (IllegalArgumentException ex) {
    showInputError();
}
parseInput();
```

Nếu lỗi cần xử lý lại phát sinh từ `parseInput()` **nằm ngoài `try`**, handler phía trên không giúp gì. Chưa kể nếu `parseInput` có checked exception, người viết vẫn phải tuân theo hợp đồng `throws` tương ứng.

### Phạm vi có trách nhiệm rõ ràng

```java
final Input input;
try {
    input = parseInput();
} catch (InvalidInputException ex) {
    showInputError(ex);
    return;
}
updateAccount(input);
```

Đoạn trên là **mô hình minh họa**, cần các kiểu `Input`, `InvalidInputException` và phương thức tương ứng. Ý tưởng là chỉ bắt lỗi thuộc bước parse tại ranh giới hiểu được lỗi nhập liệu. Nếu `updateAccount` thất bại vì sự cố hệ thống, hãy để xử lý tại nơi khác phù hợp hơn, chẳng hạn handler của tầng ứng dụng.

Không cần cố ép `try` thành một dòng. **Phạm vi đúng là phạm vi của thao tác và chính sách xử lý**: một giao dịch nhiều bước có thể cần vùng `try` bao cả giao dịch để quản lý rollback ở ranh giới chung. Quan trọng là biết handler đang nhận được những loại lỗi từ thao tác nào.

## 12. Phân biệt `try-catch` với `throws`

`try-catch` xử lý ngoại lệ **khi thực thi**; `throws` khai báo rằng phương thức có thể để một ngoại lệ **lan ra**. Hai cấu trúc phục vụ mục đích khác nhau.

Ví dụ:

```java
static String readConfig(java.nio.file.Path file)
        throws java.io.IOException {
    return java.nio.file.Files.readString(file);
}

static void start(java.nio.file.Path file) {
    try {
        String value = readConfig(file);
        System.out.println(value);
    } catch (java.io.IOException ex) {
        System.out.println("Configuration unavailable");
    }
}
```

Đây là hai phương thức minh họa. `readConfig` khai báo `throws IOException` và không tự bắt lỗi. `start` bao quanh **lời gọi `readConfig`** bằng `try` và bắt lỗi I/O. Phương thức `start` có thể chọn cách khác là khai báo `throws IOException` để chuyển trách nhiệm cho tầng bên ngoài.

Khai báo `throws IOException` **không** tự chặn việc thực thi hoặc xử lý lỗi; còn `catch (IOException)` phải nằm trong vùng `try` bảo vệ lời gọi có nguy cơ, và được xét chỉ khi ngoại lệ tương ứng thực sự thoát ra.

Nếu `readConfig` ném unchecked exception như `NullPointerException` do lỗi lập trình, `catch (IOException)` không bắt nó. Chọn phạm vi và loại handler theo lỗi mà tầng này **có trách nhiệm xử lý**, không phải theo suy nghĩ rằng đã có `catch` thì không thể xảy ra lỗi nữa.

## 13. Những lỗi phổ biến về cú pháp và phạm vi

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Viết `try { ... }` bình thường nhưng không có `catch` hay `finally` | Cú pháp `try` thường cần ít nhất một trong hai | Thêm `catch`/`finally`, hoặc dùng `try-with-resources` đúng dạng |
| Đặt lời gọi dễ lỗi ở ngoài `try` | Handler không có hiệu lực cho lời gọi ấy | Bao đúng thao tác cần xử lý |
| Đặt `catch (Exception)` trước `catch (IOException)` | Handler lớp con bị che khuất | Đưa `IOException` lên trước hoặc bỏ nhánh dư |
| Mong handler thứ hai bắt lỗi ném ra từ handler thứ nhất | Các `catch` cùng cấp không bảo vệ nhau | Dùng một `try-catch` bên ngoài hoặc thay logic |
| Nghĩ `catch` được chạy cả khi không có ngoại lệ | `catch` chỉ chạy khi có lỗi phù hợp | Đặt logic luôn cần chạy ngoài `catch` hoặc trong `finally` |
| Nghĩ `finally` tự động nuốt ngoại lệ | Thường ngoại lệ tiếp tục lan sau `finally` | Có handler phù hợp tại ranh giới có thể xử lý |
| Dùng biến khai báo bên trong `try` từ `catch` | Phạm vi biến chỉ nằm trong block khai báo | Khai báo ngoài khi thực sự cần, xử lý definite assignment |
| Viết `catch(IOException)` khi `try` không thể ném lỗi checked đó | Handler có thể bị compiler báo không thể tới được | Bắt đúng kiểu ngoại lệ của thao tác được gọi |
| Bao toàn bộ phương thức trong `try` rồi `catch(Exception) { return null; }` | Che lấp lỗi, không rõ thao tác thất bại | Thu hẹp phạm vi và giữ lỗi theo hợp đồng |
| Dùng `try-catch` quanh `thread.start()` để bắt lỗi tác vụ sau đó | Tác vụ chạy trên stack của thread khác | Dùng kết quả bất đồng bộ/handler của tác vụ, tùy API |
| Gọi `return` trong `finally` | Có thể che mất kết quả hoặc ngoại lệ đang chờ | Tránh `return`/`throw` không cần thiết trong `finally` |

## 14. Tự luyện đọc luồng thực thi

**Bài A — ngoại lệ trong `try` và handler phù hợp**

```java
try {
    System.out.println("A");
    Integer.parseInt("abc");
    System.out.println("B");
} catch (NumberFormatException ex) {
    System.out.println("C");
}
System.out.println("D");
```

Kết quả:

```text
A
C
D
```

Dòng B bị bỏ qua vì ngoại lệ đã làm gián đoạn phần còn lại của `try`.

**Bài B — ngoại lệ phát sinh ngoài `try`**

```java
Integer.parseInt("abc");
try {
    System.out.println("inside");
} catch (NumberFormatException ex) {
    System.out.println("caught");
}
```

Không có handler phía ngoài, ngoại lệ xảy ra ngay ở lệnh đầu và những câu sau không được thực thi trên cùng đường gọi. `catch` của khối phía dưới **không bảo vệ câu lệnh trước nó**.

**Bài C — ngoại lệ ném từ handler**

```java
try {
    throw new IllegalArgumentException("first");
} catch (IllegalArgumentException ex) {
    throw new IllegalStateException("second", ex);
} catch (IllegalStateException ex) {
    System.out.println("sibling");
}
```

Không in `sibling`. Lỗi `IllegalStateException` ném từ handler thứ nhất sẽ truyền ra ngoài; handler thứ hai chỉ áp dụng cho lỗi từ phần `try`.

**Bài D — handler bên trong kiểu cha**

```java
try {
    try {
        throw new NumberFormatException("bad");
    } catch (IllegalArgumentException ex) {
        System.out.println("inner");
    }
} catch (NumberFormatException ex) {
    System.out.println("outer");
}
```

Kết quả là `inner`. Ngoại lệ được bắt ở phạm vi bên trong; tầng ngoài không nhận lại nếu không có `throw` mới.

**Bài E — `finally` khi có lỗi không được bắt ở tầng hiện tại**

```java
try {
    throw new IllegalStateException("failure");
} catch (NumberFormatException ex) {
    System.out.println("number format");
} finally {
    System.out.println("cleanup");
}
```

Cấu trúc trên in `cleanup` rồi `IllegalStateException` tiếp tục lan ra caller (hoặc thành uncaught exception nếu không có handler phù hợp). Dòng `number format` không xuất hiện.

## 15. Checklist trước khi thêm `try-catch`

1. **Đoạn mã nào thực sự cần được bảo vệ?** Xác định đúng lời gọi hoặc thao tác có khả năng phát sinh ngoại lệ bạn muốn xử lý.
2. **Ngoại lệ đi từ đâu tới?** Xem API/thân phương thức được gọi; nếu lỗi đã được handler bên trong xử lý, nó không còn lan lên handler ngoài.
3. **Chọn đúng kiểu `catch` chưa?** Dựa trên kiểu thực tế, quan hệ lớp cha/con và chính sách xử lý; đặt subtype trước supertype.
4. **Handler có khả năng làm gì?** Phục hồi, chuyển trạng thái thất bại, hiển thị lỗi phù hợp hoặc ném lại có ngữ cảnh. Không nuốt lỗi chỉ để chương trình “chạy tiếp”.
5. **Phần còn lại của `try` có bị bỏ qua không?** Nếu một lời gọi ném ngoại lệ, các câu sau trên đường thành công không chạy. Đừng đặt giả định rằng mọi tác động đã xảy ra đều tự hoàn tác.
6. **Có tài nguyên cần đóng không?** Dùng `try-with-resources` cho `AutoCloseable`; tránh che nguyên nhân bằng lỗi hoặc `return` trong `finally`.
7. **Phạm vi có rộng quá không?** Nếu một handler có thể bắt lỗi từ nhiều thao tác khác bản chất, cân nhắc tách ranh giới để thông báo và phục hồi chính xác.
8. **Có thread/tác vụ bất đồng bộ không?** `try-catch` chỉ xử lý ngoại lệ trên đường thực thi động thuộc phạm vi của nó, không tự lấy lỗi ở thread khác.

**Ghi nhớ:** khối `try` xác định **phần mã đang được bảo vệ**; các `catch` xác định **kiểu lỗi và hành động xử lý**; `finally` dành cho **công việc kết thúc**. Java không chạy lại câu lệnh đã thất bại sau khi `catch` xong, không cho `catch` ở dưới “bảo vệ ngược” câu lệnh ở trên, và không tự bắt ngoại lệ từ thread khác. Đặt phạm vi hợp lý giúp xử lý lỗi đúng nguồn và tránh giấu lỗi quan trọng.