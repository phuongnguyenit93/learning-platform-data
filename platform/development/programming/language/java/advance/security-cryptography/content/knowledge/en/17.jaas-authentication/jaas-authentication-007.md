# 17.7 Subject.current, Subject.callAs và cách đọc mã cũ sử dụng doAs

Trong **JAAS (Java Authentication and Authorization Service)**, `javax.security.auth.Subject` biểu diễn danh tính đã được xác thực của một người dùng hoặc dịch vụ: nó tập hợp các **`Principal`** và credentials liên quan. Một đoạn code nghiệp vụ có thể cần biết **`Subject` nào đang gắn với phạm vi thực thi** mà không phải truyền đối tượng qua từng hàm. Các API hiện đại phục vụ việc đó là:

- **`Subject.current()`:** đọc `Subject` đang được gắn với phạm vi thực thi hiện tại; có thể trả về `null`.
- **`Subject.callAs(subject, callable)`:** chạy một `Callable<T>` với `subject` là `Subject` hiện tại trong khoảng thời gian chạy action; sau đó khôi phục ngữ cảnh trước đó.

Trong code Java cũ thường gặp **`Subject.doAs(...)`** và **`Subject.getSubject(AccessController.getContext())`**. Chúng xuất hiện trong kiến trúc **Security Manager / AccessControlContext (ACC)**; từ **JDK 24** Security Manager bị **vô hiệu hóa vĩnh viễn** (JEP 486). Vì vậy, khi đọc hoặc nâng cấp một hệ thống JAAS, cần phân biệt **ràng buộc danh tính vào phạm vi chạy**, **xác thực thông tin đăng nhập**, và **cấp phép thao tác nghiệp vụ**: ba vấn đề **không đồng nghĩa**.

**Điều kiện phiên bản:** `Subject.current` và `Subject.callAs` có từ **Java 18**, nên chương trình sử dụng chúng **không biên dịch với `--release 17`**. Hai ví dụ đầy đủ trong bài được biên dịch bằng `javac --release 18` và chạy kiểm thử trên JDK 24. Java 17 vẫn có các API legacy, nhưng không có hai phương thức mới. Trong JDK 24–26, `doAs` vẫn có trong API ở trạng thái *deprecated for removal*, còn `getSubject(AccessControlContext)` ném `UnsupportedOperationException`.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Nhận diện một `Subject`, `Principal` và các bộ credentials trong JAAS; hiểu nguồn `Subject` đáng tin cậy.
2. Giải thích chính xác **phạm vi động** của `callAs`, cách `current` trả `Subject` hoặc `null`, cách nested scope và exception khôi phục context.
3. Viết và chạy chương trình Java 18+ dùng `Subject.callAs`, kể cả `Callable` có checked exception.
4. Đọc được `Subject.doAs(Subject, PrivilegedAction)` và `doAs(Subject, PrivilegedExceptionAction)`, phân biệt exception của code cũ.
5. Hiểu tại sao `Subject.getSubject(AccessController.getContext())` hỏng từ JDK 24 và tại sao không nên tìm cách bật lại Security Manager.
6. Migrate code cũ sang `current`/`callAs` và kiểm tra **luồng không đồng bộ/thread pool** tránh làm mất hoặc rò rỉ danh tính.
7. Giữ ranh giới giữa **JAAS authentication** và **application authorization**: `callAs` không xác thực password hoặc tự cho phép truy cập file/database.

## 2. Mô hình `Subject`: danh tính, không phải một lệnh “đăng nhập”

`javax.security.auth.Subject` là một đối tượng chứa:

- **`Set<Principal>`:** một hoặc nhiều danh tính/định danh, ví dụ tên người dùng, principal Kerberos, DN từ chứng thư hoặc service principal.
- **Public credentials:** thông tin có thể chia sẻ trong mô hình bảo mật phù hợp, ví dụ certificate.
- **Private credentials:** thông tin nhạy cảm như tickets, tokens hay khóa bí mật tùy công nghệ xác thực; cần hạn chế đọc và tuyệt đối không log tùy tiện.

`Principal` chỉ là interface với phương thức `getName()`. Một `Subject` có thể có **nhiều Principal**; ứng dụng không nên giả định `subject.getPrincipals().iterator().next()` luôn đại diện đúng user hay quyền truy cập.

```text
                   JAAS LoginContext
                 login() thành công
                         |
                         v
                Subject đã xác thực
               /         |         \
           Principals  Public     Private
                       Credentials Credentials
                         |
               Subject.callAs(subject, action)
                         |
                Subject.current()
                         |
                   business code
                         |
              authorization riêng
```

### 2.1. `Subject` đến từ đâu?

Trong hệ thống JAAS thông thường, `LoginContext` sử dụng `LoginModule` và `CallbackHandler` để thực hiện **authentication**; sau khi `login()` thành công, `LoginContext.getSubject()` trả `Subject` đã được population bởi các module liên quan.

Một ứng dụng có thể tự gọi `new Subject()` để viết test, nhưng **điều đó không chứng minh người dùng đã đăng nhập**, không chứng minh chứng thư/Kerberos ticket hợp lệ và cũng không chứng minh các `Principal` bên trong đáng tin. Tạo một `Subject` chứa `CN=Admin` không làm người gọi trở thành admin về mặt bảo mật.

### 2.2. Principal không tự là Role/Permission

Một `Principal` có thể là tên tài khoản, DN, service identity hoặc thông tin nhận diện khác. **Không có quy tắc universal** rằng principal tên `"admin"` đã được cấp quyền quản trị. Quyền thật được tính qua **authorization policy/IAM/ACL/resource ownership** của ứng dụng hoặc giao thức.

Từ JDK 24, cơ chế JAAS authorization dựa trên **Security Manager / policy-file permissions** không còn hoạt động theo nghĩa trước kia. Việc có current subject **không tự thay** các lệnh kiểm tra permission của mô hình cũ.

### 2.3. `setReadOnly` và bảo vệ credentials

`Subject.setReadOnly()` ngăn thêm/bớt `Principal` và credentials khỏi các tập trực tiếp của `Subject`. Nó **không tự đóng băng nội dung mọi đối tượng credential mutable**, không hủy secrets và không giải quyết vấn đề thiếu authentication.

Khi không cần chỉnh sửa Subject sau login, ứng dụng có thể cân nhắc read-only theo lifecycle của JAAS; nhưng phải tránh gọi trước khi `LoginModule` cần thêm hoặc xóa principals/credentials trong `commit/logout`. Quản trị vòng đời secret và `logout()` phụ thuộc công nghệ/login module.

## 3. `Subject.current()` đọc điều gì?

Chữ ký:

```java
public static Subject current()
```

Nó trả về **`Subject` đang được ràng buộc với phạm vi thực thi hiện tại**. Với JDK 24+, nếu đang ở ngoài mọi `callAs`/`doAs` phù hợp, giá trị thông thường là **`null`**.

