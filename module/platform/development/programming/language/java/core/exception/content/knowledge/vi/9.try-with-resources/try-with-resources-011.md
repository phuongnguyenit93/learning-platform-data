# Tài nguyên được đóng khi `return` hoặc thoát đột ngột trong `try-with-resources`

Trong Java, `try-with-resources` quản lý vòng đời của các đối tượng `AutoCloseable` theo một **phạm vi thực thi**. Khi chương trình rời phạm vi này, Java tự gọi `close()` trên các tài nguyên đã được khởi tạo thành công, kể cả nếu phần thân `try` không chạy đến dấu ngoặc nhọn đóng.

Các đường thoát đáng chú ý gồm **`return`**, **`throw`**, **`break`** và **`continue`**. Điều đó không chỉ có nghĩa “Java cố đóng tài nguyên”: trình tự đóng, ngoại lệ phát sinh từ `close()`, và loại kết quả cuối cùng được gửi tới caller đều có quy tắc cụ thể.

**Quy tắc cốt lõi:**

- `return` trong phần thân `try-with-resources` **không bỏ qua `close()`**. Tài nguyên được đóng trước khi caller nhận kết quả.
- Nếu phần thân ném ngoại lệ, Java vẫn đóng các tài nguyên đã mở; nếu `close()` cũng ném, lỗi đóng thường được **suppressed** dưới ngoại lệ chính.
- Nếu phần thân định `return` nhưng `close()` ném lỗi, caller **có thể nhận ngoại lệ thay vì nhận giá trị trả về**.
- Với nhiều resource, Java khởi tạo theo thứ tự khai báo và đóng theo **thứ tự ngược**.
- Không được suy ra rằng resource chắc chắn đã đóng trong mọi cách process/JVM bị kết thúc cưỡng bức; đây là cơ chế gắn với luồng thực thi Java, không phải cam kết vượt qua mọi sự cố hệ thống.

## 1. Cú pháp và hợp đồng của `AutoCloseable`

Dạng cơ bản:

```java
try (Resource resource = openResource()) {
    use(resource);
}
```

Đây là **khung minh họa**, yêu cầu `Resource` triển khai `AutoCloseable` và các phương thức được định nghĩa. `resource` được khai báo trong *resource specification*, là phần nằm giữa cặp ngoặc tròn sau `try`.

Interface `java.lang.AutoCloseable` định nghĩa phương thức `close()`. Nhiều API Java như `InputStream`, `Reader`, `Writer`, `Scanner` và `java.sql.Connection` cung cấp các tài nguyên tương thích. Khi dùng `try-with-resources`:

1. Java đánh giá biểu thức khởi tạo resource.
2. Nếu khởi tạo thành công, resource được đăng ký để đóng khi rời phạm vi.
3. Phần thân `try` được thực thi.
4. Khi chuẩn bị rời khối, Java gọi `close()` cho những resource cần đóng.
5. Sau quá trình đóng, điều khiển chuyển tới `catch`, `finally` hoặc caller theo lý do hoàn tất cuối cùng.

Bạn có thể kết hợp với `catch` và `finally`:

```java
try (Resource resource = openResource()) {
    use(resource);
} catch (SomeException ex) {
    handle(ex);
} finally {
    afterAttempt();
}
```

Đây cũng là **khung minh họa**, không phải chương trình Java độc lập. Một điểm quan trọng: với `catch`/`finally` gắn cùng cấu trúc, bước **đóng resource xảy ra trước khi handler hoặc `finally` ấy chạy**.

Không cần tự gọi `resource.close()` trong `finally` chỉ để đảm bảo đóng. Làm vậy dễ dẫn đến đóng lặp và khó xử lý lỗi cleanup.

## 2. “Thoát đột ngột” (*abrupt completion*) nghĩa là gì?

Một câu lệnh hoặc khối Java có thể **hoàn tất bình thường** (*normal completion*) hoặc **hoàn tất bất thường** (*abrupt completion*).

Ví dụ các lý do hoàn tất bất thường:

| Nguyên nhân | Ví dụ | Hệ quả điều khiển |
| --- | --- | --- |
| `return` | `return result;` | Chuẩn bị rời phương thức |
| `throw` | `throw new IOException(...);` | Chuẩn bị lan truyền ngoại lệ |
| `break` | `break;` | Chuẩn bị thoát vòng lặp/`switch` phù hợp |
| `continue` | `continue;` | Chuẩn bị chuyển sang lần lặp kế |
| Ngoại lệ từ lời gọi | `readLine()` ném `IOException` | Câu lệnh hiện tại hoàn tất bất thường |

`try-with-resources` được thiết kế để **đóng tài nguyên trên những đường thoát đó**. Nó không đợi chương trình thực thi đến dấu `}` của phần thân theo đường thông thường mới gọi `close()`.

Ví dụ:

```java
static String firstLine(java.nio.file.Path path)
        throws java.io.IOException {
    try (var reader = java.nio.file.Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
```

Đây là một **phương thức minh họa hợp lệ khi đặt trong lớp Java**. `reader.readLine()` được đánh giá để chuẩn bị kết quả, nhưng trước khi caller nhận chuỗi `String`, Java đóng reader. Nếu việc đọc hoặc đóng ném `IOException`, phương thức có thể ném ngoại lệ thay vì trả kết quả.

**Không nhầm:** một resource còn nằm trong scope của khối khác không có nghĩa còn mở sau khi khối quản lý của nó đã kết thúc. Khi dùng `try (existingResource)` với biến khai báo bên ngoài, tên biến thậm chí có thể vẫn dùng được, nhưng đối tượng đã được đóng.

