# Try-catch lồng nhau và ranh giới xử lý ngoại lệ trong Java

Trong Java, `try-catch` có thể nằm **bên trong một `try` khác**. Cách tổ chức này giúp phân chia trách nhiệm: tầng trong xử lý lỗi mà nó **biết cách khôi phục**, còn tầng ngoài xử lý lỗi **vượt khỏi khả năng** của tầng trong hoặc quyết định kết quả của toàn bộ thao tác.

Điều khó không phải viết nhiều dấu ngoặc nhọn, mà là trả lời đúng ba câu hỏi:

1. **Ngoại lệ được ném ở đâu?** Nó đang nằm trong vùng `try` nào và đi qua những lời gọi nào?
2. **Handler nào được xét trước?** Một `catch` ở vùng trong có thể bắt lỗi trước khi handler ở vùng ngoài nhìn thấy, ngay cả khi handler ngoài có kiểu cụ thể hơn.
3. **Tầng nào có trách nhiệm xử lý?** Sau khi bắt lỗi, nên tiếp tục, ném lại, chuyển sang ngoại lệ mới có `cause` hay dừng thao tác?

**Quy tắc nền tảng:** Java tìm handler phù hợp theo **vùng xử lý đang hoạt động từ trong ra ngoài**. Trong cùng một cấu trúc `try`, các nhánh `catch` được xét **theo thứ tự viết từ trên xuống**. Handler đã xử lý xong mà không ném lại sẽ ngăn ngoại lệ đó lan ra tầng ngoài.

## 1. Cú pháp của `try-catch` lồng nhau

Cấu trúc tổng quát:

```java
try {
    // Công việc của phạm vi bên ngoài.
    try {
        // Công việc cần một chính sách xử lý cục bộ.
    } catch (IllegalArgumentException ex) {
        // Xử lý loại lỗi trong phạm vi bên trong.
    } finally {
        // Kết thúc/dọn dẹp cho phạm vi bên trong.
    }

    // Chỉ chạy nếu cấu trúc bên trong hoàn tất bình thường.
} catch (IllegalStateException ex) {
    // Nhận lỗi từ phần try ngoài, kể cả lỗi lan ra từ bên trong.
} finally {
    // Kết thúc/dọn dẹp cho phạm vi ngoài.
}
```

Đây là **khung cú pháp minh họa**, không phải chương trình độc lập. Có thể đặt `try-catch` trong phương thức, vòng lặp, một nhánh điều kiện hoặc thậm chí trong một nhánh `catch` khác.

Ở ví dụ:

- `try` ngoài đang thực thi cả cấu trúc `try-catch-finally` trong như một phần nội dung của nó.
- `catch (IllegalArgumentException)` trong được xét cho các lỗi thoát khỏi **phần thân `try` trong**.
- Nếu lỗi trong không khớp `catch` trong, hoặc khối `catch` trong **ném một lỗi mới**, lỗi có thể đi ra ngoài và được `catch` ngoài bắt nếu tương thích.
- `finally` trong thường chạy khi rời `try` trong; `finally` ngoài thường chạy khi rời `try` ngoài. Khi lỗi lan từ trong ra ngoài, các hoạt động dọn dẹp xảy ra theo phạm vi đang thoát.
- Những lệnh còn lại trong phần `try` mà lỗi đã làm gián đoạn **không tự động tiếp tục** sau khi handler tầng ngoài xử lý xong.

### Sơ đồ đường đi

```text
try ngoài
│
├─ thao tác trước
│
├─ try trong
│  ├─ lệnh gây lỗi X
│  ├─ catch trong khớp X?
│  │  ├─ Có  → xử lý xong → finally trong → tiếp tục trong try ngoài
│  │  └─ Không → finally trong → X đi ra try ngoài
│  └─ nếu catch trong ném Y → finally trong → Y đi ra try ngoài
│
├─ lệnh sau try trong, chỉ chạy nếu phần trong hoàn tất bình thường
│
├─ catch ngoài phù hợp với X/Y (nếu X/Y thoát khỏi try ngoài)
│
└─ finally ngoài
   ↓
sau toàn bộ cấu trúc, nếu nó hoàn tất bình thường
```

Một điểm dễ nhầm: **“handler gần nhất” không có nghĩa “handler khai báo kiểu con cụ thể nhất trên toàn chương trình”**. Điều quan trọng trước hết là handler nằm ở **vùng đang bảo vệ đường thực thi**.

## 2. Tình huống A: handler bên trong xử lý xong

Xem đoạn mã nằm trong thân một phương thức:

```java
try {
    try {
        throw new NumberFormatException("bad number");
    } catch (IllegalArgumentException ex) {
        System.out.println("inner: handled");
    }

    System.out.println("outer: after inner");
} catch (NumberFormatException ex) {
    System.out.println("outer: number-format");
}
```

