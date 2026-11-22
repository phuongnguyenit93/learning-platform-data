# Thực hành tổng hợp: Mô phỏng lỗi khởi tạo, xử lý và đóng tài nguyên trong Java

Một tác vụ Java thường có ba giai đoạn liên tiếp: **khởi tạo/mở tài nguyên → xử lý công việc → đóng/giải phóng tài nguyên**. Ví dụ: mở file rồi đọc dữ liệu và đóng stream; tạo kết nối rồi chạy truy vấn và đóng kết nối; mở kênh truyền rồi gửi dữ liệu và đóng kênh. Lỗi có thể xảy ra ở **bất kỳ giai đoạn nào**, kể cả khi chương trình đang cố dọn dẹp sau một lỗi trước đó.

Vấn đề quan trọng không chỉ là “có gọi `close()` hay không”, mà còn là **đã mở được bao nhiêu tài nguyên**, **đóng theo thứ tự nào**, **lỗi nào được báo ra như nguyên nhân chính**, và **các lỗi dọn dẹp thứ cấp có bị mất hay không**.

Trong Java 17+ và các phiên bản Java hiện đại, cách tiếp cận mặc định cho tài nguyên có vòng đời theo phạm vi là **`try-with-resources`** kết hợp `AutoCloseable` hoặc `Closeable`. Cơ chế này hiện vẫn được hỗ trợ và được đặc tả trong Java Language Specification (JLS `14.20.3). Bài thực hành sẽ **cố ý chèn lỗi ở ba giai đoạn** để quan sát chính xác hành vi JVM.

## 1. Mục tiêu sau bài học

Sau khi hoàn thành, bạn có thể:

1. Dùng `try-with-resources` để bảo đảm đóng các tài nguyên **đã khởi tạo thành công**, kể cả khi phần xử lý ném exception.
2. Giải thích được vì sao nhiều tài nguyên **khởi tạo từ trái sang phải** nhưng **đóng từ phải sang trái**.
3. Xác định tài nguyên nào cần đóng khi **khởi tạo tài nguyên thứ hai bị lỗi** và vì sao phần thân `try` không chạy.
4. Phân biệt **primary exception** với **suppressed exceptions** khi cả xử lý và đóng tài nguyên đều lỗi.
5. Chứng minh rằng nếu `close()` của một tài nguyên lỗi, các tài nguyên còn lại vẫn được **thử đóng**.
6. Viết mô phỏng có kết quả xác định để kiểm thử nhiều tình huống lỗi mà **không cần truy cập file, database hoặc mạng thật**.
7. Áp dụng quy tắc quản lý **ownership** và xử lý lỗi dọn dẹp khi xây dựng các resource thực tế.

## 2. Nền tảng: vòng đời tài nguyên và các quy tắc JVM bảo đảm

`AutoCloseable` là interface có phương thức `close()`. Bất kỳ đối tượng nào thuộc kiểu triển khai `AutoCloseable` có thể được khai báo ở phần đầu `try (...)` để Java tự gọi `close()` khi rời phạm vi.

Ví dụ cơ bản:

```java
try (var input = java.nio.file.Files.newBufferedReader(path)) {
    // Đọc file bằng input.
} // Java tự gọi input.close() tại đây.
```

Đây là **đoạn minh họa**, cần có biến `path` thuộc kiểu `java.nio.file.Path` để tích hợp vào chương trình thực tế. Khi cần mở nhiều tài nguyên:

```java
try (Resource a = openA();
     Resource b = openB()) {
    use(a, b);
}
```

Đoạn mã trên là **giả mã Java mô tả thứ tự**, trong đó `Resource`, `openA`, `openB` và `use` biểu thị những kiểu/hàm do ứng dụng tự định nghĩa. Quy tắc thực thi của Java là:

- **Khởi tạo từ trái sang phải**: thử mở `a` trước, sau đó `b`.
- **Chỉ vào thân `try` khi toàn bộ khai báo tài nguyên hoàn thành**.
- **Khi rời thân `try`**, Java gọi `close()` trên các tài nguyên đã khởi tạo thành công theo **thứ tự ngược**: `b.close()` rồi `a.close()`.
- **Nếu `openB()` ném exception**, thân `try` không chạy; Java vẫn gọi `a.close()` vì `a` đã mở thành công. Không có đối tượng `b` hoàn chỉnh được ràng buộc trong header để Java gọi `b.close()`.
- **Nếu một lần `close()` ném exception**, Java vẫn thử đóng những tài nguyên trước đó.
- **Nếu một lỗi đã tồn tại** do khởi tạo hoặc xử lý, lỗi phát sinh khi đóng tài nguyên được gắn vào lỗi trước bằng cơ chế **suppression**; lỗi ban đầu tiếp tục là lỗi chính.
- **Nếu thân `try` chạy thành công nhưng cả hai lần đóng đều lỗi**, lỗi từ lần đóng **đầu tiên** (với hai tài nguyên A, B thì là `B.close()`) là lỗi chính; lỗi của `A.close()` được lưu dưới dạng suppressed.
- Tài nguyên có giá trị `null` sẽ không được gọi `close()`; việc dùng `null` giả làm tài nguyên thường không cần thiết và dễ khiến mã khó hiểu.
- `catch` và `finally` gắn với câu lệnh `try-with-resources` chạy **sau các nỗ lực đóng tài nguyên**.

Các quy tắc này do ngôn ngữ Java bảo đảm, không phụ thuộc vào việc bạn dùng JDK 17, 21, 25 hay các phiên bản hiện hành khác.

### 2.1. “Được thử đóng” khác “đã giải phóng thành công”

`try-with-resources` **bảo đảm thực hiện lời gọi `close()`** theo quy tắc trên; nó không thể bảo đảm một thiết bị mạng đã đóng hoàn toàn, dữ liệu đã ghi thành công hoặc tác vụ commit đã hoàn tất khi `close()` ném exception.

Tài nguyên mô phỏng trong bài sẽ đánh dấu trạng thái `closed` trước khi ném lỗi, nhưng đó là **hành vi được lập trình trong lớp mô phỏng**, không phải bảo đảm chung của mọi thư viện. Trong code thật, người viết `close()` nên ưu tiên giải phóng tài nguyên nền và cập nhật trạng thái nội bộ trước khi báo lỗi nếu có thể.

## 3. Bài mô phỏng đầy đủ bằng Java 17+

Chương trình sau thiết kế `DemoResource` có đủ ba “điểm chèn lỗi”:

- **`failOnOpen`**: lỗi xảy ra khi yêu cầu tạo/mở tài nguyên;
- **`failOnWork`**: lỗi xảy ra trong quá trình xử lý;
- **`failOnClose`**: lỗi xảy ra trong phương thức `close()`.

Mỗi hành động sẽ in một dòng sự kiện. Bốn kịch bản cho thấy thứ tự thực tế và cách Java chọn lỗi chính/suppressed.

Lưu nguyên vẹn mã vào tệp **`ResourceFailuresDemo.java`**:

```java
import java.io.IOException;

public final class ResourceFailuresDemo {

    static final class DemoResource implements AutoCloseable {
        private final String name;
        private final boolean failOnClose;
        private boolean closed;

        private DemoResource(String name, boolean failOnClose) {
            this.name = name;
            this.failOnClose = failOnClose;
        }

        // Mô phỏng giai đoạn khởi tạo / mở tài nguyên.
        static DemoResource open(
                String name,
                boolean failOnOpen,
                boolean failOnClose) throws IOException {

            System.out.println("open " + name);
            if (failOnOpen) {
                throw new IOException("open " + name + " failed");
            }
            return new DemoResource(name, failOnClose);
        }

        // Mô phỏng giai đoạn dùng tài nguyên.
        void process(boolean failOnWork) throws IOException {
            System.out.println("work " + name);
            if (failOnWork) {
                throw new IOException("work " + name + " failed");
            }
        }

        // Mô phỏng giai đoạn đóng tài nguyên.
        @Override
        public void close() throws IOException {
            if (closed) {
                return;
            }

            closed = true;
            System.out.println("close " + name);

            if (failOnClose) {
                throw new IOException("close " + name + " failed");
            }
        }
    }

    static void scenario(
            String label,
            boolean failOpenB,
            boolean failWork,
            boolean failCloseA,
            boolean failCloseB) {

        System.out.println("== " + label + " ==");

        // A mở trước B; khi đóng, B được thử trước A.
        try (DemoResource a =
                     DemoResource.open("A", false, failCloseA);
             DemoResource b =
                     DemoResource.open("B", failOpenB, failCloseB)) {

            a.process(failWork);
            b.process(false);
            System.out.println("body ok");

        } catch (IOException error) {
            System.out.println(
                    "primary: " + error.getMessage());

            // Các lỗi khi đóng không nhất thiết bị mất.
            for (Throwable suppressed : error.getSuppressed()) {
                System.out.println(
                        "suppressed: " + suppressed.getMessage());
            }
        }
    }

    public static void main(String[] args) {
        // 1. Mở, xử lý và đóng đều thành công.
        scenario("success", false, false, false, false);

        // 2. B không mở được; A vẫn phải được thử đóng.
        //    A.close() cũng được cấu hình ném IOException.
        scenario("init B fails", true, false, true, false);

        // 3. Work trên A lỗi; close(B) và close(A) đều lỗi.
        scenario("work fails", false, true, true, true);

        // 4. Work thành công; close(B) rồi close(A) đều lỗi.
        scenario("close fails", false, false, true, true);
    }
}
```

**Biên dịch và chạy:**

```bash
javac -encoding UTF-8 ResourceFailuresDemo.java
java ResourceFailuresDemo
```

Chương trình chỉ sử dụng thư viện tiêu chuẩn của Java; không cần file, mạng, database, framework hoặc tham số dòng lệnh.

### 3.1. Kết quả stdout chính xác

```text
== success ==
open A
open B
work A
work B
body ok
close B
close A
== init B fails ==
open A
open B
close A
primary: open B failed
suppressed: close A failed
== work fails ==
open A
open B
work A
close B
close A
primary: work A failed
suppressed: close B failed
suppressed: close A failed
== close fails ==
open A
open B
work A
work B
body ok
close B
close A
primary: close B failed
suppressed: close A failed
```

Đây là kết quả **xác định bởi luồng điều khiển và cờ mô phỏng** trong ví dụ, không phụ thuộc vào tốc độ CPU, GC hay mạng. Lệnh `javac` không in gì nếu biên dịch thành công; lệnh `java` in các dòng trên.

## 4. Phân tích từng kịch bản

### 4.1. Kịch bản 1 — Không có lỗi

```text
open A -> open B -> work A -> work B
       -> body ok -> close B -> close A
```

Ở đây mọi khai báo tài nguyên đều thành công nên `try` thực thi đầy đủ. Khi thân `try` kết thúc, Java tự động gọi `close()` trên B rồi A. Vì không có exception, `catch` không chạy.

**Điểm cần nhớ:** thứ tự đóng là **LIFO** (*last in, first out*) đối với các resource đã khởi tạo. Với ba tài nguyên A, B, C, thứ tự thông thường là C → B → A.

### 4.2. Kịch bản 2 — Lỗi khởi tạo B, đồng thời A đóng lỗi

```text
open A -> open B (ném IOException)
       -> close A (ném IOException)
       -> primary: open B failed
       -> suppressed: close A failed
```

Phần thân `try` không hề bắt đầu: không có `work A`, `work B` hoặc `body ok`. A đã được tạo thành công nên Java phải thử đóng A. B đang lỗi trong quá trình `open(...)` và chưa tạo ra một resource `b` hợp lệ để đưa vào header, nên **không có `close B`**.

Khi `A.close()` cũng lỗi, Java **giữ lỗi `open B failed` làm primary**; `close A failed` là suppressed. Điều này giữ được thông tin “vì sao tác vụ thất bại ban đầu” mà không bỏ mất sự cố dọn dẹp.

**Bài học về khởi tạo một phần:** `try-with-resources` chỉ tự đóng các tài nguyên đã được khai báo/khởi tạo thành công trước điểm lỗi. Nếu một constructor hoặc factory đã mở tài nguyên ở bên trong rồi ném exception **trước khi trả ra đối tượng**, code của constructor/factory phải tự dọn phần tài nguyên nội bộ mà nó vừa cấp phát. `try-with-resources` của caller không thể đóng một đối tượng chưa được trả về.

### 4.3. Kịch bản 3 — Xử lý lỗi, cả hai lần đóng cũng lỗi

```text
open A -> open B -> work A (ném IOException)
       -> close B (ném IOException)
       -> close A (ném IOException)
       -> primary: work A failed
       -> suppressed: close B failed
       -> suppressed: close A failed
```

Đây là kịch bản thể hiện giá trị quan trọng nhất của `try-with-resources`:

1. `a.process(true)` ném `IOException("work A failed")`.
2. Câu lệnh `b.process(false)` và `System.out.println("body ok")` **không chạy**.
3. Khi thoát `try`, Java gọi `B.close()` trước dù thân `try` bị lỗi.
4. `B.close()` lỗi, nhưng **không ngăn** Java thử `A.close()`.
5. `A.close()` cũng lỗi.
6. Lỗi khi xử lý **vẫn là primary**; hai lỗi dọn dẹp được giữ trong mảng của `getSuppressed()` theo thứ tự phát sinh trong quá trình đóng.

Nếu code bỏ qua suppressed exceptions, người vận hành có thể chỉ nhìn thấy lỗi “work A failed” và không biết rằng **cả B và A đều không đóng bình thường**.

### 4.4. Kịch bản 4 — Xử lý thành công, chỉ đóng thất bại

```text
open A -> open B -> work A -> work B -> body ok
       -> close B (ném IOException)
       -> close A (ném IOException)
       -> primary: close B failed
       -> suppressed: close A failed
```

Phần công việc hoàn tất, nhưng việc đóng tài nguyên thất bại. Vì không có lỗi trước đó, **lỗi đầu tiên xuất hiện lúc đóng** (`B.close()`) trở thành primary. Lỗi khi đóng A được thêm vào suppressed.

**Quan trọng:** “đã in `body ok`” không có nghĩa mọi công việc I/O chắc chắn thành công. Với một số tài nguyên ghi, chính thao tác `close()` có thể đẩy dữ liệu còn trong buffer hoặc thông báo lỗi hoàn tất; vì vậy thất bại trong `close()` phải được ghi nhận và xử lý phù hợp. Trong hệ thống có transaction, **`close()` không thay thế `commit()`**; phải thiết kế transaction semantics riêng.

## 5. Bảng dự đoán lỗi trước khi chạy

| Tình huống | Thân `try` có chạy? | Thứ tự `close()` được thử | Primary exception | Suppressed |
| --- | --- | --- | --- | --- |
| A, B và work đều thành công | Có, đầy đủ | B → A | Không có | Không có |
| Mở A thất bại ngay từ đầu | Không | Không có resource trong header đã mở | Lỗi mở A | Không có từ header |
| Mở A thành công, mở B thất bại | Không | A | Lỗi mở B | Lỗi A.close nếu có |
| Thân `try` lỗi, close bình thường | Có, nhưng dừng ở điểm lỗi | B → A | Lỗi trong thân | Không |
| Thân `try` lỗi, B.close và A.close lỗi | Có, nhưng dừng ở điểm lỗi | B → A | Lỗi trong thân | Lỗi B.close, A.close |
| Thân `try` thành công, B.close và A.close lỗi | Có, đầy đủ | B → A | Lỗi B.close | Lỗi A.close |
| Thân `try` thành công, chỉ A.close lỗi | Có, đầy đủ | B → A | Lỗi A.close | Không |

Nếu một resource trong header có giá trị `null`, nó không được đóng. **Bảng giả định các resource được mở thành công luôn khác `null`.**

## 6. Primary, suppressed và cause: ba khái niệm khác nhau

Trong Java, một đối tượng `Throwable` có thể mang nhiều thông tin lỗi:

- **Primary exception**: đối tượng exception đang được ném ra ngoài `try-with-resources`, bắt trong `catch`.
- **Suppressed exceptions**: các lỗi thứ cấp phát sinh trong quá trình dọn dẹp tài nguyên khi một lỗi trước đó đã là primary; lấy bằng `error.getSuppressed()`.
- **Cause**: lỗi nguyên nhân được gắn khi bọc/chuyển đổi exception, lấy bằng `error.getCause()`. Nó biểu diễn quan hệ nguyên nhân, **không phải cùng cơ chế** với suppressed.

Ví dụ độc lập, dùng khi một lớp muốn giữ ngữ cảnh nghiệp vụ:

```java
try {
    // Thao tác có thể ném IOException.
} catch (java.io.IOException cause) {
    throw new IllegalStateException(
            "Không thể hoàn thành thao tác đọc/ghi", cause);
}
```

Đây là **đoạn minh họa** trong một phương thức có thân xử lý thực tế. Việc tạo exception mới với `cause` nêu ngữ cảnh nghiệp vụ mà không đánh mất stack trace gốc. Nếu lỗi gốc có suppressed exceptions, chúng vẫn nằm trên exception `cause`; muốn kiểm tra phải xem cause và suppressed ở đúng cấp.

Khi cần log đầy đủ, `Throwable.printStackTrace()` hoặc logging framework chuẩn của hệ thống thường có khả năng thể hiện cả **cause** và **suppressed**. Với bài tập, ta in `getMessage()` và `getSuppressed()` trực tiếp để dễ kiểm chứng. Không nên chỉ log `error.getMessage()` trong production rồi bỏ qua stack trace và các lỗi bị suppressed.

### 6.1. Thứ tự xuất hiện trong `getSuppressed()`

Khi phần thân `try` đã có primary và việc đóng B, A lần lượt lỗi, `getSuppressed()` thường chứa **B.close trước rồi A.close**, như stdout của bài. Điều này giúp suy ra thứ tự đóng và nguồn lỗi.

Lưu ý rằng mảng suppressed **không thay thế** trách nhiệm xử lý từng lỗi. Không nên cộng gộp các message thành một exception mới rồi bỏ mất các đối tượng Throwable gốc, trừ khi có một chiến lược chuyển đổi exception được thiết kế rõ ràng.

### 6.2. Tại sao `finally` tự viết dễ mắc lỗi?

Đoạn mã sau **không phải cách khuyến nghị** để quản lý các resource triển khai `AutoCloseable`:

```java
DemoResource a = DemoResource.open("A", false, false);
DemoResource b = DemoResource.open("B", false, true);
try {
    a.process(true);
} finally {
    b.close(); // Nếu dòng này ném exception, a.close() sẽ bị bỏ qua.
    a.close();
}
```

Đoạn này **chỉ minh họa lỗi thiết kế** và cần đặt trong ngữ cảnh lớp `ResourceFailuresDemo` có khai báo `DemoResource`. Nó cũng bỏ qua việc bảo vệ A nếu mở B thất bại trước khi vào `try`. Khi `b.close()` ném exception trong `finally`, lời gọi `a.close()` phía sau không chạy; lỗi dọn dẹp còn có thể che mất lỗi xử lý ban đầu.

Với resource có phạm vi rõ ràng, thay bằng:

```java
try (DemoResource a = DemoResource.open("A", false, false);
     DemoResource b = DemoResource.open("B", false, true)) {
    a.process(true);
}
```

Đây cũng là đoạn **minh họa đặt trong lớp demo** và có thể cần khai báo/lan truyền `IOException` theo chữ ký phương thức chứa nó. `try-with-resources` bảo đảm các nỗ lực đóng và lưu các lỗi liên quan đúng theo đặc tả.

## 7. Thiết kế `AutoCloseable` đúng và an toàn

Trong bài, `DemoResource.close()` được viết có chủ ý:

```java
@Override
public void close() throws IOException {
    if (closed) {
        return;
    }
    closed = true;
    System.out.println("close " + name);
    if (failOnClose) {
        throw new IOException("close " + name + " failed");
    }
}
```

Đây là phương thức **minh họa** nằm bên trong `DemoResource`, không phải chương trình chạy riêng. Các nguyên tắc quan trọng:

1. **Khai báo exception cụ thể.** `AutoCloseable.close()` cho phép ném `Exception`, nhưng khi tự thiết kế nên khai báo kiểu chuyên biệt như `IOException` hoặc không ném checked exception nếu không cần. `java.io.Closeable` kế thừa `AutoCloseable` và khai báo `close() throws IOException`.
2. **Định nghĩa ownership rõ ràng.** Bên nào sở hữu tài nguyên có trách nhiệm đóng nó. Hai nơi cùng gọi `close()` trên stream kết nối hoặc wrapper có thể gây hành vi không mong muốn.
3. **Bảo vệ trạng thái sau close.** Mô phỏng có biến `closed` để tránh thực hiện lại. Theo `AutoCloseable`, không phải mọi implementation bắt buộc idempotent; đừng phụ thuộc vào khả năng gọi `close()` lặp lại nếu tài liệu API không hứa.
4. **Ưu tiên dọn trước khi báo lỗi.** Nếu có thể, giải phóng tài nguyên bên dưới và đánh dấu trạng thái đóng trước khi ném lỗi. Mã demo chỉ mô phỏng hành vi này; trong thực tế, lỗi trả từ hệ điều hành có thể để trạng thái kết nối khó xác định.
5. **Không ném `InterruptedException` từ `close()` tùy tiện.** Tài liệu `AutoCloseable` cảnh báo điều này có thể tương tác sai với trạng thái interrupt khi exception bị suppressed. Cần thiết kế riêng cho tác vụ hủy/interrupt.
6. **Không giấu lỗi close bằng catch rỗng.** Nếu phải dọn dẹp nhiều tài nguyên hoặc có bước phục hồi, lưu lại mọi lỗi cần điều tra.
7. **Đối với tài nguyên phụ thuộc nhau**, đặt thứ tự khai báo đúng để thứ tự đóng ngược tương ứng với phụ thuộc. Ví dụ wrapper tạo sau stream nền thường cần được đóng trước; nếu wrapper.close() đã sở hữu và tự đóng stream nền thì tránh đăng ký/đóng hai lần không chủ ý.

### Trường hợp constructor thất bại sau khi cấp phát nội bộ

Ví dụ một factory thực tế làm hai việc:

```text
1. Mở socket thành công.
2. Xây dựng parser dùng socket -> ném exception.
3. Factory không trả được resource parser cho caller.
```

`try-with-resources` ở **caller** chưa nhận được parser nên không thể tự gọi `parser.close()`. Factory phải tự bảo vệ tài nguyên được tạo trong quá trình xây dựng. Một mẫu đơn giản (ví dụ độc lập về mở stream) là:

```java
static java.io.BufferedReader openReader(
        java.nio.file.Path path) throws java.io.IOException {
    // newBufferedReader tự sở hữu quá trình mở của chính nó;
    // caller sẽ sở hữu BufferedReader trả về.
    return java.nio.file.Files.newBufferedReader(path);
}
```

Khi factory cần thực hiện **nhiều bước cấp phát**, hãy có một phạm vi `try-with-resources` nội bộ cho resource đã mở, và chỉ bàn giao ownership sau khi bước khởi tạo hoàn thành thành công. Nếu thực sự chuyển quyền sở hữu từ một resource tạm sang đối tượng trả về, thiết kế tránh việc phạm vi nội bộ đóng nó trước khi trả về; mô hình đó cần được kiểm tra cẩn thận theo contract của thư viện.

## 8. Xử lý resource thực tế: ví dụ đọc file

Chương trình mô phỏng là trọng tâm của bài vì kết quả hoàn toàn xác định. Trong ứng dụng thực, `try-with-resources` được áp dụng trực tiếp cho reader:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ReadFirstLine {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("data.txt");

        try (BufferedReader reader =
                     Files.newBufferedReader(path)) {
            String firstLine = reader.readLine();
            System.out.println(firstLine);
        }
    }
}
```

**Lưu thành tệp `ReadFirstLine.java`** nếu muốn tự thử trên một file hiện có; nội dung và đường dẫn `data.txt` do người học cung cấp, nên stdout **không được khẳng định cố định**. `Files.newBufferedReader(path)` có thể ném `IOException` khi mở; `readLine()` có thể ném `IOException` trong lúc đọc; `close()` cũng có thể ném `IOException`. Nếu lỗi xảy ra khi đọc, `try-with-resources` vẫn thử đóng reader, và lỗi từ close sẽ là suppressed của lỗi đọc nếu cả hai cùng phát sinh.

Chạy khi đã chuẩn bị tệp:

```bash
javac -encoding UTF-8 ReadFirstLine.java
java ReadFirstLine
```

**Lưu ý dữ liệu và transaction:** không tự xem `close()` là đồng nghĩa với flush thành công, dữ liệu bền vững trên đĩa hoặc transaction đã commit. Với file ghi, network, JDBC và transaction, kiểm tra contract của từng API để xác định cần `flush()`, `commit()`, rollback, hoặc đổi tên file tạm theo cách an toàn. `try-with-resources` quản lý vòng đời tài nguyên, **không tự bảo đảm atomicity của nghiệp vụ**.

## 9. Các bài tập mở rộng có thể tự thực hiện

### Bài tập A — Mở A thất bại ngay

Sửa phương thức `scenario(...)` để nhận thêm cờ `failOpenA`, rồi truyền cờ đó vào `DemoResource.open("A", ...)`.

**Dự đoán:** stdout của case này chỉ có `open A`, rồi dòng primary của lỗi mở A. Vì chưa resource nào được khởi tạo thành công trong header, không có `close A` hoặc `close B`. Không có suppressed do close trong header.

### Bài tập B — Chỉ A.close lỗi

Gọi:

```java
scenario("close A only", false, false, true, false);
```

Đây là **dòng gọi bổ sung** bên trong `main` của chương trình đã cho, không phải một tệp độc lập.

**Dự đoán:** mở A/B, xử lý A/B, in `body ok`, đóng B thành công, đóng A ném lỗi. Primary là `close A failed` và `getSuppressed()` rỗng.

### Bài tập C — Chỉ lỗi xử lý

Gọi:

```java
scenario("work only", false, true, false, false);
```

**Dự đoán:** `open A`, `open B`, `work A`; sau đó Java đóng B và A bình thường. Primary là `work A failed` và không có suppressed. Điều này cho thấy `try-with-resources` hoạt động ngay cả khi cleanup thành công.

### Bài tập D — B đóng lỗi, A đóng thành công

Gọi:

```java
scenario("close B only", false, false, false, true);
```

**Dự đoán:** quá trình xử lý thành công. `close B` ném lỗi rồi `close A` vẫn được gọi; primary `close B failed` và không có suppressed.

### Bài tập E — Thử ba tài nguyên

Thêm resource C vào header:

```java
try (DemoResource a = DemoResource.open("A", false, false);
     DemoResource b = DemoResource.open("B", false, true);
     DemoResource c = DemoResource.open("C", false, true)) {
    System.out.println("body ok");
}
```

Đoạn này là **bài tập tích hợp**, cần xử lý `IOException` trong phương thức chứa nó.

**Dự đoán:** mở A → B → C; sau `body ok`, đóng C → B → A. Lỗi `close C failed` trở thành primary; lỗi `close B failed` bị suppressed; A vẫn được đóng.

### Bài tập F — Khẳng định tính đúng đắn bằng test

Không chỉ xem stdout bằng mắt; đối với bài tập kiểm thử tự động, bạn có thể:

1. Dùng một `List<String>` để ghi sự kiện mở/xử lý/đóng thay vì in trực tiếp.
2. Kiểm tra rằng thứ tự trong case thành công là `open A, open B, work A, work B, body ok, close B, close A`.
3. Với lỗi mở B, khẳng định **không có `work A` hoặc `close B`** trong danh sách, và `close A` có mặt.
4. Với lỗi xử lý đồng thời lỗi close, khẳng định exception chính vẫn có message `work A failed`; `getSuppressed().length == 2` và nội dung lần lượt là lỗi đóng B, A.
5. Khẳng định việc đóng resource đầu tiên thất bại **không ngăn** resource còn lại được thử đóng.

Có thể dùng JUnit trong dự án thật, nhưng bài thực hành chính chạy được với **JDK thuần**, không yêu cầu framework kiểm thử.

## 10. Những lỗi lập trình thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Mở hai tài nguyên trước khi bắt đầu `try` | Nếu mở tài nguyên thứ hai lỗi, tài nguyên thứ nhất có thể bị rò rỉ | Đặt cả hai trong header `try (...)` |
| Gọi `close()` nối tiếp trong một `finally` không tự bảo vệ | Lỗi close đầu tiên có thể bỏ qua các close sau | Dùng `try-with-resources` |
| Chỉ xem `getMessage()` của exception chính | Mất chi tiết lỗi đóng thứ cấp | Log stack trace và suppressed |
| Nhầm `getCause()` với `getSuppressed()` | Chẩn đoán sai quan hệ lỗi | Dùng cause cho exception wrapping; suppressed cho các lỗi thứ cấp |
| Cho rằng lỗi mở B làm B được đóng tự động | B chưa khởi tạo thành resource hợp lệ | Chỉ các resource đã khởi tạo thành công được tự đóng |
| Cho rằng lỗi xử lý làm dừng toàn bộ cleanup | Có thể dẫn đến bỏ resource | TWR vẫn thử đóng các resource đã mở |
| Cho rằng `body ok` nghĩa là I/O kết thúc thành công | `close()` có thể phát hiện lỗi ghi/flush | Xử lý exception từ close, theo contract của resource |
| Gọi `close()` thủ công trong thân `try` rồi để TWR tự đóng lần nữa | Có thể tạo close lặp ngoài ý muốn | Phân định quyền sở hữu; để TWR đóng đúng một lần theo phạm vi |
| Đánh giá sự thành công chỉ dựa trên việc hết exception | Các hệ thống ngoài JVM có thể có transaction/side effect riêng | Đảm bảo các quy tắc commit, rollback, retry riêng biệt |
| Dùng `catch (Exception ignored) {}` | Che mất lỗi quan trọng, làm khó phục hồi | Xử lý, log hoặc truyền exception đúng ngữ cảnh |

## 11. Checklist QA cuối bài

Trước khi coi chương trình quản lý tài nguyên an toàn, tự trả lời:

- [ ] Mỗi tài nguyên có ownership và phạm vi sống rõ ràng?
- [ ] Tài nguyên được đưa vào `try-with-resources` ngay khi caller thực sự nhận ownership?
- [ ] Khởi tạo nhiều resource theo thứ tự phù hợp với việc đóng ngược?
- [ ] Thử kịch bản khởi tạo resource thứ hai thất bại và xác minh resource thứ nhất vẫn được đóng?
- [ ] Khi xử lý lỗi, có thử đóng tất cả resource đã mở?
- [ ] Có quan sát/ghi nhận `getSuppressed()` nếu cả body và close cùng ném lỗi?
- [ ] Khi phần xử lý thành công mà `close()` lỗi, lỗi dọn dẹp có được báo ra?
- [ ] Factory/constructor có tự dọn tài nguyên cấp phát nội bộ nếu thất bại trước khi trả resource?
- [ ] `close()` có tính đến khả năng lỗi giữa các bước và trạng thái sau lỗi?
- [ ] Có phân biệt “đã đóng resource” với “đã commit giao dịch/lưu dữ liệu bền vững”?
- [ ] Các test xử lý exception không phụ thuộc thời điểm, thứ tự thread hoặc trạng thái hệ thống ngoài?
- [ ] Đã đọc API contract hiện hành của resource thật thay vì giả định mọi `close()` đều giống nhau?

## Kết luận

Khi mô phỏng lỗi ở **khởi tạo**, **xử lý** và **đóng**, `try-with-resources` cho thấy ba bảo đảm quan trọng của Java hiện đại: **chỉ các tài nguyên đã khởi tạo thành công mới được tự đóng; nhiều tài nguyên được thử đóng theo thứ tự ngược; các lỗi dọn dẹp không làm mất lỗi chính mà được giữ bằng suppressed exceptions**. Nếu chỉ có lỗi khi đóng, lỗi đóng đầu tiên trở thành primary. Điều quan trọng nhất khi áp dụng vào file, socket, JDBC hoặc resource tự định nghĩa là **thiết kế ownership rõ ràng, không bỏ qua lỗi close, và xử lý transaction/độ bền dữ liệu bằng contract riêng**.

## Tài liệu tham khảo hiện hành

- [Java Language Specification SE 25 — `14.20.3, try-with-resources](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.20.3): quy tắc khởi tạo trái → phải, đóng ngược, xử lý initializer/body/close exception và suppression.
- [AutoCloseable — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/AutoCloseable.html): contract `close()`, các lưu ý thiết kế resource và loại exception.
- [Throwable — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Throwable.html): `getSuppressed()`, `addSuppressed()`, `getCause()` và `printStackTrace()`.
- [Files — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): cách mở `BufferedReader` trong các ứng dụng đọc file hiện đại.