## 3. `return` trong phần thân: đóng trước khi phương thức trả kết quả

Xem:

```java
static int calculate() {
    try (TrackedResource resource = new TrackedResource()) {
        return 42;
    }
}
```

Đây là **mã minh họa**, giả định `TrackedResource implements AutoCloseable` và `close()` có hợp đồng phù hợp.

Diễn biến logic:

```text
mở resource
    ↓
vào thân try
    ↓
đánh giá biểu thức return 42
    ↓
Java gọi resource.close()
    ↓
nếu close hoàn tất bình thường
    ↓
caller nhận 42
```

Nếu `close()` ném một ngoại lệ không được xử lý, đường đi thay đổi: `return 42` có thể bị **thay bằng ngoại lệ từ `close()`**. Vì vậy, nói “gặp `return` thì resource vẫn được đóng” là đúng, nhưng chưa đầy đủ. Phải hỏi tiếp “`close()` có thành công không?” để biết caller thật sự nhận gì.

### Giá trị `return` được tính trước khi đóng

Với biểu thức trả về:

```java
try (Resource resource = openResource()) {
    return compute(resource);
}
```

thứ tự về mặt ngữ nghĩa là **tính `compute(resource)`**, chuẩn bị giá trị, rồi đóng resource, sau đó mới hoàn tất việc trả nếu không có một lý do kết thúc khác.

Nếu `compute(resource)` ném ngoại lệ trước khi có kết quả, Java vẫn đóng resource và tiếp tục xử lý đường ngoại lệ.

Điều này cũng giải thích vì sao trả về **giá trị độc lập** như `int`, `String` đã đọc hoặc DTO đã vật hóa thường phù hợp hơn trả về một đối tượng còn cần resource đang mở. Đừng trả ra một `Stream` hoặc iterator đọc lười nếu nguồn dữ liệu bị đóng trước khi caller sử dụng.

## 4. Ví dụ Java 17+ hoàn chỉnh: `return`, `throw`, `break`, `continue`

Để quan sát chính xác trình tự mà không phụ thuộc file hoặc hệ điều hành, dùng một resource giả lập tự in khi mở và đóng.

Lưu tệp **`ResourceExitFlowDemo.java`**:

```java
public class ResourceExitFlowDemo {

    static final class Trace implements AutoCloseable {
        private final String name;

        Trace(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    static int returnCase() {
        System.out.println("CASE return");

        try (Trace first = new Trace("A");
             Trace second = new Trace("B")) {
            System.out.println("body: prepare return 7");
            return 7;
        }
    }

    static void throwCase() {
        System.out.println("CASE throw");

        try (Trace resource = new Trace("T")) {
            System.out.println("body: throw");
            throw new IllegalArgumentException("bad request");
        } catch (IllegalArgumentException ex) {
            System.out.println("catch: " + ex.getMessage());
        }
    }

    static void breakCase() {
        System.out.println("CASE break");

        for (int i = 0; i < 2; i++) {
            try (Trace resource = new Trace("break-" + i)) {
                System.out.println("body: break at " + i);
                break;
            }
        }

        System.out.println("after break loop");
    }

    static void continueCase() {
        System.out.println("CASE continue");

        for (int i = 0; i < 2; i++) {
            try (Trace resource = new Trace("continue-" + i)) {
                System.out.println("body: continue at " + i);
                continue;
            }
        }

        System.out.println("after continue loop");
    }

    public static void main(String[] args) {
        System.out.println("returned=" + returnCase());
        throwCase();
        breakCase();
        continueCase();
    }
}
```

Biên dịch/chạy với **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 ResourceExitFlowDemo.java
java ResourceExitFlowDemo
```

**Stdout chính xác:**

```text
CASE return
open A
open B
body: prepare return 7
close B
close A
returned=7
CASE throw
open T
body: throw
close T
catch: bad request
CASE break
open break-0
body: break at 0
close break-0
after break loop
CASE continue
open continue-0
body: continue at 0
close continue-0
open continue-1
body: continue at 1
close continue-1
after continue loop
```

### Phân tích các nhánh

**`returnCase()`:**

- Mở A rồi B theo thứ tự khai báo.
- Phần thân chạy `return 7`.
- Java đóng B rồi A (**đảo thứ tự khai báo**).
- Sau khi cả hai `close()` hoàn tất bình thường, caller mới in `returned=7`.

Nếu `return` làm bỏ qua việc đóng, hai dòng `close` sẽ không xuất hiện trước `returned=7`. Ví dụ chứng minh điều ngược lại.

**`throwCase()`:**

- Phần thân ném `IllegalArgumentException`.
- Trước khi handler `catch` gắn cùng cấu trúc xử lý ngoại lệ, Java gọi `close T`.
- Handler in `catch: bad request`, nghĩa là nó nhận được ngoại lệ từ phần thân sau khi tài nguyên đã được đóng.

**`breakCase()`:**

- Vòng lặp bắt đầu ở `i=0`, resource `break-0` được tạo.
- `break` yêu cầu rời vòng lặp, nhưng Java **đóng resource trước**.
- Không chạy lần lặp `i=1`; sau đó in `after break loop`.

**`continueCase()`:**

- Ở mỗi lần lặp, resource được mở trong `try` riêng của lần đó.
- `continue` yêu cầu chuyển ngay đến bước tiếp theo của vòng lặp, nhưng trước hết resource hiện tại được đóng.
- Do đó thứ tự luôn là mở → dùng → đóng cho từng lần lặp, rồi mới chuyển sang lần kế tiếp.

Cả hai kiểu thoát vòng lặp đều kích hoạt việc đóng. Tuy vậy, nếu `close()` ném ngoại lệ, đường `break` hoặc `continue` **có thể bị thay bằng đường ném ngoại lệ**, thay vì chuyển tới đích dự kiến.

## 5. Khi phần thân ném ngoại lệ, `close()` chạy trước handler ngoài

Với:

```java
try (var reader = java.nio.file.Files.newBufferedReader(path)) {
    throw new IllegalArgumentException("invalid content");
} catch (IllegalArgumentException ex) {
    System.out.println("caught: " + ex.getMessage());
}
```

Đây là **đoạn minh họa**, cần biến `path` kiểu `Path`, và cần xử lý/khai báo checked `IOException` phát sinh khi mở/đóng reader. Phần thân ném một ngoại lệ unchecked, nhưng điều đó không bỏ qua thao tác `reader.close()`.

Với `try-with-resources` gắn `catch`, cơ chế tương đương về mặt trực giác:

```text
mở resource
  → chạy thân try
  → ngoại lệ xuất hiện
  → đóng resource
  → chọn catch của cấu trúc
  → xử lý hoặc tiếp tục lan truyền