**Stdout:**

```text
inner: handled
outer: after inner
```

`NumberFormatException` kế thừa `IllegalArgumentException`, nên `catch (IllegalArgumentException)` trong bắt được lỗi. Dù `catch (NumberFormatException)` ngoài cụ thể hơn, nó **không được chạy**, vì ngoại lệ đã được xử lý trong.

Đường đi: ném lỗi → handler trong → hoàn thành cấu trúc trong → tiếp tục câu lệnh sau cấu trúc trong → kết thúc `try` ngoài bình thường.

Khi nào hợp lý? Tầng trong có đủ khả năng phục hồi: chẳng hạn nó phát hiện một dòng nhập liệu không hợp lệ, bỏ qua dòng đó theo hợp đồng cho phép, và tầng ngoài tiếp tục xử lý những dòng còn lại.

**Chú ý:** “không ném lại” chỉ hợp lý nếu handler thật sự đã đưa chương trình về trạng thái chấp nhận được. Một `catch` rỗng làm tầng ngoài tưởng mọi thứ thành công có thể là lỗi thiết kế.

## 3. Tình huống B: handler trong không khớp, lỗi lan ra ngoài

Ví dụ:

```java
try {
    try {
        System.out.println("inner: begin");
        throw new IllegalStateException("repository unavailable");
    } catch (NumberFormatException ex) {
        System.out.println("inner: invalid number");
    } finally {
        System.out.println("inner: cleanup");
    }

    System.out.println("outer: next operation");
} catch (IllegalStateException ex) {
    System.out.println("outer: " + ex.getMessage());
}
System.out.println("after: continue");
```

**Stdout:**

```text
inner: begin
inner: cleanup
outer: repository unavailable
after: continue
```

Phân tích:

1. `try` trong ném `IllegalStateException`.
2. Handler `NumberFormatException` trong không khớp.
3. `finally` trong chạy và in `inner: cleanup`.
4. Lỗi lan ra `try` ngoài; dòng `outer: next operation` bị bỏ qua.
5. `catch (IllegalStateException)` ngoài nhận lỗi và xử lý.
6. Nếu handler ngoài kết thúc bình thường, chương trình tiếp tục tại `after: continue`.

Không nên cho rằng khi lỗi đã được bắt ngoài, chương trình “quay lại” để chạy dòng `outer: next operation`. Vùng `try` ngoài đã hoàn tất bất thường tại vị trí cấu trúc trong.

## 4. Tình huống C: handler trong bắt lỗi rồi ném lại cùng đối tượng

```java
try {
    try {
        throw new IllegalArgumentException("quantity <= 0");
    } catch (IllegalArgumentException ex) {
        System.out.println("inner: record context");
        throw ex;
    }
} catch (IllegalArgumentException ex) {
    System.out.println("outer: " + ex.getMessage());
}
```

**Stdout:**

```text
inner: record context
outer: quantity <= 0
```

`throw ex;` ném lại **chính đối tượng ngoại lệ** đã bắt, do đó giữ kiểu runtime và `cause` sẵn có của nó. Handler ngoài nhìn thấy ngoại lệ vì handler trong **không kết thúc bình thường**.

Đây có thể là lựa chọn hợp lý khi phạm vi trong cần ghi nhận một thông tin hữu ích, thực hiện dọn dẹp không thể chuyển sang `finally`/`try-with-resources`, hoặc quyết định rằng việc phục hồi phải do tầng khác đảm nhận.

Tuy nhiên, một handler chỉ viết:

```java
catch (IllegalArgumentException ex) {
    throw ex;
}
```

thường là **dư thừa** nếu nó không bổ sung hành động hay hợp đồng nào. Không cần tạo thêm cấp `try-catch` chỉ để ngoại lệ đi qua.

## 5. Tình huống D: handler trong chuyển sang ngoại lệ mới có nguyên nhân

Có lúc tầng trong biết lỗi kỹ thuật, còn tầng ngoài cần lỗi ở cấp nghiệp vụ/điều phối:

```java
try {
    try {
        Integer.parseInt("abc");
    } catch (NumberFormatException cause) {
        throw new IllegalStateException(
                "cannot prepare order quantity", cause);
    }
} catch (IllegalStateException ex) {
    System.out.println(ex.getMessage());
    System.out.println(ex.getCause().getClass().getSimpleName());
}
```

**Stdout:**

```text
cannot prepare order quantity
NumberFormatException
```

Handler trong tạo một **đối tượng mới** `IllegalStateException` và gắn `NumberFormatException` ban đầu làm `cause`. Handler ngoài bắt ngoại lệ **mới** theo kiểu `IllegalStateException`, chứ không tự nhìn xuyên qua `cause` để bắt theo kiểu `NumberFormatException`.

Phân biệt:

| Thao tác trong handler | Ngoại lệ đi ra tầng ngoài | Thông tin giữ lại |
| --- | --- | --- |
| Xử lý và không ném lại | Không có ngoại lệ đó đi ra | Có thể trả trạng thái hợp lệ |
| `throw ex;` | Cùng đối tượng `ex` | Kiểu và cause gốc |
| `throw new X("context", ex);` | Đối tượng mới kiểu `X` | Cause liên kết tới `ex` |
| `throw new X("context");` | Đối tượng mới kiểu `X` | Có nguy cơ mất liên hệ với nguyên nhân ban đầu |

Chỉ đổi loại ngoại lệ khi **hợp đồng tầng trên** hoặc ngữ cảnh cần điều đó. Không nên bọc lặp lại ở mọi tầng thành nhiều lớp “operation failed” vô nghĩa.

## 6. Ví dụ Java 17+ hoàn chỉnh: bốn đường đi trong nested `try-catch`

Chương trình này chạy độc lập, không cần tệp hay kết nối bên ngoài. Lưu tên **`NestedTryCatchDemo.java`**:

```java
public class NestedTryCatchDemo {

    static void run(String mode) {
        System.out.println("case=" + mode);

        try {
            System.out.println("outer: enter");

            try {
                System.out.println("inner: enter");

                if ("format".equals(mode)) {
                    throw new NumberFormatException("bad integer");
                }
                if ("state".equals(mode)) {
                    throw new IllegalStateException("closed");
                }
                if ("convert".equals(mode)) {
                    throw new IllegalArgumentException("raw");
                }

                System.out.println("inner: success");

            } catch (NumberFormatException ex) {
                System.out.println("inner: format handled");

            } catch (IllegalArgumentException ex) {
                System.out.println("inner: wrapping argument");
                throw new IllegalStateException(
                        "invalid request", ex);

            } finally {
                System.out.println("inner: finally");
            }

            System.out.println("outer: after inner");

        } catch (IllegalStateException ex) {
            System.out.println(
                    "outer: state=" + ex.getMessage());
            String causeName = ex.getCause() == null
                    ? "none"
                    : ex.getCause().getClass().getSimpleName();
            System.out.println("outer: cause=" + causeName);

        } finally {
            System.out.println("outer: finally");
        }

        System.out.println("after: complete");
    }

    public static void main(String[] args) {
        run("ok");
        run("format");
        run("state");
        run("convert");
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 NestedTryCatchDemo.java
java NestedTryCatchDemo
```

**Stdout chính xác:**

```text
case=ok
outer: enter
inner: enter
inner: success
inner: finally
outer: after inner
outer: finally
after: complete
case=format
outer: enter
inner: enter
inner: format handled
inner: finally
outer: after inner
outer: finally
after: complete
case=state
outer: enter
inner: enter
inner: finally
outer: state=closed
outer: cause=none
outer: finally
after: complete
case=convert
outer: enter
inner: enter
inner: wrapping argument
inner: finally
outer: state=invalid request
outer: cause=IllegalArgumentException
outer: finally
after: complete
```

### Phân tích theo từng chế độ

**`ok` — không có lỗi:** chạy câu `inner: success`; không handler nào chạy; `finally` trong chạy; quay lại phần `try` ngoài để in `outer: after inner`; cuối cùng `finally` ngoài và dòng `after: complete`.

**`format` — handler trong xử lý được:** ném `NumberFormatException`, được `catch (NumberFormatException)` trong bắt. Nó **không lan đến `catch` ngoài**. Sau `finally` trong, phần `try` ngoài tiếp tục in `outer: after inner`.

**`state` — lỗi không được handler trong bắt:** ném `IllegalStateException`. Hai nhánh trong chỉ dành cho `NumberFormatException` và `IllegalArgumentException`, vì vậy không khớp. `finally` trong chạy, rồi `catch (IllegalStateException)` ngoài nhận lỗi. Do không có `cause`, in `none`. Dòng `outer: after inner` không chạy.

**`convert` — handler trong chuyển lỗi:** ném `IllegalArgumentException("raw")`; handler trong bắt rồi ném `IllegalStateException("invalid request", ex)`. `finally` trong chạy; handler ngoài bắt lỗi mới và in `IllegalArgumentException` từ `getCause()`. Dòng `outer: after inner` không chạy, vì cấu trúc trong kết thúc bất thường.

Tất cả bốn trường hợp đều in `outer: finally` và `after: complete` trong chương trình này, vì handler ngoài giải quyết được các loại lỗi hiện có và không ném lỗi mới.

### Bảng quyết định ngắn

