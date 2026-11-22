# Thử nghiệm nhanh API trong JShell rồi đưa vào chương trình kiểm chứng (Java 9+)

**JShell** là công cụ REPL (Read–Eval–Print Loop) của JDK, được đưa vào từ **Java 9**. Nó nhận một biểu thức, câu lệnh hoặc khai báo Java, biên dịch và thực thi ngay trong một phiên tương tác, rồi cho phép người học thay đổi cách gọi API mà chưa cần dựng cả dự án. Nhưng việc một vài câu lệnh chạy được trong JShell **không đồng nghĩa** hành vi đã được kiểm chứng, chương trình đã quản lý đầu vào đúng, hoặc thay đổi sau này sẽ không làm hỏng kết quả.

Bài thực hành này xây một quy trình hoàn chỉnh:

**Nêu kỳ vọng → thăm dò API trong JShell → tái hiện bằng script → tách thành phương thức Java có hợp đồng rõ ràng → viết kiểm tra tự động → biên dịch/chạy lại khi sửa → đưa vào quy trình phát triển.**

Ví dụ minh họa dùng **`List.of`, `Stream.takeWhile` và `Stream.dropWhile` (có từ Java 9)**, đồng thời dùng `var` (Java 10) và `Stream.toList()` (Java 16) để viết code gọn trên **JDK 17 trở lên**. Đây là bài thuộc nhóm **Thực hành tổng hợp**, nên trọng tâm là kỹ năng chuyển từ thử nhanh sang phần mềm có thể kiểm chứng, không chỉ ghi nhớ lệnh JShell. Các API và thực hành dưới đây vẫn còn áp dụng cho Java hiện đại.

## 1. Khi nào JShell giúp ích và khi nào chưa đủ?

Trong dự án thật, mỗi lần cần hiểu một API mới, ta có thể phải tạo class, viết phương thức `main`, sửa imports, biên dịch rồi chạy. JShell cho phép thử những giả thuyết nhỏ bằng vòng lặp ngắn:

```text
Giả thuyết về API
    ↓
Nhập một snippet trong JShell
    ↓
Đọc giá trị hoặc lỗi compiler/runtime
    ↓
Thử đầu vào/điều kiện khác
    ↓
Giữ lại hành vi đã hiểu
    ↓
Đưa vào mã nguồn + test độc lập
```

JShell hữu ích cho **khám phá chữ ký phương thức, thử biến đổi dữ liệu nhỏ, kiểm tra kiểu trả về, thao tác với Collections/Stream/Optional, và xây nguyên mẫu**. Nó không thay thế unit tests, build, kiểm tra tài nguyên, kiểm tra đồng thời, security review hoặc CI.

| Khía cạnh | JShell | Chương trình Java và test |
| --- | --- | --- |
| Đơn vị làm việc | Một snippet/biểu thức/khai báo, được đánh giá ngay | Một hoặc nhiều file nguồn với package/class/method cụ thể |
| Trạng thái | Phiên REPL giữ các biến và khai báo đã nhập, có thể thay đổi | Mỗi lần chạy `java` khởi tạo tiến trình và trạng thái theo mã nguồn |
| Imports | Có sẵn một số startup imports, người dùng có thể thêm | Phải khai báo imports hoặc tên đầy đủ trong file |
| Kiểm tra hành vi | Quan sát thủ công, dễ quên edge cases | Assertions/kiểm tra tự động, tái chạy được, báo lỗi khi sai |
| Hệ quả lỗi | Snippet lỗi không nhất thiết ngăn ta nhập snippet sau | Build/test có thể thất bại và chặn phát hành |
| Kết quả cần lưu | Kết luận và snippet có ý nghĩa, script khi cần | Code đã được kiểm tra, test và cấu hình build được quản lý phiên bản |

**Quy tắc:** dùng JShell để khám phá, **không lấy output cuối cùng của phiên tương tác làm bằng chứng duy nhất**. Hành vi cần bảo vệ phải trở thành bài kiểm tra có đầu vào và kết quả kỳ vọng xác định.

## 2. Bài toán thực hành: tìm khoảng độ trễ trước cảnh báo đầu tiên

Giả sử có log độ trễ (mili-giây) của các lần gọi API **theo thứ tự thời gian**:

```text
[85, 92, 180, 75]
```

Chọn ngưỡng cảnh báo `150 ms`. Hai câu hỏi nghiệp vụ khác nhau:

1. **Khoảng liên tiếp trước cảnh báo đầu tiên** có những độ trễ nào? Mong đợi `[85, 92]`; khi gặp `180` thì dừng, không nhận `75` ở phía sau.
2. **Giá trị cảnh báo đầu tiên** là gì? Mong đợi `180`; nếu không có lần nào đạt ngưỡng, trả về không có kết quả (`Optional.empty()`).

Dùng ca này để thử hai API Java 9:

- `Stream.takeWhile(predicate)` giữ **tiền tố liên tiếp dài nhất** còn thỏa điều kiện trên **ordered stream**.
- `Stream.dropWhile(predicate)` bỏ tiền tố liên tiếp còn thỏa điều kiện, giữ phần từ lần không thỏa đầu tiên trở đi.
- `Stream.filter(predicate)` là phép lọc **mọi phần tử** thỏa điều kiện, **không** dừng ở cảnh báo đầu tiên.

Ba lời gọi trông giống nhau nhưng có ngữ nghĩa rất khác. Với dữ liệu trong ví dụ:

| Biểu thức | Kết quả | Ý nghĩa |
| --- | --- | --- |
| `takeWhile(ms -> ms < 150)` | `[85, 92]` | Những lần đạt yêu cầu **trước** cảnh báo đầu tiên |
| `dropWhile(ms -> ms < 150)` | `[180, 75]` | Phần còn lại bắt đầu tại cảnh báo đầu tiên |
| `dropWhile(...).findFirst()` | `Optional[180]` | Cảnh báo đầu tiên, nếu có |
| `filter(ms -> ms < 150)` | `[85, 92, 75]` | Mọi lần dưới ngưỡng trên toàn bộ log |

**Đừng đánh đồng prefix với filter.** Việc chọn `takeWhile` chỉ đúng nếu thứ tự có ý nghĩa và câu hỏi là “trước sự kiện đầu tiên”. Nếu bài toán là “tất cả lần đáp ứng SLA”, `filter` mới là lựa chọn.

Để triển khai chắc chắn, ta cũng đặt hợp đồng đầu vào:

- Danh sách không được `null`.
- Mỗi độ trễ phải là số nguyên **không âm**, không có phần tử `null`.
- Ngưỡng phải là số nguyên **dương**.
- Độ trễ **bằng** ngưỡng cũng được tính là cảnh báo: điều kiện nhanh là `ms < threshold`, không phải `ms <= threshold`.
- Kết quả tiền tố là danh sách không chỉnh sửa được; method không thay đổi danh sách nguồn.

Đây là những điểm phải kiểm thử sau khi thăm dò thành công, thay vì chỉ thử dữ liệu “đẹp”.

## 3. Bắt đầu JShell và quan sát một API

Kiểm tra đang dùng đúng JDK:

```bash
java -version
javac -version
jshell --version
```

Chạy:

```bash
jshell
```

Lời nhắc thường có dạng `jshell>`; phiên bản JDK, prompt và các dòng phản hồi khi khai báo biến có thể khác nhau. Tại lời nhắc, nhập lần lượt:

```java
import java.util.*;
var readings = List.of(85, 92, 180, 75);
readings.stream().takeWhile(ms -> ms < 150).toList()
readings.stream().dropWhile(ms -> ms < 150).findFirst()
readings.stream().filter(ms -> ms < 150).toList()
```

Đoạn trên là **các snippet nhập trong JShell**, không phải file Java có `main`. Các biểu thức cuối **không cần dấu chấm phẩy** khi nhập tương tác; tuy nhiên khi chuyển sang Java source, hãy dùng cú pháp Java đầy đủ phù hợp với vị trí. JShell có thể hiển thị tên biến tạm như `$3`, `$4` tùy số snippet và startup environment; **không dựa vào tên/ID tự sinh đó trong test**.

Kết quả có ý nghĩa:

```text
[85, 92]
Optional[180]
[85, 92, 75]
```

Để tránh phụ thuộc định dạng phản hồi do JShell tự tạo, có thể in có nhãn:

```java
System.out.println("prefix=" + readings.stream().takeWhile(ms -> ms < 150).toList());
System.out.println("firstAlert=" + readings.stream().dropWhile(ms -> ms < 150).findFirst().orElse(-1));
System.out.println("filtered=" + readings.stream().filter(ms -> ms < 150).toList());
```

Khi đã thử xong, nhập `/exit` để thoát.

### Lệnh điều khiển JShell khác với Java code

Những lệnh bắt đầu bằng `/` thuộc **công cụ JShell**, không phải Java:

| Lệnh | Dùng khi nào? |
| --- | --- |
| `/help` hoặc `/help <command>` | Học cú pháp lệnh và cách cấu hình |
| `/list` | Xem snippets trong phiên, giúp biết trạng thái đang có |
| `/vars` | Xem các biến và giá trị hiện hành |
| `/methods` | Xem các method đã khai báo |
| `/types` | Xem class/interface/enum/record do phiên đang giữ |
| `/edit <name>` | Mở editor chỉnh snippet (tùy môi trường) |
| `/drop <name>` | Bỏ một khai báo/snippet đang hoạt động |
| `/save snippets.jsh` | Lưu các snippets đang hoạt động ra script |
| `/save -history session.jsh` | Lưu lịch sử trong phiên để nghiên cứu lại |
| `/open snippets.jsh` | Đọc và thực thi script trong phiên |
| `/reset` | Xóa trạng thái snippet để thử lại từ đầu |
| `/exit` | Thoát JShell |

JShell cho phép khai báo biến và method từng phần; do vậy một snippet có thể **vô tình dùng lại khai báo cũ**. Trước khi xem một thử nghiệm là tái lập được, hãy tạo phiên sạch rồi chạy lại tất cả imports và các snippet liên quan. Dùng `/list` để phân biệt code thực sự đang được đánh giá với code chỉ có trong lịch sử.

Một khác biệt cần nhớ: `/save` không phải “xuất class Java chạy được”. File `.jsh` là **script dành cho JShell**; muốn đóng gói thành ứng dụng, cần tổ chức lại thành class, method, imports, package và test phù hợp. Với script lưu từ phiên REPL, hãy kiểm tra các biến/phương thức tự sinh và phần phụ thuộc vào startup imports trước khi dùng lại.

## 4. Đưa thử nghiệm thành script JShell tái lập được

Tạo thư mục `jshell-to-program`. Trong đó tạo tệp `explore.jsh` với **nội dung hoàn chỉnh** sau:

```java
import java.util.*;
var readings = List.of(85, 92, 180, 75);
System.out.println("prefix=" + readings.stream().takeWhile(ms -> ms < 150).toList());
System.out.println("firstAlert=" + readings.stream().dropWhile(ms -> ms < 150).findFirst().orElse(-1));
System.out.println("filtered=" + readings.stream().filter(ms -> ms < 150).toList());
/exit
```

Khối này có ngôn ngữ `java` vì những dòng chính là Java snippets, nhưng **dòng `/exit` là lệnh JShell** chứ không phải cú pháp Java. File `.jsh` không được đưa cho `javac` để biên dịch như class. Nó cũng không phải một chương trình Java độc lập.

Chạy từ thư mục chứa file:

```bash
jshell --feedback silent explore.jsh
```

**Stdout thực tế của các lệnh in trong script** (đã thử trên OpenJDK 21):

```text
prefix=[85, 92]
firstAlert=180
filtered=[85, 92, 75]
```

Chế độ `--feedback silent` giảm phản hồi tự động của JShell, nhờ vậy kết quả có nhãn dễ đối chiếu. Script kết thúc bằng `/exit` để tool kết thúc khi chạy theo lô; nếu muốn dùng `/open explore.jsh` trong một phiên tương tác **mà không thoát**, hãy tạo bản script không có dòng `/exit`.

**Vì sao script hữu ích nhưng vẫn chưa phải automated test?** Nó cho thấy ba kết quả trên một bộ dữ liệu duy nhất, nhưng không tự định nghĩa rằng output sai sẽ khiến quá trình build thất bại. Nó cũng chưa kiểm tra danh sách rỗng, giá trị bằng ngưỡng, dữ liệu sai hoặc tính bất biến. Giai đoạn tiếp theo phải viết hợp đồng và test trong chương trình Java.

## 5. Chọn phiên bản Java chính xác trước khi chép code

Dù JShell và các API cốt lõi có từ Java 9, không phải mọi cú pháp trong snippet đều được Java 9 hỗ trợ:

| Thành phần | Phiên bản có từ | Vai trò trong ví dụ |
| --- | --- | --- |
| `jshell` | JDK 9 | REPL khám phá Java |
| `List.of(...)` | Java 9 | Tạo danh sách có thứ tự, **không chỉnh sửa được**, không nhận null |
| `Stream.takeWhile(...)` | Java 9 | Lấy tiền tố ordered stream thỏa điều kiện |
| `Stream.dropWhile(...)` | Java 9 | Bỏ tiền tố ordered stream thỏa điều kiện |
| `var` cho local variable | Java 10 | Để compiler suy luận kiểu local của `readings` |
| `Stream.toList()` | Java 16 | Gom kết quả thành danh sách **unmodifiable** |
| `Stream.findFirst()` | `Stream.findFirst()` từ Java 8 | Biểu diễn trường hợp tìm thấy/không tìm thấy |
| `Objects.requireNonNull(...)` | Java 7 | Kiểm tra danh sách không null |