```text
Subject.current()  -> null                  [ngoài scope]

Subject.callAs(alice, action) {
    Subject.current() -> alice
}

Subject.current()  -> null                  [sau action]
```

Đây là sơ đồ minh họa, **không phải cú pháp Java chạy trực tiếp**.

**Không nên dùng `Subject.current()` rồi lập tức gọi `getPrincipals()` mà không xét trường hợp `null`.** Nếu một API yêu cầu identity, nên từ chối một cách rõ ràng theo thiết kế, hoặc nhận một `Subject` đã được authenticate như tham số riêng.

### 3.1. Current subject có phải biến toàn cục?

**Không.** Nó không có nghĩa tất cả thread trong JVM đang dùng cùng một `Subject`. `current()` phản ánh ràng buộc danh tính trong **phạm vi chạy của thread hiện tại**, và hành vi lan truyền sang child tasks phụ thuộc mô hình concurrency.

- Không dùng một static field kiểu `static Subject activeUser` cho mọi request: request khác có thể nhìn sai danh tính.
- Không tự giả định task của `ExecutorService` sẽ kế thừa current subject từ thread submit.
- Không coi `Subject.current()` là bằng chứng identity đã được verify, vì code có thể chủ động gọi `callAs` với `Subject` do chính nó tạo.

### 3.2. Khi không có current subject

`Subject.current() == null` có thể có nghĩa:

- Đoạn code chạy ngoài bất kỳ scope `callAs`/`doAs` nào.
- `callAs(null, action)` chủ động bind `null` tạm thời.
- Công việc bị chuyển qua thread/executor mà không truyền context.
- Một framework đã authenticate user nhưng **không sử dụng `Subject` làm context**; user identity có thể nằm trong đối tượng request hoặc context của framework khác.

Vì thế đừng đánh đồng “current subject null” với “toàn hệ thống chưa authenticate”. Đây là tình trạng của **JAAS Subject binding**, không phải tình trạng xác thực tổng quát.

## 4. `Subject.callAs(Subject, Callable<T>)`: phạm vi động

Chữ ký API (có từ Java 18):

```java
public static <T> T callAs(Subject subject, Callable<T> action)
        throws CompletionException
```

`callAs` nhận hai đối số:

- `subject` là `Subject` cần gắn trong lúc chạy; **có thể `null`**.
- `action` là `java.util.concurrent.Callable<T>`; **không thể `null`**.

Nó **gọi action ngay trong scope**, lấy kết quả trả về và **khôi phục Subject trước đó** sau khi action kết thúc. Đây không phải API tự enqueue task hoặc tạo thread mới. Bên trong action, `Subject.current()` sẽ trả `subject` theo mô hình hiện đại.

### 4.1. Phạm vi lồng nhau: Alice → Bob → Alice

```text
outside: current=null
  callAs(Alice)
    current=Alice
    callAs(Bob)
      current=Bob
    done Bob
    current=Alice
  done Alice
outside: current=null
```

Khi lồng `callAs`, scope bên trong **che tạm** scope bên ngoài; sau khi kết thúc, scope bên ngoài được khôi phục. Không cần “`Subject.setCurrent`” vì API này **không tồn tại**.

### 4.2. Có thể bind `null` không?

Có. Ví dụ trong scope Alice, gọi `Subject.callAs(null, () -> ...)` sẽ làm `Subject.current()` trả `null` **trong action bên trong**, rồi trả lại Alice sau khi action kết thúc.

Điều này không được dùng như “xóa quyền” của Java Security Manager. Nó chỉ là **thay đổi context hiện tại**. Một code path cần principal cụ thể phải có kiểm tra authorization riêng.

### 4.3. Exception từ `Callable`

Khác `doAs` legacy, `callAs` nhận `Callable<T>` cho phép `call()` khai báo checked exception. Theo hợp đồng API, nếu action ném exception, `callAs` ném **`CompletionException`**, với `getCause()` là exception gốc. Điều này áp dụng cả khi exception xảy ra sâu trong action: **subject binding vẫn được khôi phục** theo scope.

Không dùng `catch (Exception e) { return allowed; }` hoặc bỏ qua `CompletionException` như thể action đã chạy thành công. Khi cần gửi lỗi ra API, xem cause và chuyển thành lỗi nghiệp vụ phù hợp mà không làm lộ credentials.

### 4.4. `callAs` không nâng đặc quyền

Tên phương thức có thể khiến người đọc tưởng đây là lệnh impersonation ở cấp hệ điều hành hoặc “elevate privileges”. Không phải: **`callAs` chỉ gắn `Subject` cho code có thể đọc được**. Nó không đổi user của process Windows/Linux, không cấp permission trong hệ điều hành, không tự tạo token, không tự mở kết nối Kerberos và **không tự xác nhận Principal**.

Các thư viện hỗ trợ JAAS Subject hoặc GSS/Kerberos có thể dùng context này để chọn credentials, nhưng trách nhiệm authentication/authorization và tương thích runtime vẫn thuộc về ứng dụng/thư viện.

## 5. Vì sao `Subject.doAs(...)` xuất hiện trong code cũ?

Trước mô hình API mới, một mẫu JAAS phổ biến là:

```java
Subject.doAs(authenticatedSubject,
        (PrivilegedAction<String>) () -> service.call());
```

Trong Java cũ có Security Manager, `doAs` tích hợp với **`AccessControlContext`/`SubjectDomainCombiner`** và cơ chế policy permissions để liên hệ `Subject` với các quyền của action. Trong những phiên bản hiện đại, Security Manager đã bị loại khỏi con đường vận hành thông thường, nên cách dùng này không còn ý nghĩa **“tạm chạy với đặc quyền dựa trên Security Manager”**.

Có hai overload quan trọng:

| Legacy API | Kiểu action | Kiểu exception điển hình |
| --- | --- | --- |
| `Subject.doAs(Subject, PrivilegedAction<T>)` | `PrivilegedAction<T>.run()` không khai báo checked exception | Runtime exception đi ra theo semantics của action |
| `Subject.doAs(Subject, PrivilegedExceptionAction<T>)` | `PrivilegedExceptionAction<T>.run()` có thể ném checked exception | `PrivilegedActionException` bọc checked exception |
| `Subject.doAsPrivileged(..., AccessControlContext)` | Biến thể nhận ACC | **Không có phương thức thay thế nào bảo toàn hành vi phân quyền của Security Manager** |
| `Subject.getSubject(AccessControlContext)` | Đọc `Subject` gắn với ACC | Trên **JDK 24+ ném `UnsupportedOperationException`** |

Khi lambda có thể khớp cả `PrivilegedAction` và `PrivilegedExceptionAction`, Java có thể báo **ambiguous method call**. Trong code legacy hãy đọc kỹ cast hoặc kiểu biến:

