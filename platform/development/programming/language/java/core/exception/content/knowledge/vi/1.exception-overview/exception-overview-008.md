# Phạm vi Java Core và cách đối chiếu phiên bản JDK khi học Exception

> Chủ đề: Java Core – Exception · Nhóm: Tổng quan. Nội dung áp dụng cho Java SE và JDK, với các mốc phiên bản được đối chiếu đến ngày 18/10/2026.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt phần kiến thức Exception thuộc ngôn ngữ Java, thư viện chuẩn Java SE, JVM và công cụ JDK.
2. Nhận diện phần nào là quy tắc cốt lõi tương đối ổn định, phần nào phụ thuộc phiên bản Java, bản vá hoặc môi trường chạy.
3. Đọc đúng tài liệu Java theo phiên bản; phân biệt phiên bản biên dịch, phiên bản API đích và phiên bản JVM chạy ứng dụng.
4. Tự kiểm chứng một ví dụ xử lý ngoại lệ trên nhiều JDK bằng lệnh cụ thể, không dựa vào suy đoán từ thông báo lỗi.

## 2. "Java Core" có nghĩa gì trong phạm vi Exception?

```text
Java Core (tên gọi học tập, không phải tên một đặc tả độc lập)
├── Java Language Specification (JLS)
│   └── throw, throws, try, catch, finally, checked/unchecked,
│       đa bắt ngoại lệ (multi-catch), try-with-resources
├── Java SE API
│   └── Throwable, Exception, Error, RuntimeException,
│       IOException, AutoCloseable, các API có thể phát sinh ngoại lệ
├── JVM / Java Virtual Machine Specification (JVMS)
│   └── nạp/chạy bytecode, khởi tạo lớp, lỗi liên kết lớp,
│       stack trace và hành vi runtime do đặc tả/quá trình triển khai chi phối
└── JDK
    └── javac, java, javap, tài liệu API, công cụ chẩn đoán
```

"Java Core" thường chỉ các nền tảng Java cần biết trước khi dùng framework; tên này **không** đồng nghĩa với một module, một bản phát hành hoặc một bộ đặc tả chính thức. Để đối chiếu hành vi Exception, cần xác định nó thuộc tầng nào:

| Tầng | Câu hỏi cần hỏi | Nguồn tra cứu phù hợp |
| --- | --- | --- |
| Cú pháp và kiểm tra lúc biên dịch | `throws` có bắt buộc không? `catch` có hợp lệ không? | JLS đúng phiên bản, đặc biệt chương về exceptions và `try` |
| Thư viện chuẩn | Phương thức có khai báo `throws IOException` không? | Java SE API docs theo phiên bản và đúng overload |
| JVM / runtime | Lỗi nạp lớp, stack trace, thông điệp `NullPointerException` ra sao? | JVMS, JEP, ghi chú phát hành và kiểm thử trên JVM đích |
| Công cụ | `javac --release` kiểm tra được điều gì? | Hướng dẫn `javac` của đúng JDK đang dùng |
| Thư viện ngoài/framework | Một API bọc ngoại lệ thành loại nào? | Tài liệu và phiên bản của chính thư viện đó |

Ví dụ, `java.io.IOException` là kiểu ngoại lệ thuộc API chuẩn; quy tắc buộc xử lý hoặc khai báo ngoại lệ checked là quy tắc ngôn ngữ; còn chuỗi trong `getMessage()` có thể phụ thuộc nơi phát sinh và phiên bản triển khai.

### Nội dung cốt lõi nên nắm