Các tệp chương trình và test ở phần sau yêu cầu **Java 17+**, nên chúng không được quảng cáo là chạy bằng `--release 9`. Nếu dự án thực sự cần hỗ trợ runtime Java 9, phải loại bỏ cú pháp/API mới hơn và kiểm thử lại bằng build với `javac --release 9`; không chỉ thay chữ trong tài liệu.

Cũng đừng nhầm `List.of` với `Arrays.asList` hay `new ArrayList`. `List.of` trả về danh sách không chỉnh sửa được và loại trừ null; `Stream.toList()` cũng trả danh sách không chỉnh sửa được. Nếu bài toán đòi danh sách mutable, chủ động tạo `new ArrayList<>(...)` thay vì gọi `add` vào một kết quả unmodifiable.

## 6. Chuyển từ snippet sang API Java có hợp đồng

Lưu tệp **`ApiFromShell.java`** trong thư mục `jshell-to-program`, cùng cấp với `explore.jsh`. Toàn bộ code dưới đây là **chương trình biên dịch độc lập**, không phụ thuộc biến tạm của JShell:

```java
import java.util.List;
import java.util.Objects;
import java.util.Optional;

public final class ApiFromShell {
    private ApiFromShell() { }

    /**
     * Return readings before the first threshold violation.
     * Input values must be nonnegative and non-null.
     */
    public static List<Integer> leadingFast(List<Integer> readings, int threshold) {
        validate(readings, threshold);
        return readings.stream().takeWhile(ms -> ms < threshold).toList();
    }

    /** Return the first reading at or above the threshold, if any. */
    public static Optional<Integer> firstAlert(List<Integer> readings, int threshold) {
        validate(readings, threshold);
        return readings.stream().dropWhile(ms -> ms < threshold).findFirst();
    }

    private static void validate(List<Integer> readings, int threshold) {
        Objects.requireNonNull(readings, "readings");
        if (threshold <= 0) {
            throw new IllegalArgumentException("threshold must be positive");
        }
        if (readings.stream().anyMatch(ms -> ms == null || ms < 0)) {
            throw new IllegalArgumentException("readings must be nonnegative");
        }
    }

    public static void main(String[] args) {
        List<Integer> readings = List.of(85, 92, 180, 75);
        System.out.println("prefix=" + leadingFast(readings, 150));
        System.out.println("firstAlert=" + firstAlert(readings, 150).orElse(-1));
        System.out.println("filtered=" +
                readings.stream().filter(ms -> ms < 150).toList());
    }
}
```

Ở đây ta chuyển **một thao tác thử** thành **hai hàm có ý nghĩa và hợp đồng**:

- `leadingFast(readings, threshold)` nhận dữ liệu và ngưỡng qua tham số, không lấy biến global từ JShell. Với `List.of(85,92,180,75)` và ngưỡng `150`, trả `[85,92]`.
- `firstAlert(readings, threshold)` trả `Optional<Integer>` thay vì mã `-1` trong API. Khi không tìm thấy cảnh báo, `Optional.empty()` mô tả rõ trạng thái không có kết quả.
- `validate` chịu trách nhiệm xử lý ranh giới dữ liệu, tránh đặt các kiểm tra lặp trong mọi caller. Số độ trễ âm bị từ chối thay vì âm thầm được xem là “nhanh”.
- `main` chỉ là **demo chạy tay** để hiển thị kết quả. Logic thực sự có thể được gọi trực tiếp từ các test và từ chương trình khác.

Trong `main`, lời gọi `.orElse(-1)` chỉ dùng để in số dễ đọc trong demo; **không đổi** chữ ký `firstAlert` từ `Optional<Integer>` sang int. Nếu ứng dụng thật sử dụng `-1` như sentinel ở mọi nơi, nó có thể làm người dùng quên xử lý trường hợp không có dữ liệu.

### Tại sao `takeWhile` chứ không phải `filter`?

Hãy đọc bằng ngôn ngữ miền:

- `takeWhile(ms -> ms < threshold)`: “lấy các lần đo vẫn đạt mục tiêu **cho đến ngay trước lỗi đầu tiên**”.
- `filter(ms -> ms < threshold)`: “lấy **mọi** lần đo đạt mục tiêu trong toàn bộ lịch sử”.
- `dropWhile(ms -> ms < threshold).findFirst()`: “bỏ các lần đạt mục tiêu ban đầu; trả về sự kiện đầu tiên không đạt”.

