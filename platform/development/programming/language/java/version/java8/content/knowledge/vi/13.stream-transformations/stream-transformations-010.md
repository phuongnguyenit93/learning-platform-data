# Xử lý phần tử null, lỗi chuyển đổi và dữ liệu không hợp lệ trong Stream (Java 8)

Bài này thuộc **Biến đổi Stream**. Khi biến đổi dữ liệu từ danh sách, tệp CSV, biểu mẫu hoặc phản hồi API, một phần tử có thể là `null`, có chuỗi không chuyển được sang kiểu đích, hoặc chuyển được nhưng vi phạm quy tắc nghiệp vụ. Cần chọn rõ chính sách: **dừng khi có lỗi**, **bỏ qua bản ghi không hợp lệ**, hay **giữ cả kết quả lẫn lý do lỗi**. Các kỹ thuật bên dưới dùng API có từ Java 8 và vẫn áp dụng trên JDK hiện hành.

## 1. Phân biệt đúng ba nhóm vấn đề

| Tình huống | Ví dụ | Rủi ro khi biến đổi Stream | Cách xử lý đúng |
| --- | --- | --- | --- |
| Nguồn dữ liệu là `null` | `List<String> items = null` | Gọi `items.stream()` gây `NullPointerException` trước khi tạo pipeline | Xác định nguồn vắng mặt là lỗi hay có thể coi là tập rỗng; kiểm tra trước `stream()` |
| **Phần tử** trong nguồn là `null` | `Arrays.asList("A", null, "B")` | `map(String::trim)` hoặc gọi phương thức trên phần tử gây `NullPointerException` | `filter(Objects::nonNull)` **trước** bước cần dereference; hoặc biểu diễn `null` thành một kết quả lỗi |
| Chuyển đổi kiểu thất bại | `"abc"`, `"2147483648"` khi chuyển sang `int` | `Integer.parseInt` ném `NumberFormatException` | Bắt ngoại lệ **cụ thể** trong hàm chuyển đổi; quyết định dừng, bỏ qua, hay trả kết quả lỗi |
| Chuyển đổi được nhưng **sai quy tắc** | ID `0` hoặc `1001` khi miền cho phép là 1–1000 | Dữ liệu có kiểu hợp lệ nhưng không được phép dùng | Kiểm tra miền giá trị **sau** parse; không đồng nhất lỗi cú pháp với lỗi nghiệp vụ |
| Mapper trả về `null` | Tra cứu tên không tìm thấy | Toán tử phía sau có thể không chấp nhận `null` | Lọc `null` sau `map` nếu chính sách là bỏ qua, hoặc dùng kiểu kết quả biểu đạt sự thiếu vắng |

`Stream<T>` không tự động loại `null`. `filter` chỉ giữ phần tử làm predicate trả về `true`; `map` biến đổi từng phần tử nhưng **không tự bắt exception**. Các thao tác trung gian này có tính *lazy*: việc xử lý thường xảy ra khi gọi terminal operation như `collect`, `count` hoặc `findFirst`. Vì thế một lỗi trong `map` có thể chỉ xuất hiện tại dòng `collect`.

**Quy tắc thiết kế:** phân biệt `null` (không có giá trị), chuỗi trắng (có chuỗi nhưng không có nội dung hữu ích), sai cú pháp, và sai nghiệp vụ. Việc gộp hết thành `0`, `null` hoặc một chuỗi rỗng thường làm mất thông tin cần thiết để sửa lỗi đầu vào.

## 2. Tránh null trước khi gọi phương thức trên phần tử

Với dữ liệu mà `null` và chuỗi trống được phép bỏ qua, thứ tự an toàn là **lọc null → chuẩn hóa → lọc rỗng → tiếp tục xử lý**.

Tệp `NullFilterDemo.java` (mã độc lập, biên dịch được với Java 8):

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