| Mode | Lỗi xuất hiện trong | Handler xử lý cuối cùng | Phần sau cấu trúc trong thuộc `try` ngoài có chạy? |
| --- | --- | --- | --- |
| `ok` | Không có | Không áp dụng | Có |
| `format` | `try` trong | `catch NumberFormatException` trong | Có |
| `state` | `try` trong | `catch IllegalStateException` ngoài | Không |
| `convert` | `try` trong, sau đó wrapper từ handler trong | `catch IllegalStateException` ngoài | Không |

**Ý nghĩa của ranh giới:** nơi bắt lỗi nên tương ứng với **quyết định có thể thực hiện**. Trường hợp `format` có handler trong vì xử lý cục bộ được; `state` và `convert` trở thành trách nhiệm tầng ngoài.

## 7. Những ngoại lệ ném từ `catch` không được các `catch` anh em bắt

Một sai lầm phổ biến là tin rằng handler sau có thể xử lý lỗi do handler trước ném:

```java
try {
    throw new IllegalArgumentException("bad data");
} catch (IllegalArgumentException ex) {
    throw new IllegalStateException("conversion failed", ex);
} catch (IllegalStateException ex) {
    System.out.println("never reached for this new error");
}
```

Đây là một **đoạn minh họa**; mặc dù các nhánh là những kiểu hợp lệ, `catch (IllegalStateException)` không nhận lỗi từ `catch` đứng trước. Các `catch` cùng cấp chỉ được chọn cho ngoại lệ thoát ra từ **phần thân `try` tương ứng**, không bảo vệ thân của nhau.

Để bắt ngoại lệ mới từ handler bên trong, đặt **một `try-catch` ngoài**:

```java
try {
    try {
        throw new IllegalArgumentException("bad data");
    } catch (IllegalArgumentException ex) {
        throw new IllegalStateException("conversion failed", ex);
    }
} catch (IllegalStateException ex) {
    System.out.println("outer: " + ex.getMessage());
}
```

**Stdout:**

```text
outer: conversion failed
```

Một ranh giới xử lý được xác định bằng **vùng `try` nào đang bao quanh đoạn thực thi**, không chỉ bằng việc các `catch` tình cờ nằm gần nhau trong cùng tệp.

## 8. `finally` lồng nhau và thứ tự dọn dẹp

Khi rời một `try`, khối `finally` tương ứng thường được thực thi. Nếu ngoại lệ lan qua nhiều cấu trúc lồng nhau, quá trình dọn dẹp xảy ra từ phạm vi trong ra phạm vi ngoài:

```java
try {
    try {
        System.out.println("work");
        throw new IllegalStateException("failed");
    } finally {
        System.out.println("cleanup-inner");
    }
} catch (IllegalStateException ex) {
    System.out.println("handle-outer");
} finally {
    System.out.println("cleanup-outer");
}
```

**Stdout:**

```text
work
cleanup-inner
handle-outer
cleanup-outer
```

Ở đây không có handler trong; `finally` trong chạy trước, ngoại lệ được chuyển cho handler ngoài, sau đó `finally` ngoài chạy.

### `finally` không đảm bảo “không còn lỗi”

`finally` không tự bắt ngoại lệ: nếu không có handler phù hợp, lỗi vẫn lan ra ngoài. Ngoài ra, một `finally` **có thể ném lỗi khác**, làm che khuất lỗi đang chờ xử lý.

Ví dụ:

```java
try {
    try {
        throw new IllegalArgumentException("original");
    } finally {
        throw new IllegalStateException("cleanup");
    }
} catch (IllegalStateException ex) {
    System.out.println(ex.getMessage());
}
```

**Stdout:**

```text
cleanup
```

Ở đây lỗi `IllegalStateException("cleanup")` từ `finally` thay thế đường lan truyền của ngoại lệ ban đầu. Không có nghĩa lỗi `original` chưa từng xảy ra. Vì vậy không nên chủ động `return` hay `throw` từ `finally` nếu không thực sự muốn thay đổi đường đi của lỗi.

Với tài nguyên `AutoCloseable`, `try-with-resources` phù hợp hơn một chuỗi `finally` tự gọi `close()`: khi thân `try` và việc đóng đều thất bại, Java thường giữ lỗi của thân `try` là lỗi chính và đưa lỗi lúc đóng vào danh sách **suppressed exceptions** thay vì mất luôn lỗi chính.

## 9. `try-with-resources` có thể lồng trong `try-catch` ngoài

Xét phương thức sau, **chỉ minh họa**, cần đặt trong một lớp Java và có `Path` hợp lệ khi gọi:

```java
static String readFirstLine(java.nio.file.Path path)
        throws java.io.IOException {
    try (var reader =
                 java.nio.file.Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
```

Người gọi có thể đặt một ranh giới `try-catch` ngoài:

```java
try {
    String line = readFirstLine(path);
    System.out.println("first line: " + line);
} catch (java.io.IOException ex) {
    System.out.println("Cannot read input file");
}
```