Sự khác biệt trở nên rõ khi sau một cảnh báo có một giá trị tốt như `75`. Nếu dữ liệu bị đưa vào `HashSet` hoặc nguồn stream **không ordered**, hợp đồng tiền tố không còn giống `List.stream()`; `takeWhile`/`dropWhile` trên unordered stream có semantics khác và có thể không cho kết quả bạn hình dung theo thời gian. **Đầu vào phải giữ encounter order**; ở đây dùng `List`.

Hai phép toán `takeWhile`/`dropWhile` trên **ordered parallel stream** cũng có thể tốn kém hơn do phải giữ thứ tự; khi bài toán là prefix theo thời gian, ưu tiên đầu vào có thứ tự rõ và pipeline sequential trừ khi có benchmark đủ mạnh.

## 7. Viết chương trình kiểm chứng tự động không cần thư viện ngoài

Một ví dụ tốt không chỉ thử “happy path” rồi in `OK`. Tạo tệp thứ hai **`ApiFromShellTest.java`** cạnh `ApiFromShell.java`. Đây là một **test harness Java chạy độc lập**, dùng `AssertionError` khi kỳ vọng sai; có thể dùng ngay trên JDK 17+ mà không tải JUnit.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

public final class ApiFromShellTest {
    private static int passed;