public class NullFilterDemo {
    public static void main(String[] args) {
        List<String> raw = Arrays.asList(" Ana ", null, " ", "Binh");

        List<String> clean = raw.stream()
            .filter(Objects::nonNull)
            .map(String::trim)
            .filter(s -> !s.isEmpty())
            .collect(Collectors.toList());

        System.out.println(clean);
    }
}
```

Chạy với JDK có `javac` và `java`:

```bash
javac -encoding UTF-8 NullFilterDemo.java
java NullFilterDemo
```

Kết quả:

```text
[Ana, Binh]
```

- `Objects::nonNull` kiểm tra phần tử khác `null`; nó **không** sửa `null` thành chuỗi.
- `String::trim` chỉ được gọi sau bước kiểm tra null. Với ứng dụng cần xử lý đầy đủ các kiểu khoảng trắng Unicode, phải định nghĩa chính sách chuẩn hóa phù hợp; `trim()` không nhận diện mọi khoảng trắng Unicode.
- `filter(s -> !s.isEmpty())` đặt **sau** chuẩn hóa, vì `" "` trước `trim()` chưa phải chuỗi rỗng.
- `Collectors.toList()` thu các giá trị thành danh sách; đừng dựa vào một kiểu danh sách hay khả năng chỉnh sửa cụ thể mà tài liệu collector không bảo đảm.

**Sai thứ tự:** `raw.stream().map(String::trim).filter(Objects::nonNull)` vẫn có thể ném `NullPointerException` tại `map`. Nếu chính **kết quả của mapper** có thể là null, khi đó có thể dùng `.map(...).filter(Objects::nonNull)`, với điều kiện mapper tự xử lý đầu vào null một cách an toàn.

Nếu **bản thân danh sách** có thể null, kiểm tra nguồn trước:

```java
// Chỉ dùng cách này khi hợp đồng nghiệp vụ coi nguồn null như danh sách rỗng.
java.util.stream.Stream<String> source =
    raw == null ? java.util.stream.Stream.empty() : raw.stream();
```

Không âm thầm coi một nguồn đáng lẽ bắt buộc phải có là rỗng: trong trường hợp đó nên báo lỗi tại biên đầu vào.

## 3. Lỗi chuyển đổi nằm ở đâu trong pipeline?

Ví dụ ngắn:

```java
// Không an toàn khi dữ liệu từ bên ngoài chưa được kiểm tra.
List<Integer> numbers = Arrays.asList("12", "oops").stream()
    .map(Integer::parseInt)
    .collect(Collectors.toList());
```

Đây là đoạn minh họa, cần các import `java.util.*` và `java.util.stream.*`. Khi terminal `collect` duyệt đến `"oops"`, `Integer.parseInt` ném `NumberFormatException` và lời gọi terminal không hoàn tất bình thường. Việc thêm `filter(Objects::nonNull)` **không** xử lý được chuỗi `"oops"` hay số vượt miền `int`.

`Integer.parseInt` diễn giải số nguyên thập phân có dấu tùy chọn. Nó không tự bỏ khoảng trắng: `" 12 "` cần chuẩn hóa trước khi parse. Ngoài văn bản không phải số, số nằm ngoài giới hạn `int` cũng gây `NumberFormatException`. Sau khi parse, giá trị như `-1` vẫn có thể hợp lệ về mặt kiểu nhưng không hợp lệ với quy tắc “ID từ 1 đến 1000”.

Có ba chính sách xử lý, không nên trộn lẫn chúng một cách vô tình:

| Chính sách | Hành vi | Phù hợp khi |
| --- | --- | --- |
| **Fail fast** | Ngoại lệ hoặc kết quả thất bại chấm dứt thao tác; tầng gọi chịu trách nhiệm phản hồi | Dữ liệu phải chính xác tuyệt đối; sai một bản ghi khiến toàn lô không thể dùng |
| **Skip invalid** | Biến đầu vào sai thành **0 phần tử đầu ra** | Dữ liệu không hợp lệ có thể bỏ qua theo yêu cầu rõ ràng; không bắt buộc thống kê lý do |
| **Collect results** | Biến mỗi đầu vào thành một kết quả hợp lệ hoặc một lỗi có lý do | Import, đối soát, báo cáo chất lượng dữ liệu, phản hồi lỗi cho người dùng |

## 4. Bỏ qua phần tử không hợp lệ bằng flatMap

Nếu yêu cầu được phép bỏ dữ liệu sai, hãy đưa logic chuyển đổi vào một hàm chỉ trả về `Stream.of(value)` khi thành công và `Stream.empty()` khi thất bại. Sau đó `flatMap` ghép các stream con thành một luồng giá trị hợp lệ. Không cần cho `null` hay sentinel `0` chảy tới phần sau.

Tệp `KeepOnlyValidDemo.java` (độc lập, Java 8):

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class KeepOnlyValidDemo {
    private static Stream<Integer> parseIdOrEmpty(String raw) {
        if (raw == null) return Stream.empty();

        String cleaned = raw.trim();
        if (cleaned.isEmpty()) return Stream.empty();

        try {
            int n = Integer.parseInt(cleaned);
            return n >= 1 && n <= 1000
                ? Stream.of(n)
                : Stream.empty();
        } catch (NumberFormatException e) {
            return Stream.empty();
        }
    }

    public static void main(String[] args) {
        List<String> inputs = Arrays.asList("12", null, "abc", "0", "7");

        List<Integer> ids = inputs.stream()
            .flatMap(KeepOnlyValidDemo::parseIdOrEmpty)
            .collect(Collectors.toList());

        System.out.println(ids);
    }
}
```