Đoạn gọi cần biến `path` kiểu `java.nio.file.Path` trong cùng phạm vi. Lợi ích:

1. Tầng đọc chịu trách nhiệm **đóng reader** trong `try-with-resources`.
2. Tầng gọi chịu trách nhiệm **quyết định cách báo lỗi đọc tệp**.
3. Nếu lỗi xảy ra trong quá trình mở/đọc/đóng, ngoại lệ I/O có thể thoát ra cho caller xử lý theo hợp đồng.
4. Không cần để handler ngoài trực tiếp nắm và đóng tài nguyên nội bộ của tầng dưới.

Không nên coi `catch` ngoài là công cụ đảm bảo rollback mọi tác động: nếu đã ghi một phần tệp, cập nhật database hoặc gọi dịch vụ khác, cần chính sách khôi phục/giao dịch riêng.

### Handler bên trong có thể che mất thông tin gì?

Nếu tầng đọc viết:

```java
try (var reader =
             java.nio.file.Files.newBufferedReader(path)) {
    return reader.readLine();
} catch (java.io.IOException ex) {
    return "";
}
```

Đây là **một phần thân phương thức minh họa**, giả định phương thức trả `String`. Nếu chuỗi rỗng là dữ liệu hợp lệ, caller không phân biệt được **đọc thành công chuỗi rỗng** với **đọc thất bại**. Chỉ dùng fallback nếu hợp đồng thực sự chấp nhận và hành vi được tài liệu hóa. Nếu dữ liệu bắt buộc, để `IOException` lan lên thường đúng hơn.

## 10. Ranh giới xử lý theo tầng: thư viện, nghiệp vụ và giao tiếp

Trong một ứng dụng Java, `try-catch` lồng nhau thường xuất hiện tự nhiên trên **chuỗi lời gọi giữa các tầng**, chứ không nhất thiết tất cả nằm trong một phương thức.

Ví dụ đường gọi:

```text
controller.handleRequest()
  └─ service.placeOrder()
       └─ repository.save()
            └─ thao tác I/O ném IOException
```

Một cách phân chia trách nhiệm hợp lý:

- **Repository:** biết loại thao tác I/O thất bại, quản lý tài nguyên và có thể ném `IOException` hoặc một ngoại lệ phù hợp với hợp đồng lưu trữ.
- **Service:** biết ngữ cảnh nghiệp vụ. Chỉ bắt lỗi nếu có thể thử lại theo chính sách, thực hiện thao tác bù, hoặc chuyển lỗi sang khái niệm có ý nghĩa ở tầng nghiệp vụ. Khi đổi loại ngoại lệ, cần giữ `cause`.
- **Controller hoặc ranh giới tác vụ:** biết người gọi cần phản hồi gì. Nó có thể chuyển ngoại lệ sang trạng thái thất bại của yêu cầu, mã HTTP thích hợp, hoặc bản ghi lỗi tập trung.

**Không có quy tắc “mỗi tầng phải có đúng một `catch`”.** Nếu service không thể xử lý, để lỗi đi lên là hợp lý. Nếu controller cũng không xử lý được thì cần một ranh giới lỗi chung của framework/ứng dụng. Bắt ở mọi lớp rồi in cùng một stack trace chỉ làm log lặp và mất tính rõ ràng của trách nhiệm.

### Ví dụ Java 17+ chạy được: ranh giới tầng trong và tầng ngoài

Tệp **`ExceptionBoundaryDemo.java`**:

```java
import java.io.IOException;

public class ExceptionBoundaryDemo {

    static void repository(int id) throws IOException {
        if (id == 0) {
            throw new IOException("storage not available");
        }
        System.out.println("repository: saved " + id);
    }

    static void service(int id) throws IOException {
        try {
            repository(id);
        } catch (IOException cause) {
            throw new IOException(
                    "service: cannot save order " + id, cause);
        }
    }

    static void controller(int id) {
        System.out.println("request=" + id);

        try {
            service(id);
            System.out.println("response=OK");
        } catch (IOException ex) {
            System.out.println("response=FAILED");
            System.out.println("message=" + ex.getMessage());
            System.out.println(
                    "cause=" + ex.getCause().getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        controller(7);
        controller(0);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ExceptionBoundaryDemo.java
java ExceptionBoundaryDemo
```

**Stdout chính xác:**

```text
request=7
repository: saved 7
response=OK
request=0
response=FAILED
message=service: cannot save order 0
cause=IOException
```

Giải thích:

- `controller(7)` gọi service, repository hoàn tất bình thường; `catch` không được chạy.
- `controller(0)` gọi repository, gặp lỗi `IOException`. Handler trong service bắt lỗi đó, thêm ngữ cảnh order và ném **`IOException` mới chứa cause**.
- Handler ngoài controller nhận lỗi được service bọc, in thông điệp cấp service và kiểu nguyên nhân gốc.
- Vì controller đã bắt và không ném lại, nó chủ động trả trạng thái thất bại minh họa thay vì để exception chưa được xử lý.
- Đây là **mô hình phân tầng**, không chứng minh rằng mọi trường hợp phải bọc `IOException` bằng một `IOException` khác. Nếu thông tin ở service không hữu ích, để lỗi đi lên có thể dễ bảo trì hơn.

Trong hệ thống thật, thông điệp cho người dùng cuối và chi tiết log nội bộ nên tách riêng; không mặc định trả nguyên văn `getMessage()` chứa đường dẫn, cấu hình hay dữ liệu nhạy cảm.

## 11. Phạm vi của biến và tác động đến cách chia nested `try-catch`

Dấu ngoặc của mỗi `try`, `catch`, `finally` tạo **phạm vi khối (block scope)**. Ví dụ sau **cố ý không biên dịch**:

```java
try {
    int value = Integer.parseInt("12");
} catch (NumberFormatException ex) {
    System.out.println(value); // value không nằm trong scope.
}
```

Nếu cả đường thành công và đường xử lý lỗi cần truy cập một giá trị, nên thiết kế biến hoặc kiểu kết quả ở phạm vi thích hợp:

```java
int value;
try {
    value = Integer.parseInt(input);
} catch (NumberFormatException ex) {
    value = defaultValue;
}
System.out.println(value);
```

Đây là **mã minh họa**, giả định `input` và `defaultValue` đã được định nghĩa. Việc gán fallback ở `catch` làm biến được gán trên cả hai đường chạy và Java có thể kiểm tra `definite assignment`; nhưng fallback chỉ hợp lý khi là một phần của hợp đồng, không phải cách giấu lỗi.

Cũng chú ý biến `ex` chỉ có trong phạm vi handler khai báo nó. Đặt `try-catch` quá sâu đôi khi làm thông tin cần thiết không còn ở đúng phạm vi để báo lỗi; điều chỉnh thiết kế dữ liệu hoặc đưa xử lý lên tầng có ngữ cảnh thay vì dùng biến toàn cục.

## 12. Khi nào nên lồng, khi nào nên tách thành phương thức?

Lồng nhiều cấp `try` liên tục không tự làm code an toàn hơn. Một ranh giới có ích khi tầng đó có **mục tiêu xử lý khác biệt**.

**Nên lồng khi:**

- Một thao tác con có fallback độc lập, còn thao tác bao ngoài cần bảo vệ tính toàn vẹn của quy trình lớn hơn.
- Tầng trong cần đổi ngoại lệ kỹ thuật thành một lỗi cấp nghiệp vụ, tầng ngoài quyết định phản hồi.
- Tầng trong quản lý tài nguyên, tầng ngoài quản lý kết quả yêu cầu.
- Bạn cần phân biệt “lỗi đã phục hồi cục bộ” và “lỗi buộc hủy cả tác vụ”.

**Nên cân nhắc tách thay vì lồng sâu khi:**

- Có nhiều cấp `try-catch` cùng bắt một loại và chỉ ghi log rồi ném lại.
- Một phương thức chứa các handler trộn quá nhiều trách nhiệm nhập liệu, truy cập dữ liệu, mạng và giao diện.
- Không rõ đoạn nào được bảo vệ, hoặc không thể kiểm thử riêng từng chính sách phục hồi.
- Quá nhiều `finally` tự quản lý tài nguyên gây nguy cơ lỗi dọn dẹp che lỗi chính.

Một cấu trúc dễ đọc thường là: **phương thức nhỏ quản lý lỗi cục bộ**, **tầng gọi quyết định lỗi của thao tác lớn**. Ngoại lệ vẫn truyền qua chuỗi lời gọi khi không gặp handler.

## 13. Lưu ý với checked exception, multi-catch và lỗi unchecked

### Checked exception ở tầng trong

Nếu lời gọi trong `try` có thể ném checked `IOException`, phạm vi phù hợp phải bắt hoặc khai báo `throws` cho trường hợp chưa được xử lý:

```java
static void caller() throws java.io.IOException {
    try {
        read();
    } catch (java.io.FileNotFoundException ex) {
        System.out.println("missing file");
    }
}
```

Đây là **khung minh họa** nếu `read()` được định nghĩa với `throws IOException`. Bắt `FileNotFoundException` chỉ bao phủ một lớp con; các `IOException` khác có thể đi ra, vì vậy `caller` vẫn khai báo `throws IOException`.

Một cấu trúc `try` ngoài có `catch (IOException)` cũng có thể xử lý phần còn lại, miễn đường thực thi thật sự nằm trong vùng đó.

### Multi-catch trong nested `try`