- Cây kế thừa `Throwable`; phân biệt checked exceptions, unchecked exceptions và `Error`.
- Cách ném (`throw`), khai báo (`throws`), bắt và lan truyền ngoại lệ; thứ tự `catch`, đa bắt ngoại lệ.
- `try`/`catch`/`finally`; `try-with-resources`, `AutoCloseable` và ngoại lệ bị suppressed khi đóng tài nguyên.
- Nguyên nhân (`getCause()`), ngoại lệ bị suppressed (`getSuppressed()`), stack trace; đóng gói ngoại lệ nhưng vẫn bảo toàn nguyên nhân.
- Ranh giới API: `IOException`, `NumberFormatException`, `ClassNotFoundException`, `InterruptedException`, `IllegalArgumentException` là những ví dụ quen thuộc. Các chính sách retry, HTTP error, giao dịch hay `DataAccessException` của Spring cần thêm hợp đồng riêng của framework/thư viện.

## 3. Những quy tắc Exception nền tảng

```text
java.lang.Throwable
├── java.lang.Error                       unchecked
│   └── ví dụ: LinkageError, OutOfMemoryError
└── java.lang.Exception
    ├── java.lang.RuntimeException        unchecked
    │   └── ví dụ: IllegalArgumentException, NullPointerException
    └── các nhánh checked
        └── ví dụ: IOException, ReflectiveOperationException
```

Theo JLS, một kiểu ngoại lệ là **checked** nếu nó thuộc `Throwable` nhưng **không** thuộc `RuntimeException`, `Error` hoặc các lớp con của chúng. Compiler yêu cầu xử lý hoặc khai báo các checked exception mà lời gọi/phương thức có thể ném theo quy tắc phân tích của Java. `RuntimeException` và `Error` (cùng các lớp con) là **unchecked**, nên không bị ràng buộc `catch`/`throws` này.

Cần phân biệt:

- `throw new IOException("...")` thực sự tạo và ném một đối tượng ngoại lệ; `throws IOException` chỉ khai báo khả năng phát sinh ra khỏi một phương thức hoặc constructor.
- Khi `catch (Exception e)`, các `RuntimeException` cũng có thể bị bắt, nhưng `Error` không phải lớp con `Exception`. Không nên bắt `Error` theo thói quen để "cứu" ứng dụng khỏi sự cố nghiêm trọng.
- Nếu có nhiều nhánh `catch`, nhánh cho kiểu con phải đứng trước nhánh bắt kiểu cha. Một nhánh không thể truy cập do nhánh trước đã bắt hết sẽ gây lỗi biên dịch.
- `finally` thường chạy khi rời `try`/`catch`, nhưng không được bảo đảm trong mọi tình huống như JVM chấm dứt đột ngột. Tránh `return` hoặc `throw` mới trong `finally` vì có thể che mất kết quả hoặc ngoại lệ gốc.
- Khi xử lý `InterruptedException`, chỉ bắt và bỏ qua thường là sai; hãy để nó lan lên hoặc cân nhắc khôi phục cờ ngắt bằng `Thread.currentThread().interrupt()` nếu không thể ném tiếp.
- Checked exception không có nghĩa lỗi "chắc chắn sẽ xảy ra"; unchecked exception không có nghĩa "không cần xử lý". Quyết định xử lý phụ thuộc hợp đồng của API và khả năng khôi phục.

Ví dụ minh họa hợp đồng biên dịch, **đây chỉ là đoạn phương thức, chưa phải chương trình độc lập**:

```java
import java.io.IOException;

static String readValue() throws IOException {
    throw new IOException("Không đọc được dữ liệu");
}

static void process() {
    try {
        System.out.println(readValue());
    } catch (IOException ex) {
        System.out.println("Đã xử lý: " + ex.getMessage());
    }
}
```

Nếu bỏ `catch` ở `process()`, phải khai báo `throws IOException` cho `process()` hoặc biên dịch sẽ lỗi. Không cần `throws` chỉ để ném `IllegalStateException` vì đó là unchecked exception. Không áp dụng cùng một suy luận cho mọi phiên bản của một phương thức API: phải đọc khai báo của đúng phiên bản.

## 4. Bảng mốc JDK có ý nghĩa với Exception