    private static void equal(Object actual, Object expected, String caseName) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError(caseName + ": expected=" + expected +
                    " actual=" + actual);
        }
        passed++;
    }

    private static void throwsType(Class<? extends Throwable> expected,
                                   Runnable action, String caseName) {
        try {
            action.run();
        } catch (Throwable error) {
            if (expected.isInstance(error)) {
                passed++;
                return;
            }
            throw new AssertionError(caseName + ": wrong exception", error);
        }
        throw new AssertionError(caseName + ": no exception");
    }

    public static void main(String[] args) {
        var sample = List.of(85, 92, 180, 75);
        equal(ApiFromShell.leadingFast(sample, 150),
                List.of(85, 92), "stop at first alert");
        equal(ApiFromShell.firstAlert(sample, 150),
                Optional.of(180), "find first alert");
        equal(ApiFromShell.leadingFast(List.of(), 150),
                List.of(), "empty input");
        equal(ApiFromShell.firstAlert(List.of(10, 20), 150),
                Optional.empty(), "no alert");
        equal(ApiFromShell.leadingFast(List.of(150, 10), 150),
                List.of(), "boundary is alert");
        equal(ApiFromShell.firstAlert(List.of(150, 10), 150),
                Optional.of(150), "boundary first alert");
        throwsType(IllegalArgumentException.class,
                () -> ApiFromShell.leadingFast(sample, 0), "bad threshold");
        throwsType(NullPointerException.class,
                () -> ApiFromShell.leadingFast(null, 150), "null list");
        throwsType(IllegalArgumentException.class,
                () -> ApiFromShell.firstAlert(Arrays.asList(1, null), 150),
                "null reading");
        throwsType(UnsupportedOperationException.class,
                () -> ApiFromShell.leadingFast(sample, 150).add(10),
                "unmodifiable result");
        System.out.println("testsPassed=" + passed);
    }
}
```

**Đây là 10 phép kiểm độc lập**, được chia theo mục tiêu:

| Nhóm | Phép thử | Bảo vệ điều gì? |
| --- | --- | --- |
| Đường đi bình thường | Lấy prefix `[85,92]` | Dừng ở cảnh báo đầu tiên |
| Đường đi bình thường | Lấy `Optional.of(180)` | Trả đúng sự kiện cảnh báo |
| Cực biên | Danh sách rỗng | Không xảy ra lỗi khi không có dữ liệu |
| Cực biên | Tất cả dưới ngưỡng | Kết quả cảnh báo là `Optional.empty()` |
| Ranh giới | `150` bằng ngưỡng, prefix rỗng | Điều kiện là `<`, không phải `<=` |
| Ranh giới | `150` bằng ngưỡng, cảnh báo là 150 | Điểm chạm ngưỡng tính là cảnh báo |
| Input sai | Ngưỡng bằng 0 | Bị từ chối bằng `IllegalArgumentException` |
| Input sai | Danh sách `null` | Bị từ chối bằng `NullPointerException` |
| Input sai | Phần tử `null` | Không được xử lý như số đo hợp lệ |
| Hợp đồng kết quả | Thử gọi `add(10)` vào list trả về | List của `Stream.toList()` không chỉnh sửa được |

Các helper trong test dùng `Objects.equals` để so giá trị nội dung, **không dùng `==` để so hai danh sách**. `throwsType` kiểm tra exception **có đúng loại được kỳ vọng** hay không. Nếu test sai, `AssertionError` được ném ra, chương trình kết thúc với lỗi thay vì âm thầm in thành công.

Sở dĩ import `Arrays` là để tạo đầu vào chứa `null` bằng `Arrays.asList(1, null)`. Không dùng `List.of(1, null)` cho tình huống đó vì **`List.of` tự ném `NullPointerException` ngay tại lúc xây danh sách**, tức là test chưa hề đi vào API cần kiểm tra.

## 8. Biên dịch, chạy và đối chiếu stdout

Từ thư mục `jshell-to-program` chứa đủ ba tệp `explore.jsh`, `ApiFromShell.java` và `ApiFromShellTest.java`, chạy lần lượt:

```bash
javac -encoding UTF-8 ApiFromShell.java ApiFromShellTest.java
java ApiFromShell
java ApiFromShellTest
```

**Stdout của `java ApiFromShell` (đã biên dịch/chạy trên OpenJDK 21):**

```text
prefix=[85, 92]
firstAlert=180
filtered=[85, 92, 75]
```

**Stdout của `java ApiFromShellTest`:**

```text
testsPassed=10
```

Cả ba kết quả trong JShell trùng với chương trình Java, nhưng điều mới và quan trọng nhất là **test xác nhận thêm các trường hợp biên, input sai và đặc tính của giá trị trả về**. Khi sửa method sau này, chạy lại tệp test để phát hiện thay đổi ngoài ý muốn.

**Kiểm tra trạng thái thất bại:** nếu `javac` báo lỗi, không tiếp tục chạy class cũ rồi kết luận bản mới đã qua QA. Nên dùng build tool/CI có bước `compile → test` theo thứ tự và dừng khi bước trước thất bại. Với command shell có hỗ trợ, có thể nối bằng điều kiện `&&`; trên **Windows PowerShell 5.1**, chạy từng lệnh và kiểm tra `$LASTEXITCODE`, vì shell đó không có toán tử `&&` giống Bash hoặc PowerShell mới. Trong ứng dụng thật, Maven/Gradle hoặc CI cung cấp hành vi fail-fast rõ hơn.

Trong ví dụ, các phép kiểm ném `AssertionError` **trực tiếp**, khác với câu lệnh Java `assert expression;`. `assert` thường bị tắt mặc định nếu chạy `java` mà không có `-ea`. Nếu dùng Java `assert`, phải chủ động bật assertions trong test runner; tránh viết test mà thực ra không chạy các assertion. Một framework hiện hành như **JUnit Jupiter** thường thuận tiện hơn cho CI, báo cáo từng test, fixtures và parameterized tests, nhưng phần thực hành này chỉ cần JDK chuẩn.

### Kiểm chứng test có khả năng bắt lỗi

Một kỹ thuật nhỏ nhưng hữu ích: **cố ý làm sai rồi hoàn tác** trong bản làm việc tạm thời. Chẳng hạn đổi điều kiện `ms < threshold` thành `ms <= threshold`, sau đó biên dịch và chạy test. Hai bài kiểm tra giá trị biên `150` phải thất bại. Đổi lại thành `<` rồi chạy test thêm lần nữa để khẳng định mọi kiểm tra đều PASS. Không commit thay đổi sai này.

Tương tự, nếu vô tình đổi `takeWhile` thành `filter`, phép thử `[85,92,180,75]` sẽ phát hiện vì kết quả không còn là `[85,92]`. Đó là lý do chọn một bộ dữ liệu có **giá trị tốt sau cảnh báo** — nếu chỉ dùng dữ liệu `[85,92,180]` thì cả `filter` và `takeWhile` có thể cùng trả `[85,92]`, che giấu lỗi chọn API.

## 9. Từ kết quả thử tay đến kiểm chứng có chất lượng

Áp dụng một checklist ngắn cho mỗi API mới:

1. **Viết giả thuyết bằng ngôn ngữ nghiệp vụ.** Ví dụ “lấy độ trễ trước cảnh báo đầu tiên”, không chỉ “dùng stream”.
2. **Tạo ví dụ nhỏ có thể hiểu bằng mắt.** Chọn cả một trường hợp phân biệt được hai API gần giống nhau.
3. **Thử trong JShell.** Ghi nhận signature, giá trị, kiểu trả về và các điều kiện bất ngờ.
4. **Thử ranh giới trong JShell.** Input rỗng, null, bằng ngưỡng, số âm, thứ tự thay đổi.
5. **Chọn phiên bản JDK.** Xác định API có từ Java mấy; đừng dùng code Java 16 rồi tuyên bố phù hợp `--release 9`.
6. **Đưa logic vào method có tên/hợp đồng rõ.** Tránh phụ thuộc biến tạm `$1`, global mutable session hoặc auto-imports.
7. **Viết unit tests có expected result.** Kiểm tra thành công, không có kết quả, input sai và bảo vệ các semantics quan trọng.
8. **Biên dịch và chạy từ môi trường sạch.** Dùng `javac`/build tool, chạy app và tests riêng; bảo đảm lỗi khiến quá trình không thành công.
9. **Chạy lại trong CI.** Quản lý source/test và phiên bản dependency; không coi script REPL là regression suite duy nhất.
10. **Lưu bài học về API gần code.** Với điều kiện khó nhầm như `takeWhile` khác `filter`, viết comment/Javadoc và test nêu rõ lý do.

Mô hình này cũng áp dụng khi khám phá các API khác: `Map.of`, `Optional.stream()`, `Objects.requireNonNullElse`, `CompletableFuture` hoặc những kiểu dữ liệu trong Java library. Trước khi phát hành, luôn kiểm tra hành vi ở **JDK và dependency versions mà sản phẩm thực sự chạy**, không chỉ bản đang dùng trong REPL.

## 10. Những lỗi dễ mắc khi dùng JShell và chuyển sang code thật

| Lỗi | Triệu chứng | Cách tránh |
| --- | --- | --- |
| Nghĩ JShell là test suite | Chạy tay một trường hợp thành công nên tin API đúng | Viết assertions có đầu vào/expected kết quả và chạy tự động |
| Dựa vào biến `$1` hoặc imports ngầm | Chép code sang file `.java` không biên dịch | Khai báo imports, kiểu, tên method và class đầy đủ |
| Tái sử dụng state cũ | Snippet “chạy được” nhưng thực chất gọi method từ lần thử trước | `/list`, `/reset` hoặc khởi động JShell mới rồi tái chạy |
| Nhầm `takeWhile` với `filter` | Nhận cả giá trị `75` sau cảnh báo `180` | Test dữ liệu có phần tử đạt ngưỡng **sau** phần tử vi phạm |
| Dùng stream không có thứ tự | Prefix kết quả không có ý nghĩa theo thời gian | Dùng ordered source như `List`; nêu hợp đồng thứ tự |
| Dùng `>=` thay cho `>`, hoặc `<=` thay `<` | Sai tại giá trị đúng bằng ngưỡng | Thêm test dữ liệu `150` |
| Dùng `List.of(null)` để test hàm xử lý null | Lỗi xảy ra ngay trước khi gọi API | Tạo dữ liệu null bằng collection cho phép null |
| Gọi `add` trên kết quả `Stream.toList()` | `UnsupportedOperationException` | Chọn hợp đồng immutable hoặc tạo bản `ArrayList` |
| Nghĩ `var` và `Stream.toList()` đã có từ Java 9 | `javac --release 9` báo lỗi | Phân biệt version của từng feature, yêu cầu JDK 17+ cho bài mẫu |
| Dùng `/open` trên script có `/exit` | Phiên tương tác đóng ngay sau khi chạy script | Bỏ `/exit` trong script dành cho `/open`; giữ trong script chạy batch |
| Quên `-encoding UTF-8` | Một số môi trường đọc sai source có dấu | Đồng nhất encoding khi lưu và biên dịch |
| Chạy file `.jsh` bằng `javac` | Báo lỗi syntax ở các lệnh JShell | Chạy script bằng `jshell`, code production bằng `javac` |
| `javac` lỗi nhưng vẫn chạy class cũ | Output giống cũ, khiến tưởng bản mới đã PASS | Dừng khi compile lỗi và dùng output directory/build sạch |
| Dùng `assert` nhưng không bật `-ea` | Các điều kiện test không được thực thi | Dùng framework test hoặc kiểm tra/throw tường minh |
| Chỉ nhìn stdout mà không nhìn exit code | Tool có thể đã in lỗi ở stderr và thất bại | Xem cả stderr, exit code và tình trạng test runner |
| Dán mã chứa token, password, dữ liệu thật vào REPL | Lịch sử/script có thể lưu dữ liệu nhạy cảm | Dùng dữ liệu giả, không lưu secrets trong lịch sử/script |

**Bảo vệ dữ liệu trong REPL:** JShell là môi trường thực thi Java thực sự, không phải sandbox bảo mật cho đoạn mã không tin cậy. Một snippet có thể truy cập file, mạng và API của JVM trong phạm vi quyền tiến trình. Không chạy code lạ chỉ vì nó ngắn; không thử với dữ liệu production hoặc secret nếu không có quyền/quy trình bảo vệ phù hợp. Khi thao tác với API có side effects (ghi file, database, gửi HTTP), tạo dữ liệu giả, mock hoặc môi trường thử được kiểm soát.

## 11. Bài tập mở rộng

**Bài 1 — Giới hạn khác.** Trong JShell thử `[30, 70, 100]` với ngưỡng `100`; đoán kết quả trước khi chạy.  
**Đáp án gợi ý:** `leadingFast = [30,70]`; `firstAlert = Optional[100]` vì đạt ngưỡng cũng là cảnh báo.

**Bài 2 — Tất cả tốt.** Dùng `List.of(10, 20, 30)`, ngưỡng `100`.  
**Đáp án:** prefix có cả ba phần tử; cảnh báo là `Optional.empty()`. Hãy thêm test kiểm tra cả hai method.

**Bài 3 — Viết nhầm hàm.** Đổi `takeWhile` sang `filter`, chạy test.  
**Đáp án:** test prefix với sample `[85,92,180,75]` thất bại vì filter giữ `75`.

**Bài 4 — Tách phần kiểm tra đầu vào.** Thêm test cho số âm `List.of(10, -2, 5)`.  
**Đáp án:** API hiện có phải ném `IllegalArgumentException`. Đừng thử tạo dữ liệu âm rồi cho đó là hợp lệ; theo hợp đồng đây là input lỗi.

**Bài 5 — Tránh mã kết quả sentinel.** Tại sao API `firstAlert` trả `Optional<Integer>` chứ không trả `-1`?  
**Đáp án:** `Optional.empty()` diễn đạt rõ “không tìm thấy”; caller phải quyết định cách xử lý tình huống đó. `-1` chỉ được dùng tại ranh giới hiển thị demo, không phải hợp đồng dữ liệu của method.

**Bài 6 — Phiên bản Java.** Có thể biên dịch nguyên văn bộ ví dụ bằng Java 9 không?  
**Đáp án:** Không. `var` xuất hiện ở Java 10, `Stream.toList()` ở Java 16. Bộ ví dụ dùng Java 17+ dù phần JShell và ba API cốt lõi xuất hiện từ Java 9.

**Bài 7 — Tự động hóa.** Bổ sung một bước trong build để chạy `java ApiFromShellTest` sau compile, kiểm tra exit code và thất bại nếu test fail.  
**Đáp án gợi ý:** dùng task/phases của công cụ build hoặc CI, không chỉ xem thủ công rằng terminal có in chữ “passed”.

## Tài liệu tham khảo hiện hành

- [Oracle JDK 25 — Introduction to JShell](https://docs.oracle.com/en/java/javase/25/jshell/introduction-jshell.html): JShell là REPL từ Java 9, mục đích và cách khởi động.
- [Oracle JDK 25 — JShell Scripts](https://docs.oracle.com/en/java/javase/25/jshell/scripts.html): tạo, lưu, `/open` và chạy các file `.jsh`.
- [Oracle JDK 25 — The jshell Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jshell.html): các tùy chọn chạy, phản hồi, startup scripts và commands.
- [Oracle JDK 25 — Stream API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): `takeWhile`, `dropWhile`, `filter`, `findFirst` và `toList`.
- [Oracle JDK 25 — List API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html): `List.of`, thứ tự, tính bất biến và xử lý null.
- [Oracle JDK 25 — Optional API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html): biểu diễn giá trị có thể vắng mặt, `orElse` và `isPresent`.
- [Dev.java — JShell Tool](https://dev.java/learn/jshell-tool/): hướng dẫn thực hành công cụ JShell trong workflow Java hiện đại.

**Ghi nhớ:** JShell trả lời “API này có thể vận hành thế nào trên một ví dụ nhỏ?”; một chương trình Java có test trả lời “hành vi nào chúng ta cam kết và có thể xác minh lại sau mỗi thay đổi?”. Bước quan trọng nhất không phải copy snippet thành công, mà là **chuyển phát hiện từ REPL thành hợp đồng, xử lý đầu vào và kiểm chứng tự động tái lập được**.