`catch (IOException | NumberFormatException ex)` là cú pháp hợp lệ khi hai loại lỗi không có quan hệ cha/con, và hành động xử lý giống nhau. Nhưng `catch (NumberFormatException | IllegalArgumentException ex)` **không hợp lệ** vì `NumberFormatException extends IllegalArgumentException`.

Multi-catch không thay đổi cách xét phạm vi trong-ra-ngoài; nó chỉ gom nhiều kiểu vào **một handler** của một cấu trúc `try`.

### Lỗi unchecked

`catch (Exception)` ngoài có thể bắt nhiều loại lỗi, bao gồm `RuntimeException`, nhưng không bắt `Error`. Đừng dùng `catch (Throwable)` ở mọi cấp với mục đích “giữ ứng dụng sống”, vì `Error` có thể biểu thị điều kiện mà ứng dụng không thể phục hồi an toàn.

Một ranh giới tổng quát ở đầu yêu cầu hoặc đầu tác vụ có thể cần báo lỗi tập trung, nhưng vẫn phải giữ nguyên nhân, trạng thái thất bại và chính sách xử lý phù hợp.

## 14. Nested `try-catch` và thread: ranh giới không tự vượt qua luồng khác

Ví dụ:

```java
try {
    Thread worker = new Thread(() -> {
        throw new IllegalStateException("worker failed");
    });
    worker.start();
} catch (IllegalStateException ex) {
    System.out.println("caught in parent");
}
```

Đây là **đoạn minh họa**, không nên dùng để chứng minh stdout cố định vì hành vi uncaught handler tùy môi trường. Handler quanh `worker.start()` bảo vệ lời gọi `start()` trong thread gọi, **không tự bắt** ngoại lệ ném sau đó khi `Runnable` chạy trên stack của worker khác.

Tương tự, `worker.join()` chỉ chờ thread kết thúc, không tự ném lại lỗi đã xảy ra trong worker. Nếu cần truyền thành công/thất bại về nơi điều phối, dùng `Future`, `CompletableFuture` hoặc một cơ chế báo cáo đúng thiết kế.

Phạm vi `try-catch` là **phạm vi thực thi động của thread hiện tại**, không phải “mọi công việc bắt nguồn từ câu lệnh đã được gọi”. Đây là ranh giới quan trọng khi chuyển từ Java đồng bộ sang đa luồng.

## 15. Lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Bắt tất cả lỗi ở `try` trong rồi bỏ qua | Tầng ngoài không biết thao tác thất bại | Chỉ phục hồi khi có hợp đồng rõ; nếu không, lan truyền hoặc chuyển lỗi |
| Mong `catch` ngoài cụ thể hơn được ưu tiên trước `catch` trong kiểu cha | Hiểu sai thứ tự tìm handler | Xét vùng đang hoạt động từ trong ra ngoài trước |
| Nghĩ xử lý ở `catch` ngoài sẽ chạy tiếp phần còn lại của `try` ngoài | Bỏ sót đường thực thi bị gián đoạn | Đặt logic tiếp tục sau cấu trúc hoặc chủ động retry |
| Mong `catch` anh em bắt ngoại lệ ném từ một `catch` khác | Ngoại lệ mới thoát ra ngoài | Dùng `try-catch` ngoài hoặc tổ chức lại handler |
| Dùng `finally` ném lỗi mới không chủ đích | Có thể che nguyên nhân ban đầu | Dọn dẹp an toàn; ưu tiên `try-with-resources` |
| Lặp lại log và wrapper ở mọi cấp | Nhiễu log, chuỗi cause dài | Đặt ranh giới log/chuyển lỗi có trách nhiệm |
| Bọc lỗi nhưng không truyền `cause` | Mất thông tin chẩn đoán | Dùng constructor nhận `Throwable cause` |
| Bắt `IOException` trong cùng `try` không hề có nguồn lỗi checked tương thích | Có thể không biên dịch | Bắt quanh lời gọi thực tế có thể ném loại đó |
| Bao toàn bộ phương thức trong `try` quá rộng | Không xác định được nguồn lỗi, dễ trả thông báo sai | Thu hẹp theo thao tác và chính sách xử lý |
| Trông đợi handler bắt lỗi của thread được `start()` | Ngoại lệ ở stack khác | Dùng kênh báo cáo/quan sát lỗi của tác vụ |

## 16. Bài tập tự kiểm tra

**Bài 1 — handler trong có kiểu cha:**

```java
try {
    try {
        throw new NumberFormatException("x");
    } catch (IllegalArgumentException ex) {
        System.out.println("inner");
    }
} catch (NumberFormatException ex) {
    System.out.println("outer");
}
```

**Đáp án:** chỉ in `inner`. `NumberFormatException` thuộc `IllegalArgumentException` và đã được handler trong xử lý.

**Bài 2 — lỗi không khớp trong, có `finally`:**