| Mốc Java SE / JDK | Điểm cần đối chiếu khi học Exception | Điều không nên kết luận quá mức |
| --- | --- | --- |
| 7 (2011) | `try-with-resources`; `AutoCloseable`; ngoại lệ suppressed; multi-catch (`catch (A \| B e)`), một số quy tắc suy luận kiểu ngoại lệ khi rethrow | Không phải tất cả tài nguyên đều tự đóng; chỉ đối tượng thích hợp với `AutoCloseable` trong cấu trúc quản lý tài nguyên |
| 8 (2014) | Các cơ chế Exception của Java 7 tiếp tục áp dụng; đây là mốc hệ thống cũ thường cần tương thích | Không mặc định được dùng API hay cú pháp xuất hiện ở Java 9+ |
| 9 (2017) | Có thể dùng biến `final` hoặc effectively final đã khai báo trong `try (resource)`; hệ module ảnh hưởng việc tìm/đọc lớp; `javac --release` ra đời | Không phải toàn bộ hành vi lỗi classpath/module là "Exception mới" |
| 11 (2018, LTS) | Mốc phổ biến khi kiểm tra tương thích ứng dụng; API chuẩn được bổ sung so với 8, ví dụ `Files.readString` từ Java 11 | Có API trên 11 không đồng nghĩa chạy được trên runtime 8 |
| 14 (2020) | JEP 358 bổ sung cơ chế helpful `NullPointerException` message, ban đầu cần bật tùy chọn VM | Nội dung message không phải giao diện ổn định để ứng dụng parse |
| 15 (2020) | Tùy chọn `ShowCodeDetailsInExceptionMessages` được bật mặc định trong HotSpot của JDK 15 | `new NullPointerException("...")` do người viết tạo không tự có mô tả biểu thức lỗi giống NPE do JVM sinh |
| 17 (2021, LTS) | Mốc baseline phổ biến để build/test Java hiện đại; những quy tắc lõi checked/unchecked vẫn tiếp tục | Đừng gán mọi thay đổi JDK 9–17 cho chính cú pháp `try/catch` |
| 21 (2023, LTS) | Mốc runtime LTS khác cần chạy lại test xử lý lỗi, API và dependency | Không suy ra mọi stack trace hay hành vi thư viện sẽ đồng nhất với 17 |
| 25 (2025, LTS) | Mốc LTS mới nhất tại 18/10/2026, có ý nghĩa khi chọn target dài hạn | "LTS" là cách hỗ trợ phát hành, không phải một loại cơ chế Exception |
| 27 (15/09/2026, feature release) | JDK GA mới nhất tại 18/10/2026; đối chiếu release notes và kiểm thử thực tế nếu dùng | Phiên bản mới nhất không tự động là lựa chọn triển khai phù hợp mọi tổ chức |

Các năm/mốc chỉ giúp chọn tài liệu; **không** thể thay cho việc xem JLS, API docs và release notes của cả phiên bản cụ thể lẫn bản cập nhật (ví dụ 17.0.x, 21.0.x). Bản phân phối Oracle JDK, OpenJDK hoặc nhà cung cấp khác cũng có chính sách hỗ trợ và cấu hình khác nhau.

### Những thay đổi thật sự đáng nhớ

**Java 7: nhiều ngoại lệ và quản lý tài nguyên an toàn hơn.** `try-with-resources` đóng tài nguyên theo thứ tự ngược với thứ tự mở; nếu phần thân `try` đã ném ngoại lệ, lỗi từ `close()` thường được gắn vào ngoại lệ gốc dưới dạng `suppressed`. `Throwable.getSuppressed()` đọc danh sách này. Multi-catch giảm lặp code khi các loại lỗi có cùng hướng xử lý; các kiểu trong cùng một multi-catch không được là quan hệ lớp cha–con.

**Java 9: tái sử dụng biến tài nguyên.** Từ Java 9, có thể viết `try (reader)` nếu `reader` là biến đã gán hợp lệ và không bị gán lại (final/effectively final). Trên Java 7/8, cần một khai báo tài nguyên trong dấu ngoặc, chẳng hạn `try (BufferedReader in = reader)`.