```java
String name = Subject.doAs(s,
        (PrivilegedAction<String>) () -> "Alice");
```

Đây là fragment minh họa, `s` là một `Subject` đã được tạo/phê duyệt. Khi migrate sang `callAs`, overload ambiguity không còn vì `Callable<T>` là một dạng tham số duy nhất.

### 5.1. `doAs` có bị xóa khỏi JDK 24 không?

**Chưa.** Tài liệu Java SE 24–26 vẫn liệt kê `doAs`, nhưng đánh dấu **deprecated for removal**. Trên JDK 24+, nó vẫn có thể bind `Subject` cho khoảng thời gian action chạy; **không còn cơ chế nâng đặc quyền Security Manager**. Tuy nhiên, không nên giữ mã mới phụ thuộc API deprecated; chuyển sang `Subject.callAs`.

### 5.2. Cái gì thực sự hỏng từ JDK 24?

Mẫu cũ:

```java
AccessControlContext context = AccessController.getContext();
Subject found = Subject.getSubject(context);
```

Trên JDK 24+, `Subject.getSubject(context)` **luôn ném `UnsupportedOperationException`**, kể cả khi gọi bên trong một `Subject.doAs(...)`. Đây là thay đổi API có chủ đích khi Security Manager bị vô hiệu hóa.

Thay bằng:

```java
Subject found = Subject.current();
```

Không chuyển `Subject.getSubject(AccessController.getContext())` thành `Subject.getSubject(null)` để thử vượt lỗi: API này **không hỗ trợ nữa**, không phải chỉ sai tham số.

## 6. Mốc phiên bản Java cần nhớ

| JDK | Tình trạng thực tế | Khuyến nghị khi đọc/nâng cấp |
| --- | --- | --- |
| **Java 8–17** | Legacy `Subject.doAs`/`getSubject(ACC)` tồn tại; **chưa có `current`/`callAs`** | Với code bắt buộc chạy Java 17, chưa thể viết trực tiếp API mới; tách tương thích runtime hoặc lên JDK hỗ trợ |
| **Java 18–22** | `Subject.current`/`Subject.callAs` được bổ sung **từ Java 18**; legacy API deprecated | Viết code mới theo API mới, kiểm thử theo phiên bản Security Manager thực tế |
| **Java 23** | Hành vi `Subject` phụ thuộc trạng thái Security Manager “allowed” hay không; khi không được phép, `getSubject(ACC)` ném UOE và current binding theo scope | Kiểm thử khi không cho phép Security Manager; loại bỏ giả định về ACC và thread inheritance |
| **Java 24–26** | Security Manager **vô hiệu hóa vĩnh viễn** từ JDK 24; `getSubject(ACC)` ném UOE; `doAs` deprecated vẫn bind theo scope | Dùng `current`/`callAs`; tự thực thi authorization, xử lý async context và migration exception |

Ở JDK 23 từng có cấu hình tương thích tạm thời `-Djava.security.manager=allow` trong một số trường hợp để giữ hành vi cũ. **Đó không phải giải pháp nâng cấp lâu dài và không khôi phục Security Manager trên JDK 24+.** Không hướng dẫn production bật lại một cơ chế đã vô hiệu hóa để sửa lỗi JAAS.

### 6.1. JEP 411 và JEP 486 liên quan thế nào?

- **JEP 411 (Java 17):** đánh dấu Security Manager **deprecated for removal**.
- **Java 18:** thêm `Subject.current` và `Subject.callAs` như hướng thay thế các phương thức JAAS Subject phụ thuộc ACC.
- **Java 23:** điều chỉnh hành vi khi Security Manager không được phép, giúp phát hiện sớm code đang phụ thuộc `getSubject(ACC)` hoặc việc truyền context qua child thread.
- **JEP 486 (Java 24):** vô hiệu hóa Security Manager vĩnh viễn; authorization dựa trên Security Manager/policy files không còn được hỗ trợ.

**Điểm phân biệt:** “đổi tên `doAs` thành `callAs`” chỉ là **một phần** migration. Nếu code trước đây dựa vào Security Manager để chặn truy cập file/network/API, bạn phải **thiết kế lại cơ chế kiểm tra quyền** tương ứng, không chỉ sửa cú pháp.

## 7. Ví dụ runnable Java 18+: current, nested callAs và ExecutorService

Ví dụ này **tạo Subject giả lập trong memory để học API**, không có JAAS LoginModule hay password thật. Nó kiểm tra: phạm vi rỗng → Alice → Bob → Alice, `callAs(null)`, khôi phục sau exception, và sự khác biệt giữa task thread pool **không được truyền context** so với task **được re-bind tường minh**.

Dùng `javax.security.auth.x500.X500Principal` làm kiểu `Principal` có sẵn trong JDK, thay vì viết thêm principal class. Constructor `new Subject(true, ...)` tạo một đối tượng **read-only** theo mục đích demo.

Lưu file **SubjectScopeDemo.java**:

```java
import java.io.IOException;
import java.util.Set;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import javax.security.auth.Subject;
import javax.security.auth.x500.X500Principal;

public class SubjectScopeDemo {
    static Subject user(String name) {
        return new Subject(true,
                Set.of(new X500Principal("CN=" + name)),
                Set.of(), Set.of());
    }

    public static void main(String[] args) throws Exception {
        Subject alice = user("Alice");
        Subject bob = user("Bob");

        System.out.println("outside null: "
                + (Subject.current() == null));

        String result = Subject.callAs(alice, () -> {
            boolean aliceVisible = Subject.current() == alice;
            boolean nestedBob = Subject.callAs(
                    bob, () -> Subject.current() == bob);
            boolean restoredAlice = Subject.current() == alice;
            boolean temporarilyNull = Subject.callAs(
                    null, () -> Subject.current() == null);
            boolean restoredAgain = Subject.current() == alice;
            return aliceVisible + "," + nestedBob + ","
                    + restoredAlice + "," + temporarilyNull
                    + "," + restoredAgain;
        });
        System.out.println("nested scope checks: " + result);
        System.out.println("after scope null: "
                + (Subject.current() == null));

        boolean checkedExceptionWrapped = false;
        try {
            Subject.callAs(alice, () -> {
                throw new IOException("test failure");
            });
        } catch (CompletionException expected) {
            checkedExceptionWrapped =
                    expected.getCause() instanceof IOException;
        }
        System.out.println("checked exception wrapped: "
                + checkedExceptionWrapped);
        System.out.println("after exception null: "
                + (Subject.current() == null));

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            // Tạo worker trước khi submit trong phạm vi Alice.
            pool.submit(() -> Subject.current()).get();

            Future<Boolean> implicit = Subject.callAs(
                    alice,
                    () -> pool.submit(() -> Subject.current() == null));

            Future<Boolean> explicit = Subject.callAs(alice, () -> {
                Subject captured = Subject.current();
                return pool.submit(() ->
                        Subject.callAs(captured,
                                () -> Subject.current() == alice));
            });

            System.out.println("pool not inherited: "
                    + implicit.get());
            System.out.println("explicit propagation works: "
                    + explicit.get());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

**Phiên bản tối thiểu: Java 18.** Có thể biên dịch với JDK 24 bằng mức tương thích `--release 18`:

```bash
javac --release 18 -encoding UTF-8 SubjectScopeDemo.java
java SubjectScopeDemo
```

Stdout đã xác minh khi chạy trên JDK 24:

```text
outside null: true
nested scope checks: true,true,true,true,true
after scope null: true
checked exception wrapped: true
after exception null: true
pool not inherited: true
explicit propagation works: true
```

### 7.1. Giải thích chi tiết kết quả

**Trước `callAs`:** demo chưa gắn `Subject`, nên `Subject.current()==null` là `true`.

**Bên trong Alice:** `current()==alice` là `true`; so sánh bằng `==` ở đây chứng minh đúng **cùng object reference** được gắn, không phải so sánh danh tính nghiệp vụ.

**Trong scope Bob:** `callAs(bob, ...)` tạm thay Subject hiện tại. Khi Bob kết thúc, Alice được phục hồi. Đây là **cấu trúc scope lồng nhau**, không phải thay đổi vĩnh viễn một global singleton.

**`callAs(null)`:** tạm cho `current()==null`, rồi Alice được phục hồi ngay sau callback.

**Ngoài scope:** `current()==null` lại là `true`; không cần gọi phương thức `setCurrent(null)` không tồn tại.

**Checked exception:** `IOException` từ `Callable.call` được chuyển thành nguyên nhân của `CompletionException`. Sau khi catch, current vẫn được khôi phục về `null`.

**ExecutorService:** `pool.submit` không tự kế thừa subject đang gắn ở thread gọi. Demo đã **khởi tạo worker trước** để tránh nhầm với bất kỳ cơ chế thread creation nào; task chạy trong worker kiểm tra `current()==null`.

**Truyền tường minh:** capture `Subject` từ scope Alice, gửi object reference đến worker rồi **gọi `Subject.callAs(captured, ...)` trong worker**; task đó nhìn thấy Alice trong đúng phạm vi của chính nó. Hết task, worker được khôi phục context trước đó.

### 7.2. Những gì demo KHÔNG chứng minh

- Không chứng minh Alice/Bob đã authenticate: hai `Subject` được tạo thủ công chỉ để thử scoped API.
- Không chứng minh có quyền admin hay quyền file/network: **`callAs` không thực thi quyền Security Manager**.
- Không chứng minh mọi concurrency framework đều truyền context giống nhau: executor, CompletableFuture, parallel stream, reactive streams và structured concurrency có lifecycle khác nhau.
- Không bảo đảm worker không thể nhìn thấy một `Subject` ở bối cảnh khác nếu có custom wrapper/framework đặc thù; hãy kiểm thử **runtime và context propagation policy** của ứng dụng.
- Không chứng minh truyền một `Subject` mutable có private credentials giữa nhiều thread là an toàn; bảo vệ credential và lifetime riêng.

## 8. Ví dụ runnable: cách đọc legacy `doAs` và lỗi `getSubject` trên JDK 24+

Code cũ thường dùng hai overload `doAs`, và lấy `Subject` thông qua `AccessController.getContext()`. Chương trình này cho thấy **doAs vẫn bind subject trên JDK 24**, nhưng **lối đọc dựa trên ACC không còn dùng được**.

Lưu file **LegacySubjectDemo.java**:

```java
import java.io.IOException;
import java.security.AccessController;
import java.security.PrivilegedAction;
import java.security.PrivilegedActionException;
import java.security.PrivilegedExceptionAction;
import java.util.Set;
import javax.security.auth.Subject;
import javax.security.auth.x500.X500Principal;

@SuppressWarnings("removal")
public class LegacySubjectDemo {
    public static void main(String[] args) throws Exception {
        Subject alice = new Subject(
                true, Set.of(new X500Principal("CN=Alice")),
                Set.of(), Set.of());

        String result = Subject.doAs(alice,
                (PrivilegedAction<String>) () ->
                        Subject.current() == alice
                                ? "Alice" : "not Alice");
        System.out.println("legacy doAs still binds: " + result);

        boolean checkedWrapped = false;
        try {
            Subject.doAs(alice,
                    (PrivilegedExceptionAction<Void>) () -> {
                        throw new IOException("legacy failure");
                    });
        } catch (PrivilegedActionException expected) {
            checkedWrapped =
                    expected.getException() instanceof IOException;
        }
        System.out.println("legacy checked wrapped: " + checkedWrapped);

        boolean oldReaderUnavailable = false;
        try {
            Subject.getSubject(AccessController.getContext());
        } catch (UnsupportedOperationException expected) {
            oldReaderUnavailable = true;
        }
        System.out.println("getSubject unsupported on JDK 24+: "
                + oldReaderUnavailable);
    }
}
```

Biên dịch **Java 18+** vì ví dụ có dùng `Subject.current()`; chạy trên **JDK 24+** để thấy `getSubject` không còn dùng được:

```bash
javac --release 18 -encoding UTF-8 LegacySubjectDemo.java
java LegacySubjectDemo
```

Stdout kiểm tra trên JDK 24:

```text
legacy doAs still binds: Alice
legacy checked wrapped: true
getSubject unsupported on JDK 24+: true
```

**`@SuppressWarnings("removal")` trong demo chỉ để giữ ví dụ tập trung, không phải khuyến nghị che cảnh báo trong production.** Trong dự án thực, hãy chuyển sang API mới, kiểm tra các phụ thuộc legacy và giữ cảnh báo deprecation trong CI khi có thể.

### 8.1. Vì sao hai exception wrapper khác nhau?

- **`doAs(PrivilegedExceptionAction)`:** checked exception từ `run()` được bọc bằng **`PrivilegedActionException`**; lấy exception thật qua `getException()` hoặc `getCause()`.
- **`callAs(Callable)`:** exception từ `call()` được bọc bằng **`CompletionException`**; lấy cause qua `getCause()`.
- **`doAs(PrivilegedAction)`:** bản thân `run()` không khai báo checked exception; cần phân biệt unchecked exception từ nghiệp vụ.
- **`Subject.getSubject(ACC)`:** ném **`UnsupportedOperationException`** trên JDK 24+, không phải “không có user nên trả `null`”.

Đừng đổi catch từ `PrivilegedActionException` thành `IOException` trực tiếp mà bỏ qua wrapper. Đây là nguồn gây lỗi khi migration code có checked exceptions.

## 9. Chuyển đổi code cũ sang API mới

### 9.1. Bản đồ thay thế

| Trong code legacy | Thay thế hiện đại | Điều phải kiểm tra |
| --- | --- | --- |
| `Subject.getSubject(AccessController.getContext())` | `Subject.current()` | Có thể `null`; không cần và không nên lấy ACC |
| `Subject.doAs(subject, PrivilegedAction<T>)` | `Subject.callAs(subject, Callable<T>)` | Bỏ cast `PrivilegedAction`; thay đổi wrapper khi action throw |
| `Subject.doAs(subject, PrivilegedExceptionAction<T>)` | `Subject.callAs(subject, Callable<T>)` | `PrivilegedActionException` → `CompletionException` |
| `Subject.doAsPrivileged(subject, action, acc)` | Gắn context bằng `callAs` nếu chỉ cần identity | Không có thay thế cho **giới hạn/nâng quyền** của Security Manager |
| `AccessController.doPrivileged(...)` | Thiết kế lại phần authorization nếu phụ thuộc SM | Không đổi tên trực tiếp để khôi phục permission enforcement |
| ACC chứa Subject được truyền đến child threads | Truyền `Subject` đã authenticate và bind lại trong task | Không kỳ vọng ExecutorService tự kế thừa |

### 9.2. Mẫu migrate lấy identity hiện hành

Trước (cũ, phụ thuộc Security Manager/ACC):

```java
// LEGACY - minh họa; code hiện đại không nên dùng.
Subject s = Subject.getSubject(AccessController.getContext());
if (s == null) {
    throw new SecurityException("Missing JAAS subject");
}
```

Sau (Java 18+):

```java
Subject s = Subject.current();
if (s == null) {
    throw new SecurityException("Missing JAAS subject");
}
```

Trong cả hai fragment, một `Subject` có mặt **không đảm bảo authentication**: vẫn cần chắc chắn caller chỉ tạo/bind `Subject` từ nguồn đã xác thực và kiểm tra authorization.

### 9.3. Migrate action trả kết quả

Trước:

```java
String value = Subject.doAs(authenticatedSubject,
        (PrivilegedAction<String>) () -> service.readValue());