```bash
javac -encoding UTF-8 KeepOnlyValidDemo.java
java KeepOnlyValidDemo
```

```text
[12, 7]
```

Một đầu vào tạo **một** phần tử khi thành công và **không** tạo phần tử khi thất bại. `flatMap` thích hợp vì số phần tử đầu ra có thể là 0 hoặc 1. Đây là lựa chọn có chủ đích: số bản ghi bị bỏ và lý do bị bỏ **không còn trong danh sách kết quả**. Nếu cần các thông tin đó, dùng cách ở mục 5.

Có thể biểu diễn “có thể có một kết quả” bằng `Optional<Integer>` trong Java 8. Tuy nhiên, `Optional.ofNullable(input).map(Integer::parseInt)` **vẫn ném** `NumberFormatException` nếu chuỗi không chuyển được; `Optional` biểu diễn sự có/vắng mặt, không tự động bắt lỗi. Java 8 cũng chưa có `Optional.stream()`, vì vậy ví dụ dùng `Stream.of/empty` để giữ đúng mức API của module.

## 5. Giữ lại mọi lỗi thay vì âm thầm loại bản ghi

Khi nạp dữ liệu thật, bỏ qua hàng sai có thể dẫn tới thiếu dữ liệu mà không ai biết. Thiết kế rõ ràng hơn là **một đầu vào → một đối tượng kết quả**, mang giá trị hợp lệ hoặc lý do lỗi. Phần biến đổi không ghi vào danh sách lỗi dùng chung, nhờ vậy pipeline đơn giản, dễ kiểm thử và không có side effect trong `map`.