**Java 14/15: thông báo NPE hữu ích hơn.** HotSpot bổ sung thông tin về thao tác dereference null theo JEP 358. Java 14 có tùy chọn bật `-XX:+ShowCodeDetailsInExceptionMessages`; từ JDK 15 HotSpot bật mặc định. Thông điệp phụ thuộc bytecode và tình huống; NPE do tự khởi tạo, tắt tùy chọn hoặc bytecode thiếu thông tin có thể cho kết quả khác. Test nên khẳng định **kiểu ngoại lệ, cause, hành vi**, tránh so sánh cố định toàn bộ message.

**Các mốc LTS mới hơn:** Những quy tắc nòng cốt về `throw`, `throws`, `catch` và checked/unchecked không được định nghĩa lại mỗi kỳ phát hành. Tuy vậy, API, runtime, classpath/module, thư viện, cờ JVM, bản sửa lỗi và chi tiết diagnostic có thể thay đổi. Vì thế luôn tách "quy tắc ngôn ngữ" khỏi "hành vi cụ thể của ứng dụng".

## 5. Ví dụ chạy được từ Java 7+: primary và suppressed exception

Tạo tệp `ExceptionScopeDemo.java`:

```java
import java.io.IOException;

public class ExceptionScopeDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("close");
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("work");
            throw new IllegalStateException("work failed");
        } catch (Exception ex) {
            System.out.println("primary="
                    + ex.getClass().getSimpleName() + ": " + ex.getMessage());

            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("suppressed="
                        + suppressed.getClass().getSimpleName()
                        + ": " + suppressed.getMessage());
            }
        }
    }
}
```

Biên dịch/chạy trên một JDK hỗ trợ `--release 8` (ví dụ JDK 17):

```bash
javac --release 8 ExceptionScopeDemo.java
java ExceptionScopeDemo
```

Trên JDK 8 dùng `javac ExceptionScopeDemo.java` vì trình biên dịch JDK 8 chưa có `--release`. Đầu ra chuẩn chính xác:

```text
work
close
primary=IllegalStateException: work failed
suppressed=IOException: close failed
```

Diễn giải: `IllegalStateException` từ phần thân `try` là ngoại lệ chính; `close()` vẫn chạy và ném `IOException`; ngoại lệ khi đóng được gắn vào `getSuppressed()`, không xóa nguyên nhân lỗi gốc. Vì tự in loại và message thay cho toàn bộ stack trace, ví dụ cho output ổn định hơn giữa các phiên bản JDK. Đây không phải là ví dụ về `getCause()`: **cause** dùng cho quan hệ nguyên nhân khi bọc ngoại lệ, còn **suppressed** mô tả lỗi bổ sung, thường do đóng tài nguyên.

## 6. Ví dụ phân biệt cú pháp Java 8 và Java 9

Tạo tệp `ReuseResourceDemo.java` (yêu cầu Java 9+):

```java
import java.io.BufferedReader;
import java.io.StringReader;

public class ReuseResourceDemo {
    public static void main(String[] args) throws Exception {
        BufferedReader reader = new BufferedReader(new StringReader("hello"));
        try (reader) {
            System.out.println(reader.readLine());
        }
    }
}
```

```bash
javac --release 9 ReuseResourceDemo.java
java ReuseResourceDemo
```

```text
hello
```

Khi thử `javac --release 8 ReuseResourceDemo.java` trên trình biên dịch có hỗ trợ cả release 8 và 9, cú pháp `try (reader)` bị từ chối ở mức nguồn Java 8. Với Java 8, viết lại phần `try` như sau (chỉ là đoạn thay thế trong chương trình trên):

```java
try (BufferedReader managed = reader) {
    System.out.println(managed.readLine());
}
```