```

Sau:

```java
String value = Subject.callAs(authenticatedSubject,
        () -> service.readValue());
```

Các biến `authenticatedSubject`/`service` là phần phụ thuộc của ứng dụng, nên đây là **fragment**, không phải chương trình độc lập. Khi action chỉ cần thấy `Subject.current`, thay thế về hành vi binding là phù hợp. Nếu code cũ phụ thuộc Security Manager cho phép file/URL/permission, phải xử lý ranh giới đó riêng.

### 9.4. Migrate checked exception an toàn

Mẫu cũ:

```java
try {
    return Subject.doAs(authenticatedSubject,
            (PrivilegedExceptionAction<String>)
                    () -> service.loadFromDisk());
} catch (PrivilegedActionException e) {
    Throwable original = e.getException();
    // Phân loại original theo hợp đồng API ứng dụng.
    throw new IllegalStateException("Operation failed", original);
}
```

Mẫu mới:

```java
try {
    return Subject.callAs(authenticatedSubject,
            () -> service.loadFromDisk());
} catch (CompletionException e) {
    Throwable original = e.getCause();
    // Không nuốt exception; chọn type/lỗi an toàn theo nghiệp vụ.
    throw new IllegalStateException("Operation failed", original);
}
```

Hai đoạn là **fragments**, cần nằm trong method có return type tương ứng và import `CompletionException`, `PrivilegedExceptionAction`, `PrivilegedActionException`. Với lỗi `IOException` cần giữ nguyên ở API cấp trên, có thể xét:

```java
try {
    return Subject.callAs(authenticatedSubject,
            () -> service.loadFromDisk());
} catch (CompletionException e) {
    if (e.getCause() instanceof IOException io) {
        throw io;
    }
    throw e;
}
```

Fragment này chỉ compile trong một method `throws IOException` (hoặc xử lý checked exception phù hợp); dùng Java 18+ và các biến dịch vụ đã có.

### 9.5. Không sửa code chỉ bằng search-and-replace

Một migration đúng đòi rà soát:

1. Chỗ nào lấy `Subject` từ `LoginContext.getSubject()` hoặc nguồn xác thực khác?
2. Chỗ nào tạo `Subject` giả chỉ bằng `new Subject()` mà code đang nhầm là authenticated?
3. Các đoạn gọi `doAs` có thật sự chỉ cần **identity binding**, hay còn dựa vào Security Manager policy?
4. Có code đọc `Subject.getSubject(AccessController.getContext())` trong thư viện/JAR không?
5. Có code giả định Subject **tự truyền vào thread mới, executor, reactive callback** không?
6. Các checked exceptions được bắt đúng wrapper mới và audit log không lộ credential không?
7. Người dùng bị thiếu `Subject` có bị fail closed ở các thao tác yêu cầu authentication không?
8. Các tests trước/ngoài/sau `callAs`, nested scope và concurrency đã kiểm tra chưa?

## 10. JAAS `LoginContext` và `Subject.callAs` nối với nhau như thế nào?

**Authentication** phải hoàn tất trước khi bind một `Subject` để xử lý yêu cầu yêu cầu danh tính.

Ví dụ logic tích hợp (`LoginContext` phải được cấu hình bằng `LoginModule` và `CallbackHandler` thật; fragment không chạy độc lập):

```java
LoginContext login = new LoginContext("ApplicationLogin", callbackHandler);
try {
    login.login();
    Subject authenticated = login.getSubject();
    if (authenticated == null) {
        throw new SecurityException("JAAS login returned no Subject");
    }
    Subject.callAs(authenticated, () -> {
        service.processAuthenticatedRequest();
        return null;
    });
} finally {
    // Theo lifecycle thực: logout và cleanup credentials.
    login.logout();
}
```

Trong hệ thống thật, xử lý `LoginException`, timeout, retry và callback secrets; đồng thời tránh gọi `logout` khi login chưa thành công nếu module không hỗ trợ. Fragment trên mô tả thứ tự ý tưởng, **không thay thế code vận hành đầy đủ**.

### 10.1. `callAs` không tự gọi `login`

Không có thứ tự ngầm:

```text
Subject.callAs(subject, action)
        !=
LoginContext.login() + authorization
```

Bạn có thể gọi `callAs` với `Subject` trống hoặc tự tạo. Vì vậy, một service không nên dùng điều kiện `Subject.current()!=null` làm **bằng chứng duy nhất** để cho phép rút tiền, tải dữ liệu cá nhân hoặc gọi API đặc quyền.

### 10.2. Đọc principal một cách có mục đích

Mã minh họa cho một ứng dụng đã xác thực, muốn đọc X.500 principal:

```java
Subject s = Subject.current();
if (s == null) {
    throw new SecurityException("No authenticated JAAS context");
}
Set<X500Principal> names =
        s.getPrincipals(X500Principal.class);