Tệp `ParseAuditDemo.java` (độc lập, Java 8):

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class ParseAuditDemo {
    static class ParseResult {
        final String raw;
        final Integer value;
        final String error;

        private ParseResult(String raw, Integer value, String error) {
            this.raw = raw;
            this.value = value;
            this.error = error;
        }

        static ParseResult ok(String raw, int value) {
            return new ParseResult(raw, value, null);
        }

        static ParseResult rejected(String raw, String error) {
            return new ParseResult(raw, null, error);
        }

        boolean isValid() {
            return error == null;
        }
    }

    static ParseResult parseId(String raw) {
        if (raw == null) {
            return ParseResult.rejected(raw, "missing value");
        }

        String normalized = raw.trim();
        if (normalized.isEmpty()) {
            return ParseResult.rejected(raw, "blank value");
        }

        try {
            int n = Integer.parseInt(normalized);
            if (n < 1 || n > 1000) {
                return ParseResult.rejected(raw, "out of range 1..1000");
            }
            return ParseResult.ok(raw, n);
        } catch (NumberFormatException e) {
            return ParseResult.rejected(raw, "invalid integer");
        }
    }

    public static void main(String[] args) {
        List<String> inputs =
            Arrays.asList(" 12 ", null, "abc", "0", "1001", "7", "");

        // Mỗi hàng đầu vào sinh một kết quả, kể cả khi lỗi.
        List<ParseResult> checked = inputs.stream()
            .map(ParseAuditDemo::parseId)
            .collect(Collectors.toList());

        // Chỉ lấy dữ liệu đã được xác nhận hợp lệ.
        List<Integer> accepted = checked.stream()
            .filter(ParseResult::isValid)
            .map(r -> r.value)
            .collect(Collectors.toList());

        System.out.println("Accepted: " + accepted);

        // Demo in lỗi; forEachOrdered giữ thứ tự gặp trong nguồn.
        checked.stream()
            .filter(r -> !r.isValid())
            .forEachOrdered(r ->
                System.out.println("Rejected [" + r.raw + "]: " + r.error));
    }
}
```

```bash
javac -encoding UTF-8 ParseAuditDemo.java
java ParseAuditDemo
```

```text
Accepted: [12, 7]
Rejected [null]: missing value
Rejected [abc]: invalid integer
Rejected [0]: out of range 1..1000
Rejected [1001]: out of range 1..1000
Rejected []: blank value
```

Giải thích:

1. `parseId` kiểm tra null, chuẩn hóa chuỗi, bắt **riêng** `NumberFormatException`, rồi xác minh miền 1–1000.
2. `map(ParseAuditDemo::parseId)` không bỏ phần tử. Dù hợp lệ hay không, mỗi đầu vào trở thành một `ParseResult`.
3. Danh sách `checked` là một “ảnh chụp” kết quả để đọc lại cho nhiều mục đích; một `Stream` đã dùng terminal operation không được sử dụng lại, nhưng có thể tạo stream mới từ `checked`.
4. `filter(ParseResult::isValid)` bảo đảm `r.value` có giá trị theo bất biến do `ParseResult` tạo ra. Nếu ứng dụng phức tạp, hãy đóng gói kết quả hợp lệ và lỗi bằng các kiểu riêng để ngăn trạng thái không nhất quán.
5. `forEachOrdered` ở bước in giữ thứ tự với nguồn có encounter order. In là terminal side effect minh họa; quy trình nghiệp vụ nên ưu tiên trả về danh sách kết quả/lỗi để tầng gọi xử lý.

Khi cần biết **dòng nguồn nào sai**, hãy giữ chỉ số từ trước khi biến đổi, ví dụ dùng `IntStream.range(0, inputs.size()).mapToObj(i -> ...)` để mang `i` cùng kết quả. Đừng chỉ lưu văn bản lỗi vì nhiều hàng có thể có cùng giá trị. Khi ghi log, tránh đưa dữ liệu cá nhân hoặc bí mật thô vào thông báo; mô tả lỗi có mã, vị trí và thông tin đủ để sửa.

## 6. Hợp đồng chuẩn hóa và validation phải được định nghĩa

Việc “chuyển được thành `int`” không đồng nghĩa “hợp lệ cho ứng dụng”. Với ví dụ ID trong khoảng 1–1000, ma trận sau thể hiện kỳ vọng:

| Đầu vào | Sau `trim()` | Kết quả |
| --- | --- | --- |
| `null` | Không chuẩn hóa | Thiếu giá trị |
| `""` hoặc `" "` | `""` | Chuỗi rỗng |
| `" 12 "` | `"12"` | Chấp nhận ID 12 |
| `"abc"` hoặc `"10.5"` | Không phải số nguyên | Lỗi cú pháp |
| `"2147483648"` | Vượt `Integer.MAX_VALUE` | Lỗi chuyển kiểu |
| `"0"` hoặc `"-1"` | Parse thành công | Sai miền 1–1000 |
| `"1001"` | Parse thành công | Sai miền 1–1000 |
| `"7"` hoặc `"1000"` | Parse thành công | Hợp lệ |
| `"+7"` hoặc `"0007"` | Parse thành công | Hợp lệ **nếu** hợp đồng cho phép dấu cộng/số 0 dẫn đầu |

Nếu yêu cầu chỉ chấp nhận **chữ số ASCII, không dấu, không số 0 dẫn đầu**, cần kiểm tra cú pháp bổ sung *trước* khi parse, chẳng hạn bằng regex tương ứng với hợp đồng. `Integer.parseInt` không tự áp những quy tắc nghiệp vụ đó. Regex cũng **không** thay thế xử lý tràn `int`: một chuỗi toàn chữ số quá dài vẫn có thể gây `NumberFormatException`.

Đối với số thập phân, ngày tháng hoặc tiền tệ, hãy dùng parser và kiểu dữ liệu phù hợp cho miền đó; không biến lỗi thành `0`, `Double.NaN` hay ngày mặc định nếu các giá trị ấy có thể bị hiểu là dữ liệu hợp lệ. Việc chuẩn hóa chữ hoa/thường, khoảng trắng, locale, dấu phân cách và timezone phải có quy tắc rõ ràng.

## 7. Những bẫy thường gặp khi kết hợp các toán tử Stream

| Cách làm có vấn đề | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| `map(String::trim).filter(Objects::nonNull)` | Dereference null **trước** khi lọc | Lọc null trước `map` |
| `filter(Objects::nonNull).map(Integer::parseInt)` với dữ liệu thô | Chỉ loại null, không loại ký tự sai hoặc tràn số | Dùng hàm parse có chính sách lỗi |
| `Optional.ofNullable(s).map(Integer::parseInt)` | `Optional.map` không xử lý ngoại lệ parse | Parse trong helper bắt ngoại lệ cụ thể và trả kết quả có nghĩa |
| `map(parseOrNull).mapToInt(Integer::intValue)` | Unbox null gây lỗi | Dùng kết quả hợp lệ, lọc trước khi `mapToInt`, hoặc ánh xạ `IntStream` an toàn |
| `orElse(0)` cho mọi trường hợp lỗi | Trộn “không có/không hợp lệ” với số 0 thật | Dùng `Optional`, kết quả phân loại hoặc lỗi riêng |
| `catch (Exception e) { return null; }` | Che lỗi lập trình/hạ tầng thành lỗi dữ liệu | Bắt ngoại lệ cụ thể; để lỗi bất thường nổi lên |
| `peek(list::add)` để ghi lỗi dùng chung | Side effect khó dự đoán, đặc biệt với parallel/short-circuit | `map` thành đối tượng kết quả rồi `collect` |
| Xem `null` là an toàn trong mọi terminal/collector | Một số API không chấp nhận null; `findFirst`/`findAny` có thể ném NPE nếu phần tử chọn là null | Chuẩn hóa/lọc hoặc dùng kiểu kết quả trước terminal |
| Dùng `parallelStream()` để xử lý/log lỗi theo thứ tự | Thứ tự chạy và side effect có thể thay đổi; lỗi trong nhánh song song khó truy vết | Ưu tiên hàm chuyển đổi thuần, kết quả có vị trí; song song khi đã chứng minh an toàn |

Không nên dựa vào việc `collect(Collectors.toList())` có thể lưu null trong một số tình huống để suy luận rằng mọi collector đều chấp nhận null. Ví dụ, việc tạo bản đồ với `Collectors.toMap` còn có ràng buộc về khóa trùng; null trong đầu ra collector cũng cần được kiểm tra theo đúng API. Ưu tiên giữ pipeline với các giá trị có hợp đồng rõ ràng.

**Lưu ý về lazy/short-circuit:** một pipeline kết thúc bằng `findFirst`, `anyMatch` hay `limit` có thể không duyệt mọi phần tử, nên không thể dùng nó làm phép kiểm tra **tất cả** lỗi đầu vào. Muốn tổng hợp lỗi của toàn lô, duyệt hết nguồn bằng một terminal phù hợp và lưu kết quả. Ngoại lệ ném ra giữa lúc duyệt không tự trở thành “một hàng lỗi” để Stream tiếp tục.

## 8. Cách chọn chiến lược trong ứng dụng

- **Dữ liệu nội bộ đã được bảo đảm sạch:** phép `map` thông thường có thể là đủ, nhưng bất biến dữ liệu phải rõ ràng và được kiểm thử.
- **Dữ liệu bên ngoài, cho phép bỏ qua:** helper trả `Stream.empty()/Stream.of(value)` hoặc một kiểu `Optional` rồi `flatMap`; đo số hàng bỏ nếu nghiệp vụ cần.
- **Nhập liệu hàng loạt hoặc cần phản hồi người dùng:** biến từng hàng thành kết quả hợp lệ/lỗi, giữ vị trí và lý do; xử lý danh sách kết quả ở tầng điều phối.
- **Một hàng sai phải chặn toàn lô:** parse/validate và để lỗi có ngữ cảnh đi tới tầng quản lý giao dịch; không âm thầm đổi lỗi thành dữ liệu mặc định.

Đặt ranh giới trách nhiệm rõ: *parser* giải thích cú pháp, *validator* kiểm tra quy tắc miền, *pipeline* quyết định lọc/biến đổi/thu gom, còn tầng ứng dụng quyết định trả lỗi, tiếp tục hay rollback. Điều này giữ cho các hàm trong `map` dễ kiểm thử và tái sử dụng.

## 9. Tự kiểm tra

**Câu 1.** Vì sao `filter(Objects::nonNull)` không giải quyết được đầu vào `"oops"` khi dùng `Integer.parseInt`?  
**Đáp án:** `"oops"` không null, nhưng không thể parse thành `int`.

**Câu 2.** Vì sao nên phân biệt `"0"` với `"abc"` trong ví dụ ID 1–1000?  
**Đáp án:** `"0"` parse thành công nhưng sai quy tắc miền; `"abc"` sai cú pháp.

**Câu 3.** Khi nào dùng `flatMap` trả `Stream.empty()`?  
**Đáp án:** Khi hợp đồng cho phép biến đầu vào không hợp lệ thành **không có** phần tử đầu ra, và không cần giữ chi tiết lỗi trong kết quả đó.

**Câu 4.** Làm thế nào giữ đủ thông tin để báo từng dòng import sai?  
**Đáp án:** `map` từng hàng thành kết quả có giá trị hoặc lỗi, giữ chỉ số hàng, rồi `collect` toàn bộ kết quả; chỉ sau đó phân loại thành công/thất bại.

**Câu 5.** Vì sao `map(...).findFirst()` không thích hợp để “kiểm tra hết dữ liệu”?  
**Đáp án:** `findFirst` là terminal short-circuit, có thể dừng ngay khi tìm được phần tử đầu tiên.

## Tài liệu tham khảo chính thức

- [Java SE 8 — Stream API](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Stream.html): `filter`, `map`, `flatMap`, `findFirst`, `forEachOrdered`.
- [Java SE 8 — package java.util.stream](https://docs.oracle.com/javase/8/docs/api/java/util/stream/package-summary.html): pipeline, lazy evaluation, terminal operation và quy tắc side effect.
- [Java SE 8 — Integer](https://docs.oracle.com/javase/8/docs/api/java/lang/Integer.html): `parseInt` và `NumberFormatException`.
- [Java SE 8 — Optional](https://docs.oracle.com/javase/8/docs/api/java/util/Optional.html): biểu diễn giá trị có thể vắng mặt; không thay thế quản lý ngoại lệ.

**Điểm cần nhớ:** bảo vệ null **trước dereference**, tách **chuyển kiểu** khỏi **validation**, và chọn có chủ đích giữa **dừng**, **bỏ qua**, hoặc **trả kết quả kèm lỗi**.