Phương thức `close()` vẫn hoạt động theo hợp đồng tài nguyên. Sự khác biệt ở đây thuộc **ngữ pháp được phép bởi phiên bản nguồn**, không phải chuyện `BufferedReader` được phát minh ở Java 9.

## 7. Phân biệt JDK biên dịch, API đích và JVM thực thi

Ba thứ phải được ghi rõ mỗi khi báo cáo "code chạy trên Java X":

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| JDK dùng để biên dịch | `javac 17.0.x` | Xác định compiler và những đích `--release` đang hỗ trợ |
| Phiên bản Java SE/API đích | `--release 8` | Giới hạn cú pháp Java 8, class-file target và API nền tảng tương ứng |
| JVM dùng để chạy | `java 8`, `java 17` hay `java 21` | Quyết định môi trường runtime, triển khai API, diagnostic, dependency và thực thi |

Kiểm tra máy hiện tại:

```bash
java -version
javac -version
javac --help
```

`java -version` thường in thông tin ra stderr; `java --version` là cú pháp dài có từ Java 9. `javac --help` cho biết các mức `--release` mà **chính phiên bản javac đó** hỗ trợ; không nên giả định một compiler rất mới vẫn hỗ trợ mọi mức cũ.

Với JDK 9+ khi compiler còn hỗ trợ đích 8:

```bash
javac --release 8 ExceptionScopeDemo.java
java ExceptionScopeDemo
```

`--release 8` kiểm tra cùng lúc khả năng dùng cú pháp Java 8, dạng bytecode cho Java 8 và API nền tảng khả dụng ở Java 8. Chỉ dùng `-source 8 -target 8` bằng một JDK mới **không tương đương** nếu không kiểm soát bộ API chuẩn mà compiler nhìn thấy; chương trình có thể vô tình gọi một API chỉ tồn tại trên JDK mới. Với những dự án lớn, thiết lập `release` trong Maven/Gradle và chạy CI trên JVM đích.

Ví dụ cụ thể về API: `Files.readString(Path)` được giới thiệu từ Java 11. Một chương trình gọi phương thức đó không hợp lệ khi kiểm tra API đích Java 8 dù cú pháp gọi phương thức vẫn giống Java 8. Ngược lại, ví dụ `try (reader)` ở phần trước thất bại với `--release 8` vì **cú pháp**. Hai tình huống có thể cho lỗi biên dịch khác nhau, không nên gộp chúng làm một.

### Tương thích xuôi/ngược và class file

Bytecode biên dịch cho phiên bản Java mới có thể bị runtime cũ từ chối bằng `UnsupportedClassVersionError` (một `LinkageError`, tức `Error`). Một số class-file major version thường gặp: Java 8 = 52, 11 = 55, 17 = 61, 21 = 65, 25 = 69, 27 = 71. Đây là công cụ **chẩn đoán**, không phải bảo đảm "chỉ cần đúng major version là chạy": runtime còn cần API, module, thư viện native, dependency và môi trường phù hợp.

Đối với nguồn Java 8 chạy trên JDK mới, tính tương thích thường tốt nhưng không tuyệt đối. Nâng JDK có thể lộ ra API đã bị bỏ, truy cập nội bộ JDK bị hạn chế, cấu hình mã hóa/bảo mật khác hoặc thay đổi runtime; cần đọc hướng dẫn migration và chạy test.

## 8. Quy trình đối chiếu phiên bản JDK cho một vấn đề Exception

Khi gặp khác biệt, làm lần lượt:

1. **Ghi rõ ca kiểm thử:** tên ngoại lệ đầy đủ (ví dụ `java.lang.NoClassDefFoundError` thay vì chỉ "lỗi class"), mã nguồn tối thiểu, đầu vào, mong đợi và kết quả thực tế.
2. **Chụp ba phiên bản:** output `java -version`, `javac -version`, cấu hình `--release`/build tool; thêm phiên bản hệ điều hành và dependency khi liên quan.
3. **Phân loại nguồn thay đổi:** lỗi compiler (checked/unchecked, `catch`, cú pháp) → JLS; kiểu/hợp đồng API → API docs; nạp lớp/VM message → JVMS/JEP/release notes; hành vi thư viện ngoài → release notes thư viện.
4. **Đối chiếu tài liệu theo đúng mốc:** đọc JLS và API docs cho cả phiên bản cũ lẫn mới; tìm "Since", `@since`, `throws`, mô tả side effect, release notes và hướng dẫn migration. Không chỉ tìm một bài blog nói "Java mới đổi Exception".
5. **Biên dịch có kiểm soát:** trên compiler phù hợp, thử `--release N`, biết rõ nó không thay thế việc chạy thử trên JVM N. Nếu compiler không còn hỗ trợ N, dùng toolchain/JDK hỗ trợ N.
6. **Chạy cùng bộ test trên runtime cần hỗ trợ:** kiểm tra đúng loại ngoại lệ, thứ tự xử lý/đóng tài nguyên, cause/suppressed và hành vi phục hồi; dùng môi trường cô lập tương đương khi cần.
7. **Ghi kết luận có bằng chứng:** nêu hành vi khác từ bản nào, bước tái hiện, dòng tài liệu hoặc issue chính thức, và thay đổi mã/cấu hình đã sửa được lỗi.

Bảng kiểm thử tối thiểu có thể dùng khi nâng từ JDK 8 lên 17/21/25:

| Ca thử | Kỳ vọng kiểm chứng |
| --- | --- |
| Checked `IOException` | Compiler yêu cầu bắt hoặc khai báo khi phương thức có thể ném; code xử lý đúng luồng |
| Unchecked `IllegalArgumentException` | Không cần `throws` bắt buộc; catch ở biên ứng dụng nếu có thể xử lý |
| `try-with-resources` khi `close()` cũng lỗi | Primary exception vẫn được giữ; ngoại lệ đóng xuất hiện trong `getSuppressed()` |
| Cú pháp `try (reader)` | Hợp lệ từ Java 9; không hợp lệ với target nguồn 8 |
| `NullPointerException` do dereference | Có thể khác message theo JVM; test theo kiểu lỗi và hành vi |
| API chỉ có trong Java 11+ | Build `--release 8` bị từ chối dù runtime đang chạy JDK mới |
| Lỗi nạp lớp/dependency | Kiểm tra cả `ClassNotFoundException` (checked) và `NoClassDefFoundError` (Error) đúng ngữ cảnh |

Điểm khác nhau của hai lỗi cuối: `ClassNotFoundException` thường đến từ thao tác nạp lớp tường minh như `Class.forName`; `NoClassDefFoundError` thường xuất hiện khi JVM không thể định nghĩa/khởi tạo lớp cần thiết trong quá trình sử dụng, bao gồm cả tình huống thiếu lớp hoặc khởi tạo lớp thất bại trước đó. Chúng khác loại trong hệ phân cấp `Throwable`, vì vậy không nên gộp thành một `catch (Exception)` và giả định xử lý được cả hai.

## 9. Những lỗi học tập và triển khai dễ mắc