for (X500Principal name : names) {
    System.out.println(name.getName(X500Principal.RFC2253));
}
```

Đoạn trên chỉ phù hợp nếu X.500 principal thật sự được công nghệ xác thực của ứng dụng sử dụng; không tự cho rằng mọi `Subject` có `X500Principal`. Trong production, không log danh tính nhạy cảm trừ khi policy cho phép và không in private credentials.

### 10.3. Logout và scope khác nhau

`callAs` luôn **khôi phục current subject binding** khi action hoàn tất; điều đó **không tự đăng xuất** khỏi KDC, không hủy Kerberos tickets/token và không xóa secrets khỏi `Subject`.

`LoginContext.logout()` dùng để yêu cầu các `LoginModule` cleanup theo contract của chúng. Bạn phải quản lý **cả hai vòng đời**: phạm vi thực thi và thời hạn credentials/phiên đăng nhập.

## 11. Async, executor, virtual threads và context propagation

### 11.1. Vì sao Subject “biến mất” khi chuyển sang worker?

Code phía request thread:

```java
Subject.callAs(requestSubject, () -> {
    executor.submit(() -> service.handleRequest());
    return null;
});
```

Đây là fragment. Nếu `handleRequest` gọi `Subject.current()` trên một **executor worker thread**, nó **không mặc định** nhận `requestSubject` từ thread submit. Worker có thể được tạo trước đó và phục vụ nhiều request khác nhau; việc mong Java tự sao chép per-thread context sẽ dễ sai.

Điểm này đặc biệt quan trọng khi hệ thống hiện đại hóa từ Java cũ vốn dựa vào `AccessControlContext` hoặc library propagation đặc thù.

### 11.2. Truyền tường minh và bind theo scope trong worker

Một mẫu rõ ràng hơn:

```java
Subject captured = Subject.current();
Future<Result> future = executor.submit(() ->
        Subject.callAs(captured, () -> service.compute()));
```

Đây là fragment. Để dùng an toàn:

- Chỉ capture `Subject` **được authenticate/ủy quyền đúng** trong request hiện tại.
- Hạn chế lifetime của task, không giữ object chứa private credentials quá lâu trong queue.
- `callAs` đặt context trong **worker** và khôi phục sau khi task kết thúc; đây là cách tránh rò rỉ giữa các request khi dùng thread pool.
- `Future.get()`/`CompletableFuture` có các wrapper exceptions riêng (`ExecutionException`/`CompletionException`); nhớ xử lý **nhiều tầng cause** thay vì chỉ thay một catch.
- Nếu task tạo thêm task khác, phải thiết kế chính sách truyền context xuyên qua **toàn bộ cây task**, hoặc dùng framework context propagation đã được kiểm định.

### 11.3. Tại sao không tự dùng một `ThreadLocal<Subject>` global?

Có thể có lý do legacy, nhưng một custom `ThreadLocal` dễ bị:

- Quên `remove()` trong pool → request sau nhìn danh tính request trước.
- Copy reference của private credentials vào những thread không có quyền.
- Dùng một thread cho nhiều request reactive/coroutine mà semantics không đúng.
- Lẫn với `Subject.current()` của JDK, khiến thư viện đọc một context còn ứng dụng ghi context khác.

Ưu tiên scope **`Subject.callAs`** nếu thư viện đã tiêu thụ `Subject.current`; đảm bảo context được khôi phục có cấu trúc. Nếu app có framework security context riêng, hãy tích hợp qua API được hỗ trợ, không tự biến mọi identity thành Subject.

### 11.4. Structured concurrency

Tài liệu JDK mới mô tả rằng current Subject **có thể được kế thừa bởi child threads khởi chạy và hoàn tất trong scope cha khi sử dụng structured concurrency** phù hợp. Tuy nhiên:

- Đây **không** là cơ chế tự truyền cho mọi `new Thread` hoặc mọi `ExecutorService`.
- Structured concurrency có lịch sử **preview API** ở các JDK khác nhau; không đưa mã preview vào ví dụ Java 18+ ở bài này.
- Nếu một framework dùng structured concurrency, kiểm tra phiên bản JDK, giới hạn scope, cách hủy task và rules inheritance cụ thể.
- Với thread pool và tác vụ không có quan hệ cha–con có cấu trúc, dùng **truyền tường minh** hoặc adapter context propagation đáng tin.

## 12. Authorization trong thế giới không còn Security Manager

### 12.1. Chỉ bind Subject không đủ

Trên JDK 24+, `Subject.callAs` gắn thông tin danh tính cho code đọc, nhưng **không có bộ permission file/`SecurityManager.checkPermission` hoạt động như thời cũ**.

Ví dụ conceptual:

```text
User authenticator  -> Subject trusted by application
Subject.callAs(...) -> Scope so service can read identity
Authorization        -> Check identity/roles/tenant/resource policy
Sensitive operation  -> Execute only if policy explicitly allows
Audit                -> Record safe metadata, not credentials
```

Nếu đoạn code cần đọc file hoặc thao tác database, **OS ACL, IAM credentials, DB privileges và authorization logic** vẫn là các lớp kiểm soát thực sự. Không dựa vào lời gọi `callAs` để tự động chống việc một user không được phép đọc dữ liệu.

### 12.2. `Subject.current` có thể là input cho policy, không phải policy

Một ứng dụng có thể có code kiểu:

```java
Subject current = Subject.current();
if (current == null) {
    throw new SecurityException("Authentication required");
}
authorizationService.requireAccess(
        current, "orders:read", requestedOrderId);