```

Điều này có ích khi `catch` ghi log lỗi sau một lần xử lý: resource được đăng ký trong cấu trúc đã qua bước đóng trước khi handler chạy. Nhưng **không** được kết luận rằng việc đóng luôn thành công; nếu `close()` thất bại, cần kiểm tra exception hoặc suppressed exceptions.

### Nếu handler ở tầng ngoài, có khác không?

Giả sử:

```java
try {
    try (Resource resource = openResource()) {
        doWork(resource);
    }
} catch (RuntimeException ex) {
    recoverOrReport(ex);
}
```

Đây là **khung minh họa**. Khi ngoại lệ unchecked thoát khỏi `try` trong, resource được đóng trước khi điều khiển chuyển đến handler bên ngoài. Phạm vi xử lý lồng nhau không làm mất cơ chế tự động đóng, vì mỗi `try-with-resources` bảo vệ vòng đời tài nguyên của chính nó.

## 6. Nếu `close()` ném lỗi khi phần thân định `return`

Đây là trường hợp dễ gây hiểu lầm:

```java
static int compute() {
    try (FailingResource resource = new FailingResource()) {
        return 123;
    }
}
```

Giả sử `FailingResource.close()` ném `IllegalStateException("close failed")`. Khi ấy:

1. Phần thân đã đánh giá `123` và chuẩn bị trả.
2. `close()` được gọi theo cơ chế `try-with-resources`.
3. `close()` ném `IllegalStateException`.
4. Phương thức **không hoàn tất bằng `return 123`** mà kết thúc bằng ngoại lệ từ `close()`, trừ khi ngoại lệ được xử lý trong một handler bao ngoài phù hợp.

Đây không phải việc Java “quên trả kết quả”, mà là quy tắc ưu tiên **hoàn tất bất thường mới** của việc đóng so với đường trả giá trị đang chờ.

**Vì sao không có suppressed exception trong trường hợp này?** Phần thân `try` mới chuẩn bị `return`, chưa ném một ngoại lệ chính nào. Khi `close()` là nguồn ngoại lệ duy nhất, lỗi đóng trở thành ngoại lệ chính được quan sát.

So sánh:

| Trạng thái phần thân | Trạng thái `close()` | Caller thường quan sát |
| --- | --- | --- |
| `return 123` | Bình thường | Nhận `123` |
| `return 123` | Ném `Eclose` | Nhận `Eclose` thay vì `123` |
| Hoàn tất bình thường | Ném `Eclose` | Nhận `Eclose` |
| Ném `Ebody` | Bình thường | Nhận `Ebody` |
| Ném `Ebody` | Ném `Eclose` | Nhận `Ebody`; `Eclose` là suppressed |

Phần cuối bảng là điểm nổi bật của `try-with-resources` so với một `finally` thủ công có câu `throw` mới.

## 7. Khi cả phần thân và `close()` cùng ném lỗi: suppressed exceptions

Giả sử phần thân ném `IllegalArgumentException("body failed")` rồi quá trình đóng resource ném `IllegalStateException("close failed")`.

Java cần bảo toàn **lỗi chính của thao tác** và vẫn ghi nhận sự cố **dọn dẹp**. Với `try-with-resources`, trong tình huống thông thường:

- Ngoại lệ từ phần thân được giữ làm **ngoại lệ chính**.
- Ngoại lệ từ `close()` được thêm vào danh sách `getSuppressed()` của ngoại lệ chính.
- Handler bao ngoài bắt ngoại lệ chính; nếu muốn điều tra lỗi đóng, xem mảng do `getSuppressed()` trả về.

Đây là cách Java tránh việc một lỗi cleanup vô tình **ghi đè hoàn toàn** lỗi gốc.

### `getSuppressed()` khác `getCause()`

`Throwable.getCause()` biểu thị **chuỗi nguyên nhân** thường được lập trình viên truyền qua constructor `new X(message, cause)`. `Throwable.getSuppressed()` biểu thị **các ngoại lệ phụ đã được gắn vào ngoại lệ chính**, điển hình là lỗi đóng tài nguyên.

Một ngoại lệ chính có thể có cả `cause` và nhiều suppressed exceptions; đây là hai quan hệ khác nhau.

Trong trường hợp `try-with-resources` tự quản lý lỗi đóng, đừng chỉ nhìn `ex.getCause()` rồi khẳng định không có lỗi phụ. Cần xem `ex.getSuppressed()` nếu tình trạng cleanup quan trọng.

### Có bao nhiêu lỗi đóng được lưu lại?

Với nhiều resource, mỗi `close()` được gọi theo thứ tự ngược, kể cả khi một `close()` trước đó ném lỗi. Nếu phần thân đã ném ngoại lệ chính và nhiều lần đóng đều lỗi, các lỗi đóng được thêm vào danh sách suppressed.

Ví dụ khai báo A rồi B, phần thân ném E, cả B.close và A.close ném lỗi:

```text
mở A
mở B
thân try ném E
B.close() ném EB
A.close() ném EA
caller bắt E
E.getSuppressed() thường có [EB, EA]
```

Ở đây `[EB, EA]` là ký hiệu giải thích thứ tự, không phải một câu lệnh Java. Đầu ra chính xác sẽ được kiểm chứng bằng chương trình kế tiếp.

## 8. Ví dụ Java 17+ hoàn chỉnh: return bị thay và lỗi đóng bị suppressed

Lưu tệp **`CloseFailureFlowDemo.java`**:

```java
public class CloseFailureFlowDemo {