- **Xem Java Core là một phiên bản riêng:** thay bằng "Java SE N" hoặc "JDK N, vendor, update" khi cần kết luận cụ thể.
- **Dùng tài liệu Java mới để kết luận về Java 8:** phải mở API/JLS tương ứng; chú ý `@since` và API bị loại bỏ.
- **Chỉ nhìn `java -version`:** CLI `javac`, Maven/Gradle toolchain và Java dùng để chạy có thể khác nhau.
- **Lẫn lỗi biên dịch với ngoại lệ runtime:** checked exception chưa xử lý có thể khiến chương trình không được biên dịch; nó không phải là đối tượng Exception vừa được ném ở runtime.
- **Bắt `Exception` hoặc `Throwable` quá rộng:** dễ che lỗi logic, xử lý sai `InterruptedException` hoặc vô tình nuốt lỗi nặng. Chỉ bắt những lỗi mà tầng hiện tại có trách nhiệm giải quyết.
- **So khớp nguyên văn `getMessage()`/stack trace trong test:** chi tiết runtime, đường dẫn, số dòng, ngôn ngữ và cấu hình có thể khác; kiểm tra hợp đồng thay vì chuỗi hiển thị không được bảo đảm.
- **Nghĩ `finally` luôn an toàn khi ném lỗi:** một ngoại lệ hoặc `return` trong `finally` có thể làm mất thông tin lỗi ban đầu; ưu tiên `try-with-resources` cho tài nguyên thích hợp.
- **Đồng nhất cause với suppressed:** dùng `getCause()` để theo dõi lỗi được bọc, `getSuppressed()` để thấy lỗi bổ sung như khi đóng tài nguyên.
- **Cho rằng biên dịch `--release 8` là đã test trên Java 8:** nó kiểm soát source/API/class file, nhưng cần chạy kiểm thử trên runtime Java 8 thực tế cùng dependency mục tiêu.

## 10. Tự kiểm tra kiến thức

1. Vì sao `IOException` thường phải được bắt hoặc khai báo còn `IllegalStateException` thì không? Hãy trả lời dựa trên cây `Throwable`, không dựa vào tên class.
2. Nếu phần thân `try-with-resources` và `close()` cùng ném ngoại lệ, đối tượng nào là primary, đối tượng nào nằm trong `getSuppressed()`?
3. Vì sao `try (reader)` chạy được trên Java 9+ nhưng cần viết lại khi biên dịch cho Java 8?
4. Một chương trình `javac --release 8` thành công trên JDK 17 đã được chứng minh chạy đúng trên JVM 8 chưa? Cần kiểm tra thêm điều gì?
5. Khi chuyển từ JDK 8 sang JDK 21 và thấy message `NullPointerException` thay đổi, nên đọc tài liệu nào và sửa loại assertion nào trong test?

Gợi ý đáp án: (1) checked so với unchecked; (2) lỗi phần thân là primary, lỗi đóng là suppressed; (3) cú pháp Java 9 mở rộng; (4) chưa, phải chạy test trên runtime 8 và dependency phù hợp; (5) JEP 358, release notes, không cố định message trong assertion nếu API không cam kết.

## 11. Tài liệu gốc để tự đối chiếu

- Java Language Specification: https://docs.oracle.com/javase/specs/ (chọn đúng Java SE version; §14, §11 và phần `try`/`throw`/`throws` liên quan).
- Java SE API docs: https://docs.oracle.com/en/java/javase/ (chọn `java.lang.Throwable`, `AutoCloseable` và package cần tìm theo phiên bản).
- Oracle: Java SE 7 try-with-resources và suppressed: https://www.oracle.com/technical-resources/articles/java/trywithresources.html
- Java 9, cú pháp tài nguyên ngắn gọn: https://docs.oracle.com/en/java/javase/13/language/try-resources.html
- OpenJDK JEP 358 – Helpful NullPointerExceptions: https://openjdk.org/jeps/358
- Ghi chú JDK 15 về flag NPE mặc định: https://www.oracle.com/java/technologies/javase/15all-relnotes.html
- `javac`, `--release` và các giới hạn tương thích: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- Danh mục release notes để so sánh JDK 8–27: https://www.oracle.com/java/technologies/javase/jdk-relnotes-index.html
- JDK 27 GA ngày 15/09/2026: https://www.oracle.com/java/technologies/javase/27all-relnotes.html

**Tiêu chí hoàn thành:** Với một lỗi Exception cụ thể, bạn xác định được tầng chịu trách nhiệm (ngôn ngữ/API/JVM/thư viện), mốc JDK áp dụng, lệnh biên dịch và runtime cần dùng, kiểm thử tái hiện được, và nguồn tài liệu xác thực cho kết luận.