```

Đây là fragment: `authorizationService` và `requestedOrderId` phải do ứng dụng cung cấp. Quan trọng là `authorizationService` phải:

1. Chỉ chấp nhận một `Subject` có **nguồn xác thực đáng tin** từ boundary được kiểm soát.
2. Phân biệt principal là identity, không tự đọc tên role giả do caller tự thêm.
3. Kiểm tra **quyền trên tài nguyên cụ thể** (tenant, owner, scope, action).
4. Fail closed khi không có đủ context, credentials hết hạn hoặc policy không rõ.
5. Không để caller untrusted tự chọn `Subject` rồi mượn `callAs` để vượt quyền.

### 12.3. Giải pháp thay `doAsPrivileged`

Nếu code cũ làm:

```java
// LEGACY: từng sử dụng AccessControlContext/policy permissions.
Subject.doAsPrivileged(subject, action, context);
```

Bạn **có thể** thay phần “bind identity trong một scope” bằng `Subject.callAs(subject, callable)` nếu service chỉ cần current subject. Nhưng **không có API thay thế tương đương cho việc nâng/quy định permission của Security Manager**. Quyền thao tác file/network/API phải được chuyển sang ranh giới khác (IAM/OS permissions/ACL, service boundary, explicit policy), có kiểm thử regressions và threat model.

## 13. Lỗi và triệu chứng hay gặp khi nâng JDK

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `cannot find symbol: Subject.current` ở `javac --release 17` | API chỉ có từ Java 18 | Nâng target JDK hoặc giữ code compatibility riêng, không giả là API Java 17 |
| `UnsupportedOperationException` trong `Subject.getSubject(...)` JDK 24 | ACC-based reader đã bị vô hiệu hóa | Chuyển sang `Subject.current()` và scope `callAs` |
| `doAs` warning deprecated for removal | API cũ phụ thuộc Security Manager concept | Migrate sang `callAs`, kiểm thử exception |
| `reference to doAs is ambiguous` | Hai overload với functional interface gần nhau | Cast `PrivilegedAction`/`PrivilegedExceptionAction` trong legacy; code mới dùng Callable |
| Catch `PrivilegedActionException` không bắt lỗi sau migrate | `callAs` dùng `CompletionException` | Đổi handling và preserve root cause |
| `Subject.current()==null` trong executor | Subject không tự kế thừa qua thread pool | Capture trusted subject, bind trong task bằng `callAs` |
| Subject xuất hiện sai user ở worker | Custom ThreadLocal/context bị rò, thiếu cleanup | Dùng scoped binding; kiểm thử isolation giữa request |
| `Subject.current()!=null` nhưng API bị truy cập trái phép | Đang coi presence of Subject là authorization | Kiểm tra policy/tenant/action/resource riêng |
| Kerberos/GSS lỗi sau nâng JDK | Thư viện dùng ACC/getSubject hoặc phụ thuộc inheritance cũ | Nâng dependency, kiểm thử JAAS login, delegation và thread propagation |
| Dùng `-Djava.security.manager=allow` trên JDK 24 để cứu code | Security Manager đã vô hiệu hóa vĩnh viễn | Sửa code/API, không dùng flag cũ làm giải pháp |
| Mất private credentials sau `logout` | LoginModule đã cleanup session hoặc code giữ Subject quá lâu | Quản lý lifecycle và tác vụ bất đồng bộ đúng |
| Nhiều `Principal` nhưng app lấy phần tử đầu tiên | Không có thứ tự/semantics universal của Set | Lọc đúng Principal class và policy của domain |
| Debug in `Subject.toString()` | Có nguy cơ ghi lộ metadata/credential theo implementation | Log tối thiểu, không in private credentials |
| Context bị giữ quá lâu trong queue | Captured Subject mang credential đã hết hạn/thu hồi | TTL, hủy task, tái xác minh tại boundary đúng |

### 13.1. Diagnostic checklist

Khi thấy lỗi “Subject not found” sau nâng JDK:

1. In phiên bản JDK trong môi trường test (không log thông tin đăng nhập): `java -version`.
2. Kiểm tra source/classpath có `getSubject(AccessController.getContext())` hay không.
3. Kiểm tra có `Subject.doAs`/`doAsPrivileged`, hoặc `AccessController.doPrivileged` phụ thuộc permission của Security Manager.
4. Xem `LoginContext.login()` có thật sự thành công và tạo `Subject` đúng không.
5. Xác định callback chạy **cùng scope/thread** với `callAs` hay đã chuyển sang executor/async.
6. Kiểm tra root cause của `CompletionException` và những wrapper khác.
7. Chạy test trước/ngoài/sau scope, nested calls, exception, executor và many concurrent users.
8. Kiểm tra các authorization decisions bằng test có Subject đúng, sai, null, hết hạn và giả mạo.

## 14. Dùng `jdeprscan` để phát hiện API deprecated

JDK có công cụ **`jdeprscan`** hỗ trợ rà soát class/JAR có gọi API deprecated. Ví dụ:

```bash
jdeprscan --release 24 path/to/legacy-app.jar
```

Đây là lệnh minh họa; thay đường dẫn JAR bằng **artifact của chính ứng dụng**. Nó có thể chỉ ra các dùng `AccessController`/`Subject.getSubject` hoặc API Java khác deprecated. **Không xem output trống là bằng chứng đã migrate hoàn toàn**, vì không phải mọi đường gọi động/reflection hoặc hành vi Security Manager đều được phát hiện bằng quét bytecode.

Trong kiểm thử local của chương trình `LegacySubjectDemo`, `jdeprscan --release 24` đã cảnh báo việc dùng `AccessController` và `Subject.getSubject`. Cần kết hợp với tìm kiếm mã nguồn và kiểm thử thực tế.

### 14.1. Các bước migrate cho dự án nhiều module

1. **Inventory:** liệt kê mọi lời gọi `doAs`, `doAsPrivileged`, `getSubject`, `AccessController`; xem dependencies/frameworks có dùng JAAS/GSS không.
2. **Version policy:** xác định minimum JDK. Nếu vẫn cần Java 17, không đưa thẳng `Subject.callAs` vào source được compile `--release 17`; có thể tách adapter theo runtime hoặc nâng minimum JDK có kế hoạch.
3. **Authentication boundary:** xác định nguồn `Subject` sau JAAS login; không chấp nhận Subject tự tạo từ user input.
4. **Context scope:** thay `doAs` bằng `callAs` khi chỉ cần binding, thay `getSubject(ACC)` bằng `current`.
5. **Authorization boundary:** chuyển mọi logic từng dựa vào Security Manager sang policy/IAM/ACL explicit.
6. **Concurrency:** rà soát thread pools, `CompletableFuture`, async RPC, reactive flows, structured concurrency; truyền Subject đúng cách, không rò.
7. **Exceptions:** sửa `PrivilegedActionException` sang `CompletionException`, giữ cause chính xác; test checked/unchecked failure.
8. **CI:** chạy `javac --release <minimum>`, `jdeprscan`, unit/integration tests trên JDK mục tiêu và negative security tests.
9. **Production rollout:** quan sát logs an toàn về authentication/authorization failures, bật rollback plan không hạ security policy, nâng dependencies trước khi đổi JDK diện rộng.

## 15. Lưu ý an toàn về credentials, Subject và quyền truy cập

### 15.1. `Subject.current()` không phải chứng thực mật mã

Không đánh giá một service là trusted chỉ vì nó trả `Subject.current() != null`. Đối tượng đó có thể được tự tạo từ các `Principal` bất kỳ. Authentication phải được tiến hành bởi JAAS LoginModule hoặc boundary tin cậy, và việc cấp quyền phải xét identity/role/scopes đã được verified.

### 15.2. Không lan truyền private credentials một cách tùy tiện

`Subject` có thể chứa **Kerberos tickets**, tokens, keys, certificates hoặc credentials khác. Khi capture và gửi `Subject` đến executor:

- Chỉ truyền khi task thật sự cần current subject và được ủy quyền.
- Không lưu đối tượng trong global static cache hoặc queue không có TTL.
- Không serialize `Subject` làm payload mạng chỉ để “giữ context”.
- Không in `Subject` hoặc các credentials trong debug log.
- Dọn/làm hết hiệu lực credentials đúng theo `LoginModule.logout` hoặc chính sách của technology.

### 15.3. Quyền không tăng nhờ nesting

Nếu một task không có quyền thực hiện thao tác, `Subject.callAs(adminSubject, ...)` do **code không được tin cậy** thực hiện không nên là cách vượt quyền. Một lớp authorization đúng phải bảo vệ **nguồn Subject, khả năng bind, quyền của workload và chính sách tài nguyên**, không chỉ đọc một chuỗi tên principal.

### 15.4. Thông điệp lỗi không được lộ credentials

`CompletionException.getCause()` đôi khi chứa chi tiết service hoặc authentication. Khi trả lỗi ra API, đừng phản hồi nguyên nội dung exception từ JAAS/LDAP/Kerberos vào client. Log an toàn theo correlation ID, trạng thái, module và mã lỗi; hạn chế tên user, tokens, paths và private credentials theo policy.

## 16. Bài tập tự kiểm tra

**Câu 1.** `Subject.current()` được thêm từ Java 17 hay Java 18?  
**Đáp án:** **Java 18**; `--release 17` không biên dịch code gọi phương thức này.

**Câu 2.** Sau khi `Subject.callAs(alice, action)` hoàn tất, current subject có mặc định vĩnh viễn là Alice không?  
**Đáp án:** **Không.** Nó được khôi phục về giá trị trước khi gọi, thường `null` nếu ngoài scope.

**Câu 3.** Lồng `Subject.callAs(bob, action)` vào trong scope Alice thì trong Bob và sau Bob có gì?  
**Đáp án:** Trong action Bob, `current()==bob`; sau action Bob và trước khi scope Alice kết thúc, `current()==alice`.

**Câu 4.** `callAs` có nhận `Subject` là `null` không?  
**Đáp án:** **Có.** Bên trong action current subject sẽ là `null`; scope bên ngoài được khôi phục sau đó. `action` thì không được `null`.

**Câu 5.** Một `Callable` ném `IOException`. Caller `callAs` bắt loại exception nào?  
**Đáp án:** **`CompletionException`** và lấy `IOException` gốc qua `getCause()`.

**Câu 6.** `doAs(PrivilegedExceptionAction)` cũng ném `CompletionException` trên JDK cũ?  
**Đáp án:** **Không.** Checked exception được bọc bằng `PrivilegedActionException`, đây là khác biệt quan trọng khi migrate.

**Câu 7.** Trên JDK 24, `Subject.doAs(subject, action)` có còn trong API không?  
**Đáp án:** **Có**, nhưng deprecated for removal; nó bind current subject theo scope, **không nâng đặc quyền Security Manager**.

**Câu 8.** Trên JDK 24, code `Subject.getSubject(AccessController.getContext())` nếu chưa có Subject sẽ trả `null`?  
**Đáp án:** **Không.** API này luôn ném `UnsupportedOperationException`, không phụ thuộc có Subject hay không.

**Câu 9.** Thread pool task submit bên trong `Subject.callAs(alice, ...)` có tự kế thừa Alice không?  
**Đáp án:** **Không được giả định.** Executor worker thông thường không tự mang current subject từ submitter; capture Subject đáng tin và bind lại khi thực thi.

**Câu 10.** `Subject.callAs` có đủ để chấp nhận một user truy cập tài khoản ngân hàng không?  
**Đáp án:** **Không.** Cần authentication chính thống và authorization theo user/tenant/resource/action; context binding chỉ là đầu vào.

**Câu 11.** Một `Subject` có principal tên `"admin"` là tự chứng minh đã được cấp role admin?  
**Đáp án:** **Không.** Tên principal phải đến từ nguồn đã xác thực và quyền do policy xác định; tạo `new Subject()` không phải login.

**Câu 12.** Khi migrate `doAsPrivileged`, có thể chỉ thay bằng `callAs` rồi coi hệ thống vẫn bảo vệ file bằng Java Security Manager không?  
**Đáp án:** **Không.** Security Manager không còn hỗ trợ từ JDK 24; phải thiết kế lại authorization/OS permissions/IAM.

**Câu 13.** Tại sao cần thử lỗi trong nested `callAs`?  
**Đáp án:** Để kiểm tra context được **khôi phục đúng kể cả khi action throw**, không rò danh tính sang request hoặc task khác.

**Câu 14.** Dùng `jdeprscan` không thấy cảnh báo thì có chắc code không còn vấn đề JAAS/Security Manager?  
**Đáp án:** **Không.** Vẫn phải kiểm tra dynamic/reflection calls, dependencies, permission semantics, concurrency và integration tests.

## 17. Nguồn tham khảo chính thức

- [Java SE 26 — Subject API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/security/auth/Subject.html): `current`, `callAs`, `doAs`, `getSubject`, version và exception semantics.
- [Oracle — Migrating from Subject.getSubject/Subject.doAs to Subject.current/Subject.callAs](https://docs.oracle.com/en/java/javase/25/security/migrating-from-deprecated-removal-subject-getsubject-subject-doas-methods-subject-current-subject-callas-methods.html): migration và thay đổi sau JDK 24.
- [Oracle — Java Authentication and Authorization Service Reference Guide](https://docs.oracle.com/en/java/javase/24/security/java-authentication-and-authorization-service-jaas-reference-guide.html): JAAS authentication, Subject/Principals và giới hạn authorization hiện đại.
- [OpenJDK — JEP 486: Permanently Disable the Security Manager](https://openjdk.org/jeps/486): nguyên nhân thay đổi hành vi Java 24.
- [OpenJDK — JEP 411: Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411): bối cảnh từ Java 17.
- [Oracle — JDK 23 Release Notes, Subject API changes](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html): trạng thái Security Manager và cách Subject được truyền sang child threads.
- [Java SE 26 — LoginContext](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/security/auth/login/LoginContext.html): tạo `Subject` từ cơ chế JAAS login.
- [Oracle — jdeprscan](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jdeprscan.html): quét bytecode để nhận diện các API deprecated.

### Ghi nhớ

**`Subject.current()` đọc danh tính đang được gắn với scope; `Subject.callAs(subject, action)` chỉ bind trong khoảng chạy action và tự khôi phục sau đó.** Hai API được thêm từ **Java 18**. Code cũ dùng **`doAs`** cần migrate vì deprecated; đặc biệt, **`getSubject(AccessController.getContext())` luôn ném `UnsupportedOperationException` từ JDK 24**. Đừng mang tư duy Security Manager permissions sang `callAs`: **authentication, context propagation và authorization là ba trách nhiệm khác nhau**, cần kiểm soát nguồn `Subject`, ràng buộc thread/task và quyền tài nguyên một cách tường minh.