    static final class Tracked implements AutoCloseable {
        private final String name;
        private final boolean failsOnClose;

        Tracked(String name, boolean failsOnClose) {
            this.name = name;
            this.failsOnClose = failsOnClose;
            System.out.println("open " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
            if (failsOnClose) {
                throw new IllegalStateException(
                        "close failed: " + name);
            }
        }
    }

    static int returnThenCloseFails() {
        System.out.println("CASE return-close-error");

        try (Tracked resource = new Tracked("R", true)) {
            System.out.println("body: return 9");
            return 9;
        }
    }

    static void bodyAndCloseFail() {
        System.out.println("CASE body-and-close-errors");

        try (Tracked first = new Tracked("A", true);
             Tracked second = new Tracked("B", true)) {
            System.out.println("body: throw");
            throw new IllegalArgumentException("work failed");
        } catch (IllegalArgumentException ex) {
            System.out.println("primary: " + ex.getMessage());
            System.out.println("suppressed count: "
                    + ex.getSuppressed().length);
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println(
                        "suppressed: " + suppressed.getMessage());
            }
        }
    }

    static void closeOnlyFailure() {
        System.out.println("CASE close-only-error");

        try (Tracked resource = new Tracked("C", true)) {
            System.out.println("body: normal");
        } catch (IllegalStateException ex) {
            System.out.println("caught: " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println(
                    "returned=" + returnThenCloseFails());
        } catch (IllegalStateException ex) {
            System.out.println("caught: " + ex.getMessage());
            System.out.println("suppressed count: "
                    + ex.getSuppressed().length);
        }

        bodyAndCloseFail();
        closeOnlyFailure();
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac -encoding UTF-8 CloseFailureFlowDemo.java
java CloseFailureFlowDemo
```

**Stdout chính xác:**

```text
CASE return-close-error
open R
body: return 9
close R
caught: close failed: R
suppressed count: 0
CASE body-and-close-errors
open A
open B
body: throw
close B
close A
primary: work failed
suppressed count: 2
suppressed: close failed: B
suppressed: close failed: A
CASE close-only-error
open C
body: normal
close C
caught: close failed: C
```

### Phân tích ba đường lỗi

**`returnThenCloseFails()`:** phần thân chuẩn bị trả `9` nhưng `R.close()` ném `IllegalStateException`. Lời gọi bên trong biểu thức `"returned=" + returnThenCloseFails()` không hoàn tất bình thường, nên **không in dòng `returned=9`**. Handler bên ngoài bắt lỗi đóng. Vì phần thân không ném lỗi chính, danh sách suppressed rỗng.

**`bodyAndCloseFail()`:** phần thân ném `IllegalArgumentException("work failed")`. Hai resource đã mở được đóng **B trước, A sau**. Cả hai `close()` ném `IllegalStateException`; Java gắn các lỗi này vào ngoại lệ chính. Handler bắt lỗi chính và in hai suppressed exceptions đúng thứ tự B, A.

**`closeOnlyFailure()`:** thân `try` hoàn tất bình thường nhưng `close()` ném `IllegalStateException`. Handler nhận chính ngoại lệ đóng. Điều này xác nhận `try-with-resources` không mặc nhiên bỏ qua lỗi cleanup.

Trong hệ thống thật, cần lựa chọn chính sách khi đóng thất bại: log, báo lỗi tác vụ, retry ở tầng phù hợp hoặc đánh dấu dữ liệu chưa chắc đã được ghi hoàn chỉnh. Không nên trả thành công giả chỉ vì phần thân `try` đã in “done”.

## 9. `break` và `continue` vẫn đóng tài nguyên

Hai lệnh này không rời toàn bộ phương thức, nhưng chúng **rời phạm vi `try`** khi chuyển điều khiển ra ngoài phần thân. Vì vậy `try-with-resources` vẫn thực hiện đóng.

Ví dụ ở mức cấu trúc:

```java
for (int i = 0; i < 10; i++) {
    try (Resource resource = open(i)) {
        if (shouldSkip(i)) {
            continue;
        }

        if (shouldStop(i)) {
            break;
        }

        use(resource);
    }
}
```

Đây là khung minh họa, cần định nghĩa `Resource`, `open`, `shouldSkip`, `shouldStop` và `use`. Đường đi:

- Nếu `shouldSkip(i)` là `true`, resource của lần lặp hiện tại được đóng **trước khi** vòng lặp bắt đầu lần kế.
- Nếu `shouldStop(i)` là `true`, resource được đóng **trước khi** thoát khỏi vòng lặp.
- Nếu `use(resource)` hoàn tất bình thường, resource vẫn được đóng khi hết thân `try`.
- Nếu `use(resource)` ném ngoại lệ, resource vẫn được đóng trong quá trình thoát bất thường.

**Lưu ý:** nếu `close()` phát sinh lỗi trên đường `continue` hoặc `break`, quá trình chuyển điều khiển có thể bị thay bằng ngoại lệ chưa được bắt. Vì thế vòng lặp có thể không chuyển đến nơi bạn dự đoán nếu cleanup thất bại.

### `break` có nhãn và `continue` có nhãn

Java có `break label;` và `continue label;`. Khi lệnh chuyển điều khiển ra khỏi một hoặc nhiều phạm vi `try-with-resources`, các resource của những phạm vi bị rời được đóng theo quy tắc tương ứng. Nếu một lệnh có nhãn **không rời khỏi một phạm vi `try-with-resources` cụ thể**, tài nguyên của phạm vi đó chưa bị đóng chỉ vì có lệnh chuyển điều khiển.

Do đó cần xét **những scope nào thực sự bị thoát**, không chỉ dựa vào việc có từ khóa `break`/`continue` xuất hiện trong mã.

## 10. `return` trong `catch` hoặc `finally` ngoài có ảnh hưởng gì?

Xét:

```java
static int recover() {
    try (Tracked resource = openTracked()) {
        throw new IllegalArgumentException("bad input");
    } catch (IllegalArgumentException ex) {
        return 0;
    } finally {
        System.out.println("request finished");
    }
}
```

Đây là khung minh họa với kiểu `Tracked` và `openTracked()` phù hợp. Trình tự:

1. Mở resource và chạy thân `try`.
2. Phần thân ném `IllegalArgumentException`.
3. Resource được đóng.
4. Handler `catch` quyết định `return 0`.
5. `finally` cùng cấu trúc thực thi.
6. Nếu `finally` hoàn tất bình thường, caller nhận `0`.

Nếu `finally` **cũng `return` hoặc `throw`**, nó có thể thay thế quyết định của `catch`. Đó là quy tắc hoàn tất bất thường của `finally`, **khác** cơ chế resource tự động đóng, nhưng có thể xảy ra trong cùng một cấu trúc.

Không nên dùng `finally` để trả fallback hoặc nuốt lỗi. Đặt chính sách phục hồi ở `catch` thích hợp; để `try-with-resources` giải quyết vòng đời resource.

## 11. Ngoại lệ trong quá trình khởi tạo resource cũng dẫn tới đóng những resource đã mở

Không phải mọi trường hợp thoát bất thường đều bắt đầu từ phần thân `try`. Ngay **initializer** trong danh sách resource cũng có thể thất bại:

```java
try (Resource first = openFirst();
     Resource second = openSecond()) {
    doWork(first, second);
}
```

Đây là đoạn minh họa. Nếu `openFirst()` thành công, nhưng `openSecond()` ném ngoại lệ:

- `first` đã được khởi tạo thành công, nên Java gọi `first.close()`.
- `second` chưa được khởi tạo thành công, nên không có resource `second` hợp lệ để gọi `close()`.
- Phần thân `doWork(first, second)` **không chạy**.
- Ngoại lệ từ `openSecond()` là lỗi chính.
- Nếu `first.close()` cũng ném lỗi, lỗi đóng có thể được gắn **suppressed** dưới lỗi khởi tạo.

Với tài nguyên có initializer trả `null`, Java **không gọi `close()` trên `null`** theo cơ chế đóng tài nguyên. Tuy nhiên, việc sử dụng biến resource `null` trong thân `try` có thể phát sinh `NullPointerException` như các lời gọi Java khác.

### Ví dụ kiểm chứng bằng lập luận

```text
open A thành công
open B ném "init B failed"
close A
catch thấy "init B failed"
```

Nếu `close A` cũng ném, ngoại lệ đóng được ghi nhận như lỗi phụ theo quy tắc suppression; không làm cho thân `try` đã bị bỏ qua bắt đầu chạy.

Vì vậy, `try-with-resources` còn xử lý cả **rò rỉ tài nguyên khi một phần công đoạn khởi tạo đã thành công**.

## 12. `try-with-resources` và `try-finally` tự viết khác nhau khi cả hai lỗi

Xét mã thủ công:

```java
Resource resource = openResource();
try {
    doWork(resource);
} finally {
    resource.close();
}
```

Đây là đoạn minh họa, yêu cầu các khai báo/phương thức thích hợp. Về đường đóng bình thường, nó có vẻ tương tự `try-with-resources`. Nhưng khi:

- `doWork(resource)` ném ngoại lệ `Ebody`;
- `resource.close()` trong `finally` ném ngoại lệ `Eclose`;

thì một `throw` mới từ `finally` có thể **che mất `Ebody`**. Không có cơ chế tự động thêm `Eclose` vào `Ebody.getSuppressed()` chỉ vì `close()` được viết trong `finally` thông thường.

Với `try-with-resources`:

```java
try (Resource resource = openResource()) {
    doWork(resource);
}
```

Java biên dịch cấu trúc theo cơ chế quản lý lỗi chính và lỗi đóng, giữ `Ebody` làm ngoại lệ chính và có thể gắn `Eclose` vào danh sách suppressed. Đây là lý do **nên ưu tiên `try-with-resources` cho đối tượng `AutoCloseable`** thay vì tự viết đóng trong `finally`.

### Có nên tự gọi `close()` trong thân `try` không?

Nếu tự gọi `resource.close()` trong thân và sau đó để `try-with-resources` tự đóng lần nữa, bạn có nguy cơ **đóng hai lần**. Không phải mọi `AutoCloseable` đều cam kết hành vi đóng lặp vô hại. Hãy thiết kế ownership rõ ràng; đa số trường hợp chỉ để Java gọi `close()` khi rời phạm vi.

### `close()` ném checked exception

`AutoCloseable.close()` có thể khai báo `throws Exception`. Loại checked exception cần xử lý được kiểm tra theo **kiểu tĩnh của resource**. Nếu gọi qua một biến kiểu `AutoCloseable`, một phương thức có thể cần `throws Exception`; nếu dùng `BufferedReader`, các checked exception liên quan thường ở nhánh `IOException`.

Vì vậy đoạn:

```java
static void use(AutoCloseable resource) throws Exception {
    try (resource) {
        System.out.println("using resource");
    }
}
```

là **phương thức minh họa theo Java 9+**, sử dụng tham số `resource` không bị gán lại và có chữ ký `throws Exception` để đáp ứng checked exception có thể xảy ra khi đóng. Nó cũng minh họa rằng sử dụng biến khai báo bên ngoài trong resource specification là hợp lệ khi tham số *effectively final*.

## 13. Thứ tự đóng khi có nhiều resource và thoát bất thường

Với:

```java
try (R a = openA();
     R b = openB();
     R c = openC()) {
    return calculate(a, b, c);
}
```

đây là khung minh họa với các lớp/hàm giả định. Java mở các resource theo **A → B → C** và đóng theo **C → B → A** khi rời phạm vi.

Nếu `calculate` trả bình thường, Java chuẩn bị trả giá trị nhưng vẫn đóng cả ba resource trước khi caller nhận.

Nếu `calculate` ném ngoại lệ `E`, Java vẫn gọi ba `close()`; các lỗi đóng có thể được gắn suppressed trên `E`.

Nếu `c.close()` ném khi phần thân đang định `return`, ngoại lệ đóng này có thể trở thành lỗi chính. Các lần đóng `b` và `a` vẫn được thử; nếu chúng cũng ném lỗi, các lỗi phụ có thể được gắn suppressed vào lỗi chính từ `c.close()`.

**Đừng kết luận rằng một `close()` lỗi sẽ khiến Java bỏ qua các resource còn lại.** Cơ chế đóng được thiết kế để thử đóng những resource đã khởi tạo thành công, theo thứ tự ngược.

### Khi nhiều resource phụ thuộc nhau

Ví dụ reader bọc một input stream: `reader.close()` có thể đã đóng luôn stream bên dưới. Nếu khai báo cả hai trong danh sách resource, Java có thể gọi đóng stream thêm lần nữa. Nhiều stream chuẩn chịu được điều đó, nhưng một số `AutoCloseable` tùy biến có thể không an toàn khi đóng lặp.

Hãy đăng ký đúng **tài nguyên mà phạm vi hiện tại sở hữu**, dựa vào hợp đồng đóng của wrapper và nguồn, thay vì tự động thêm tất cả đối tượng có `close()` vào danh sách.

## 14. Ngắt thread và đóng tài nguyên

Một thread có thể bị yêu cầu dừng công việc bằng cơ chế interrupt. Nhưng `Thread.interrupt()` **không tự động ném ngoại lệ vào mọi chỗ đang chạy** và không bảo đảm mọi API sẽ ngay lập tức dừng.

Nếu một thao tác trong thân `try-with-resources` ném `InterruptedException` và ngoại lệ này làm rời phần thân, các tài nguyên đã được đăng ký vẫn được đóng theo quy tắc thoát bất thường.

Ví dụ khung:

```java
static void consume(AutoCloseable resource)
        throws Exception {
    try (resource) {
        Thread.sleep(1_000);
    }
}
```

Đây là phương thức minh họa Java 17+, trong đó tham số resource không bị gán lại. Nếu `Thread.sleep` ném `InterruptedException` vì thread đang ngủ bị ngắt, resource được đóng trước khi ngoại lệ thoát khỏi phương thức. Nếu tầng trên bắt `InterruptedException` và chọn dừng tác vụ, thông thường cần xử lý trạng thái ngắt đúng chính sách (ví dụ khôi phục interrupt flag khi không thể ném tiếp).

Cần phân biệt việc **thoát khỏi phần thân bằng ngoại lệ** (cơ chế đóng có hiệu lực) với một thread vẫn đang chạy trong lời gọi bị chặn hoặc vòng lặp vô hạn mà chưa rời `try`. Trong trường hợp thứ hai, resource chưa nhất thiết được đóng tại thời điểm bạn quan sát.

## 15. Khi nào cơ chế đóng tự động không đảm bảo xảy ra?

`try-with-resources` hoạt động theo các quy tắc thực thi của ngôn ngữ Java. Tuy vậy, không thể hứa `close()` sẽ luôn chạy trong mọi trường hợp bên ngoài mô hình này:

- `Runtime.getRuntime().halt(...)` kết thúc JVM trực tiếp.
- `System.exit(...)` bắt đầu kết thúc JVM; không đảm bảo mọi thread đang trong `try-with-resources` hoàn tất công việc và đóng resource.
- Tiến trình bị hệ điều hành kết thúc cưỡng bức, JVM gặp sự cố nghiêm trọng hoặc hệ thống mất điện.
- Thread mắc kẹt trong một thao tác không thoát, nên khối `try` chưa được rời.
- `close()` được gọi nhưng chính nó treo vô thời hạn hoặc thất bại giữa chừng; lời gọi được thực hiện không chứng minh việc giải phóng tài nguyên hoàn tất thành công.

Không dùng shutdown hook thay cho quản lý vòng đời tài nguyên ở từng phạm vi; shutdown hook cũng không phải cơ chế có thể bảo đảm trong mọi kiểu dừng process.

**Quy tắc thực hành:** `try-with-resources` đáng tin cho các đường hoàn tất Java thông thường, gồm `return`, `throw`, `break` và `continue`; nhưng nó không thay thế quy trình phục hồi sau crash, cơ chế giao dịch hoặc chính sách shutdown.

## 16. Quan hệ giữa scope, ownership và việc đóng khi thoát sớm

Ba khái niệm cần tách rời:

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Scope | Tên biến còn có thể truy cập từ mã hiện tại không? | Biến khai báo trong `try (...)` không dùng được sau cấu trúc |
| Lifetime | Resource đã đóng hoặc còn sẵn sàng dùng chưa? | `try (external)` đóng external khi rời khối |
| Ownership | Thành phần nào chịu trách nhiệm đóng? | Hàm tự mở file thì thường tự đóng file |

Từ Java 9, có thể khai báo biến trước rồi đưa vào `try`:

```java
var reader = java.nio.file.Files.newBufferedReader(path);
try (reader) {
    return reader.readLine();
}
```

Đây là **thân phương thức minh họa** với `path` hợp lệ và chữ ký checked exception thích hợp. Biến `reader` vốn được khai báo ngoài `try`, nhưng khi phương thức chuẩn bị `return`, resource vẫn được đóng. Điều kiện sử dụng biến ngoài trong resource specification là `final` hoặc *effectively final*.

Nếu một biến còn nằm trong scope sau khi rời `try (reader)`, điều đó **không cho phép tiếp tục đọc qua reader đã đóng**. Phạm vi biến không kéo dài vòng đời resource.

### Không đóng resource do người khác còn sở hữu

Nếu caller cấp một stream còn cần dùng, một phương thức con tùy tiện viết `try (callerStream)` rồi `return` sớm sẽ khiến stream **bị đóng trước khi caller sử dụng tiếp**. Cú pháp chạy đúng nhưng thiết kế ownership sai.

Tốt hơn là thống nhất hợp đồng: hàm nào **tạo và sở hữu** resource thường chịu trách nhiệm đóng; hàm chỉ **mượn** resource thường không đóng nếu caller còn sử dụng sau đó. Có những API chuyển quyền sở hữu cho callee, nhưng việc đó phải được công bố rõ.

## 17. Những nhầm lẫn thường gặp

| Nhầm lẫn | Sự thật | Cách thực hành |
| --- | --- | --- |
| “`return` chạy ngay nên bỏ qua `close()`” | Java đóng trước khi hoàn tất `return` | Dùng `try-with-resources` quanh tài nguyên cần đóng |
| “Có `break`/`continue` thì resource không đóng” | Các đường thoát khỏi phạm vi vẫn kích hoạt đóng | Đảm bảo phạm vi `try` tương ứng thực sự bị rời |
| “`close()` luôn chạy sau `catch`” | `close()` chạy trước các handler gắn cùng cấu trúc | Kiểm tra suppressed exception từ handler |
| “`close()` lỗi nhưng `return` chắc chắn trả thành công” | Lỗi đóng có thể thay đường `return` | Không bỏ qua ngoại lệ đóng |
| “Nếu body và close cùng lỗi thì chỉ thấy lỗi close” | Với `try-with-resources`, lỗi body là chính, close bị suppressed | Kiểm tra `getSuppressed()` |
| “Suppressed exception là `cause`” | `getCause()` và `getSuppressed()` khác nhau | Dùng đúng API chẩn đoán |
| “`close()` của B lỗi thì A không được đóng” | Java vẫn thử đóng các resource đã mở khác | Thiết kế `close()` độc lập và an toàn |
| “`openB()` lỗi thì `openA()` để rò rỉ” | A đã mở được sẽ được đóng khi init B lỗi | Đặt resource vào cùng resource specification khi phù hợp |
| “Biến còn scope nghĩa là resource còn mở” | Scope không đồng nghĩa lifetime | Không dùng resource đã đóng |
| “Một đối tượng có `close()` là dùng được trong `try`” | Kiểu phải triển khai `AutoCloseable` | Kiểm tra kiểu và hợp đồng đóng |
| “`try-with-resources` đảm bảo trên cả mất điện/halt” | Không có bảo đảm tuyệt đối ngoài thực thi bình thường | Thiết kế shutdown/crash recovery riêng |
| “Tài nguyên đóng thì tác động trước đó tự rollback” | Đóng không đồng nghĩa rollback | Dùng hợp đồng transaction/bù trừ khi cần |
| “Có thể tự gọi `close()` rồi để tự động đóng lại” | Có thể double-close | Làm rõ ownership và tránh đóng trùng |

## 18. Checklist trước khi sử dụng `try-with-resources`

1. **Kiểm tra kiểu:** resource có thực sự triển khai `AutoCloseable` không? `close()` có thể ném checked exception nào?
2. **Xác định ownership:** đây có phải resource mà phạm vi hiện tại chịu trách nhiệm đóng không?
3. **Giới hạn scope:** các thao tác cần resource đã nằm trọn trong phần thân `try` chưa?
4. **Xét `return`:** giá trị được đánh giá trước khi đóng; nếu close lỗi, caller có thể không nhận giá trị đó.
5. **Xét `throw`:** nếu thân ném ngoại lệ, Java sẽ thử đóng và lỗi đóng có thể xuất hiện trong `getSuppressed()`.
6. **Xét `break` và `continue`:** lệnh có thật sự rời vùng quản lý resource không? Có phụ thuộc vào lần lặp kế tiếp không?
7. **Xét nhiều resource:** mở trái → phải, đóng phải → trái; kiểm tra wrapper có thể đã đóng nguồn bên dưới chưa.
8. **Xét initializer thất bại:** các resource đã khởi tạo thành công trước điểm lỗi vẫn được đóng.
9. **Xét handler:** `catch` gắn với `try-with-resources` chạy sau bước đóng; phải đủ rộng để bắt lỗi mong muốn, nhưng không nên nuốt lỗi không có phương án xử lý.
10. **Xét tính đầy đủ của kết quả:** phần thân thành công không đảm bảo toàn bộ lời gọi thành công nếu `close()`/flush thất bại.
11. **Xét suppressed:** nếu hệ thống log lỗi, có cần lưu cả danh sách lỗi đóng phụ không?
12. **Xét shutdown/crash:** có cơ chế xử lý tình huống tiến trình không đi qua đường thoát Java thông thường không?
13. **Kiểm thử:** bao phủ đường thành công, `return` sớm, ngoại lệ thân `try`, lỗi `close()`, lỗi initializer và nhiều resource cùng thất bại.

## 19. Bài tập tự kiểm tra

**Bài A.** Trong `try (R r = new R()) { return 5; }`, `r.close()` có được gọi không?

**Có**, khi phương thức chuẩn bị rời phần thân bằng `return`, với điều kiện resource đã được khởi tạo và JVM tiếp tục thực thi bình thường. `close()` chạy trước khi caller nhận `5`.

**Bài B.** Nếu `close()` ném `IllegalStateException` trong khi `try` chuẩn bị trả `5`, caller luôn nhận `5` chứ?

**Không.** Ngoại lệ từ `close()` có thể thay đường `return`, nên caller nhận lỗi thay vì số `5` nếu không có handler phù hợp.

**Bài C.** `try` ném `IOException("read failed")`, còn `close()` ném `IOException("close failed")`. Với `try-with-resources`, lỗi nào là chính?

**Thông thường là `"read failed"`**, còn lỗi `"close failed"` được lưu trong `getSuppressed()` của ngoại lệ chính.

**Bài D.** Resource A mở trước B. Khi `return` trong thân, A hay B được đóng trước?

**B trước A.** Java đóng ngược thứ tự khai báo, không phụ thuộc việc thoát bằng `return` hay kết thúc bình thường.

**Bài E.** Vòng lặp mở một resource mỗi lần. Trong thân `try` có `continue;`. Resource của lần hiện tại có đóng trước lần sau không?

**Có**, nếu `continue` rời phạm vi `try-with-resources` đó. Cơ chế đóng chạy trước khi điều khiển tiếp tục vòng lặp.

**Bài F.** `openA()` thành công, `openB()` lỗi, thân `try` chưa chạy. A có được đóng không?

**Có.** Những resource đã được khởi tạo thành công được đóng khi khởi tạo resource sau thất bại.

**Bài G.** Cả thân và hai lệnh đóng đều lỗi. Caller có thể xem những lỗi đóng ở đâu?

Qua **`getSuppressed()`** trên ngoại lệ chính, theo thứ tự các lần đóng tạo ra chúng.

**Bài H.** Một resource có `close()` đã được gọi nhưng bản thân close gặp lỗi. Có thể kết luận tài nguyên chắc chắn được giải phóng thành công không?

**Không.** “Đã gọi `close()`” không bảo đảm “đóng thành công”; trạng thái thực tế phụ thuộc hợp đồng và implementation của resource.

**Bài I.** Gọi `System.exit(...)` bên trong thân `try-with-resources` có giống một `return` thông thường không?

**Không.** Dừng tiến trình/JVM không bảo đảm việc đóng tài nguyên đang mở qua đường thực thi `finally`/`try-with-resources`. Không dùng `System.exit` để thay cho quy trình đóng thông thường.

**Bài J.** `try (external)` tự động đóng tài nguyên, nhưng `external` được khai báo bên ngoài và sau `try` vẫn nhìn thấy. Có thể dùng tiếp không?

**Không nên**, trừ khi hợp đồng resource cụ thể quy định một thao tác sau đóng là hợp lệ. Scope của biến và trạng thái đóng là hai chuyện khác nhau.

## Kết luận

**`try-with-resources` đóng tài nguyên đã được khởi tạo thành công trước khi hoàn tất đường rời phạm vi**, kể cả khi có `return`, `throw`, `break` hoặc `continue`. Với nhiều resource, thứ tự đóng **ngược với thứ tự khởi tạo**. Khi phần thân ném lỗi và `close()` cũng ném, Java bảo toàn ngoại lệ chính và ghi lỗi đóng dưới dạng **suppressed exception**. Nhưng nếu phần thân chỉ chuẩn bị `return` và `close()` ném lỗi, kết quả trả về có thể **bị thay bằng ngoại lệ đóng**.

Thiết kế đúng cần kết hợp ba điều: **phạm vi sử dụng đủ hẹp**, **ownership tài nguyên rõ ràng**, và **xử lý trung thực các lỗi cả trong thân lẫn lúc đóng**. Cơ chế này giải quyết nhiều đường thoát trong Java, nhưng không thay thế quản lý giao dịch hoặc các bảo đảm phục hồi khi process bị kết thúc bất thường.