```java
try {
    try {
        throw new IllegalStateException("broken");
    } catch (NumberFormatException ex) {
        System.out.println("wrong catch");
    } finally {
        System.out.println("cleanup");
    }
} catch (IllegalStateException ex) {
    System.out.println("handled outside");
}
```

**Đáp án:**

```text
cleanup
handled outside
```

Lỗi lan ra khỏi khối trong sau khi `finally` thực thi.

**Bài 3 — lỗi được chuyển trong `catch`:**

```java
try {
    try {
        throw new IllegalArgumentException("bad");
    } catch (IllegalArgumentException ex) {
        throw new IllegalStateException("wrapped", ex);
    }
} catch (IllegalStateException ex) {
    System.out.println(ex.getCause().getMessage());
}
```

**Đáp án:** in `bad`. Lỗi ngoài là `IllegalStateException`, `cause` là ngoại lệ `IllegalArgumentException` ban đầu.

**Bài 4 — câu lệnh sau cấu trúc trong có chạy?**

Nếu `try` trong ném `IllegalStateException` không được handler trong bắt, handler ngoài bắt được và kết thúc bình thường, câu lệnh **nằm trong `try` ngoài, ngay sau cấu trúc trong** có chạy hay không?

**Không.** Cấu trúc trong hoàn tất bất thường, khiến phần `try` ngoài bị gián đoạn; sau handler ngoài, luồng tiếp tục sau cấu trúc `try-catch` ngoài (nếu nó hoàn tất bình thường).

**Bài 5 — lỗi trong `finally`:**

Nếu phần `try` trong đang ném ngoại lệ A, nhưng `finally` trong lại ném ngoại lệ B, handler ngoài sẽ nhận ngoại lệ nào theo quy tắc hoàn tất của Java?

**Thông thường là B.** Đường hoàn tất bất thường do `finally` mới có thể thay thế A. Với tài nguyên `AutoCloseable`, `try-with-resources` có cơ chế suppressed exceptions giúp lưu lỗi khi đóng tài nguyên, nên không thể suy luận mọi lỗi trong `finally` đều được giữ tự động.

**Bài 6 — lỗi của thread khác:**

Có thể bao `new Thread(task).start()` trong `try-catch` để bắt `RuntimeException` mà chính `task.run()` ném sau đó không?

**Không tự động.** `task.run()` chạy trong thread mới, không nằm trên ngăn xếp lời gọi của thread thực hiện `start()`.

## 17. Checklist thiết kế ranh giới xử lý

Khi chuẩn bị thêm một tầng `try-catch`, hãy tự hỏi:

1. **Tầng này sở hữu thao tác nào?** Xác định câu lệnh và chuỗi lời gọi cần bảo vệ; tránh bắt nhầm từ phần mã không liên quan.
2. **Tầng trong có sửa được lỗi không?** Nếu có chính sách phục hồi được kiểm thử, xử lý tại đây. Nếu không, đừng bắt chỉ để bỏ qua.
3. **Lỗi còn lại đi đâu?** Nếu không có handler trong khớp, nó sẽ đi ra phạm vi ngoài sau dọn dẹp.
4. **Có chuyển lỗi sang loại mới không?** Nếu có, kiểu handler ngoài phải tương thích với **đối tượng mới**, và `cause` nên giữ lỗi gốc.
5. **Sau khi handler chạy thì chương trình tiếp tục ở đâu?** Không giả định các câu lệnh đã bị bỏ qua trong `try` sẽ chạy bù.
6. **`finally` và tài nguyên có an toàn không?** Giảm việc ném lỗi/`return` trong `finally`; ưu tiên `try-with-resources` khi phù hợp.
7. **Checked exception đã được khai báo hoặc bắt đủ chưa?** Một handler lớp con không luôn bao phủ toàn bộ loại cha được khai báo bởi lời gọi.
8. **Có đổi thread không?** Nếu có, đặt cơ chế nhận kết quả/lỗi ở ranh giới đồng thời phù hợp.
9. **Có bị lặp logging và wrapper không?** Chỉ thêm tầng xử lý nếu tầng đó có hành động hoặc ngữ cảnh mới.
10. **Đã kiểm thử từng nhánh chưa?** Ít nhất cần đường thành công, lỗi bắt trong, lỗi lan ngoài, lỗi được wrap và trường hợp dọn dẹp.

**Kết luận:** `try-catch` lồng nhau không phải “nhiều lớp bảo hiểm tự động”, mà là cách diễn đạt **ranh giới trách nhiệm**. Handler trong được xét trước đối với lỗi thuộc phạm vi của nó; nếu nó không khớp hoặc ném lỗi mới, tầng ngoài có thể xử lý. Thiết kế tốt giúp lỗi có đường đi rõ ràng, tài nguyên được quản lý ở đúng nơi và caller nhận được thất bại thật thay vì trạng thái thành công giả.