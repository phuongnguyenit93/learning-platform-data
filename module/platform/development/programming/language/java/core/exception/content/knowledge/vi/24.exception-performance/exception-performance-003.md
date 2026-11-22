# Không dùng ngoại lệ cho nhánh điều khiển thường xuyên trong Java

> **Chủ đề:** Java Core → Exception → Hiệu năng. Mục tiêu là phân biệt **thất bại bất thường** với **kết quả bình thường nhưng không thỏa điều kiện**, để lựa chọn giữa `if`, giá trị trả về, `Optional`/`OptionalInt`, result type và `throw/catch`. Nội dung giải thích cả chi phí hiệu năng, ngữ nghĩa API, ví dụ Java 17 chạy độc lập, các trường hợp phản ví dụ và cách đo đạc trước khi tối ưu.

## 1. Nguyên tắc: exception không phải câu lệnh if thứ hai

Ngoại lệ trong Java được thiết kế để biểu diễn và lan truyền một **điều kiện bất thường so với hợp đồng thao tác**. Cơ chế `throw`/`catch` giúp thoát khỏi đường xử lý thông thường, chuyển nguyên nhân lên tầng có thể xử lý và tự chạy các khối `finally` cần thiết.

Một nhánh xuất hiện thường xuyên nhưng **được dự kiến là kết quả hợp lệ** — không tìm thấy đối tượng, hết dữ liệu, người dùng bỏ trống ô tìm kiếm, hàng đợi tạm rỗng — thường nên được biểu diễn rõ bằng điều kiện hoặc kiểu kết quả. Nếu viết `throw` cho những trường hợp này trong vòng lặp nóng, bạn dễ làm mã khó đọc, làm nhiễu log, che giấu lỗi thật và trả thêm chi phí của cơ chế exception.

Ví dụ tư duy:

- **Bình thường:** không có thêm dòng nào trong file; một hàm đọc tới cuối luồng trả sentinel `-1` hoặc `null` theo contract.
- **Bình thường:** tra một key hợp lệ nhưng không có phần tử; API trả null/`Optional.empty()`/`Result.notFound` theo thiết kế.
- **Bất thường:** file chưa đọc xong nhưng storage phát sinh lỗi I/O; có thể ném `IOException`.
- **Bất thường:** một bất biến nội bộ bị phá, trạng thái API không hợp lệ hoặc caller vi phạm contract đã công bố; có thể ném exception thích hợp.
- **Theo ngữ cảnh:** nhập văn bản không parse được là bình thường với form tương tác nhiều đầu vào; nhưng có thể là lỗi cấu hình nghiêm trọng khi đọc một manifest mà nhà phát hành cam kết luôn hợp lệ.

Vì vậy, không có quy tắc “bất kỳ lỗi nào cũng không được ném” hay “cứ gọi API ném exception là code sai”. Điều quan trọng là **tần suất dự kiến, hợp đồng và điểm có quyền xử lý**.

## 2. Một phản ví dụ: duyệt danh sách bằng IndexOutOfBoundsException

Đây là **minh họa cách làm không nên dùng**:

~~~java
// Chỉ là đoạn phương thức, giả định List<String> items đã tồn tại.
int index = 0;
try {
    while (true) {
        process(items.get(index++));
    }
} catch (IndexOutOfBoundsException end) {
    // Cố coi lỗi vượt chỉ số là tín hiệu kết thúc.
}
~~~

Vấn đề:

1. Hết danh sách là điều kiện bình thường và có thể kiểm tra bằng `index < items.size()` hoặc iterator.
2. `get(index)` và mã trong `process(...)` đều có thể phát sinh exception; cách bắt quá rộng ở vòng ngoài có thể nhầm một bug thực sự với “đã duyệt xong”.
3. Một số triển khai `List` có thể thay đổi đồng thời; ví dụ không đưa ra hợp đồng consistency khi cấu trúc bị cập nhật.
4. Người đọc phải hiểu ngầm rằng exception được dùng như cách thoát loop, trong khi `for` hoặc `for-each` biểu đạt ý định trực tiếp hơn.
5. Tạo và ném exception thường xuyên khiến chương trình chịu thêm chi phí; mức chi phí cụ thể phải được đo trên JVM và tải thực tế.

Cách diễn đạt đúng:

~~~java
// Chỉ là đoạn phương thức, giả định List<String> items đã tồn tại.
for (String item : items) {
    process(item);
}
~~~

Hoặc khi thực sự cần chỉ số:

~~~java
for (int i = 0; i < items.size(); i++) {
    process(items.get(i));
}
~~~

**Ngoại lệ không nên thay thế điều kiện vòng lặp nếu chính điều kiện đó là một phần bình thường của thuật toán.**

## 3. Chi phí thực tế của việc ném ngoại lệ đến từ đâu?

Không nên hiểu đơn giản “từ khóa `throw` chậm”. Một lần exception thất bại có thể gồm nhiều công việc:

1. **Tạo đối tượng `Throwable`:** constructor của nhiều loại exception sử dụng `fillInStackTrace()` để ghi nhận thông tin stack, thường tốn hơn việc trả một giá trị đơn giản.
2. **Stack unwinding:** runtime đi ngược các frame cho tới handler phù hợp, thực hiện xử lý cleanup như `finally` hoặc try-with-resources.
3. **Ảnh hưởng tối ưu của JVM:** đường chạy khác thường có thể không được JIT tối ưu giống đường thành công; việc chuyển điều khiển và deoptimization có thể ảnh hưởng kết quả.
4. **Cấp phát và GC:** nhiều exception mới có thể tăng áp lực cấp phát và thu gom rác; mức ảnh hưởng phụ thuộc JVM, loại lỗi và khối lượng công việc.
5. **Xử lý/ghi log:** định dạng stack trace, serialization/logging exception hoặc chuyển nó qua nhiều tầng có thể còn tốn hơn việc ném riêng lẻ.
6. **Khả năng quan sát:** lượng log lỗi giả quá nhiều khiến alert, dashboard và việc phân loại sự cố kém hiệu quả.

Tuy nhiên cần chính xác:

- **Không có hằng số tốc độ cố định** cho exception so với `if`; kết quả thay đổi theo JVM, compiler, mức nóng của call site, số frame và tần suất lỗi.
- **Không phải mọi throwable đều xây stack trace đầy đủ:** một số exception/constructor tùy chọn bỏ stack trace, và JVM có thể có tối ưu đặc biệt cho những tình huống lặp lại.
- HotSpot có các hành vi tối ưu liên quan exception, nhưng **không dựa vào chi tiết riêng JVM** để biện hộ cho một nhánh điều khiển khó hiểu.
- Nếu exception **rất hiếm**, overhead của đường lỗi có thể không đáng kể; thiết kế API rõ nghĩa và bảo toàn nguyên nhân quan trọng hơn việc loại bỏ bằng mọi giá.
- Một kiểu trả về phức tạp hơn (`Optional`, result object) cũng có chi phí: cấp phát, boxing, phân nhánh hoặc chuyển dữ liệu. Không mặc định rằng thay `throw` bằng `Optional` luôn nhanh hơn.

**Tối ưu đúng là chọn ngữ nghĩa trước rồi đo đường nóng**; hiệu năng là một lý do mạnh, nhưng không phải lý do duy nhất.

## 4. Những nhánh thông thường nên có biểu diễn riêng

| Tình huống | Không nên lạm dụng | Biểu diễn dễ hiểu hơn | Lưu ý |
|---|---|---|---|
| Duyệt hết collection | Catch `IndexOutOfBoundsException` | `for`, iterator, `hasNext()` | Cần xét đồng thời nếu collection bị sửa |
| Hết dữ liệu byte | Catch exception “end of input” | `InputStream.read() == -1` | `IOException` vẫn chỉ lỗi I/O |
| Hết dòng văn bản | Catch `NullPointerException` sau `readLine()` | `readLine() == null` | Dòng rỗng `""` khác EOF |
| Hết phần tử iterator | Catch `NoSuchElementException` | `iterator.hasNext()` | Nếu có sửa đồng thời, vẫn phải tuân contract |
| Bản ghi không tồn tại | Throw rồi catch `NoSuchElementException` quanh lookup lặp lại | `Optional.empty()` hoặc result type | API có thể chủ động chọn throw cho invariant khác |
| Queue tạm rỗng | Catch `NoSuchElementException` từ `remove()` | `poll()` trả `null` khi rỗng | Chỉ phù hợp khi `null` không phải phần tử hợp lệ |
| Số nhập không hợp lệ thường xuyên | Gọi `parseInt` rồi catch trong mỗi vòng nóng | Parser có kết quả success/failure | Validate không được làm sai grammar/overflow |
| Quy tắc nghiệp vụ bị từ chối | Catch một exception cho mọi request “không đủ tồn kho” | Kết quả domain rõ ràng nếu việc từ chối là dự kiến | Vẫn có thể dùng exception ở API có contract khác |
| Option cấu hình bắt buộc thiếu | Bắt exception rồi dùng giá trị mặc định tùy tiện | Kiểm tra config lúc startup và fail fast khi sai | Đây có thể là failure thật, không nên giấu |

**Không tự thay một API chỉ vì có từ `Exception` trong chữ ký.** Nếu giao diện thư viện chọn ném checked/unchecked exception cho tình huống cụ thể, adapter của bạn có thể phải bắt nó ở ranh giới và chuyển sang kiểu kết quả phù hợp với miền nghiệp vụ.

## 5. Ví dụ Java 17 chạy độc lập: parse dữ liệu thường xuyên

Giả sử một bộ đọc import nhận nhiều chuỗi từ người dùng; dữ liệu không hợp lệ là chuyện dự kiến và cần được đếm/hiển thị. Có hai cách minh họa:

- Cách A: gọi `Integer.parseInt` trên mỗi chuỗi, bắt `NumberFormatException` để ghi nhận trường hợp không parse được.
- Cách B: hàm riêng cho **chuỗi số nguyên không âm hệ 10 chỉ chứa ký tự ASCII '0'..'9'**, trả `OptionalInt.empty()` khi không hợp lệ, không dùng exception làm kết quả từ chối thông thường.

Hai cách được thử trên cùng dữ liệu hợp lệ/phủ định tương đương; **chúng không có grammar giống hệt nhau cho mọi input**: `Integer.parseInt` cho phép dấu `+`/`-` theo quy tắc của nó, trong khi hàm kiểu kết quả ở ví dụ chỉ cho phép chữ số ASCII không dấu. Đây là **lựa chọn contract có chủ đích** cho dữ liệu nhập; không được coi parser này là thay thế drop-in cho mọi lần gọi `parseInt`.

Lưu toàn bộ thành **`ExceptionControlFlowDemo.java`**:

~~~java
import java.io.IOException;
import java.io.StringReader;
import java.util.OptionalInt;

public class ExceptionControlFlowDemo {
    record Summary(int accepted, int rejected, long sum) { }

    private static final String[] INPUTS =
            {"42", "7", "x", "", "2147483648", "001"};

    static Summary viaExceptions() {
        int accepted = 0;
        int rejected = 0;
        long sum = 0;

        for (String text : INPUTS) {
            try {
                int value = Integer.parseInt(text);
                accepted++;
                sum += value;
            } catch (NumberFormatException ex) {
                // Dữ liệu nhập không parse được là nhánh dự kiến.
                rejected++;
            }
        }
        return new Summary(accepted, rejected, sum);
    }

    static OptionalInt parseUnsignedDecimal(String text) {
        if (text == null || text.isEmpty()) {
            return OptionalInt.empty();
        }

        int value = 0;
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            if (c < '0' || c > '9') {
                return OptionalInt.empty();
            }

            int digit = c - '0';
            if (value > (Integer.MAX_VALUE - digit) / 10) {
                return OptionalInt.empty(); // Tránh overflow.
            }
            value = value * 10 + digit;
        }
        return OptionalInt.of(value);
    }

    static Summary viaResult() {
        int accepted = 0;
        int rejected = 0;
        long sum = 0;

        for (String text : INPUTS) {
            OptionalInt parsed = parseUnsignedDecimal(text);
            if (parsed.isPresent()) {
                accepted++;
                sum += parsed.getAsInt();
            } else {
                rejected++;
            }
        }
        return new Summary(accepted, rejected, sum);
    }

    static void print(String label, Summary summary) {
        System.out.printf(
                "%s: accepted=%d rejected=%d sum=%d%n",
                label, summary.accepted(),
                summary.rejected(), summary.sum());
    }

    public static void main(String[] args) throws IOException {
        Summary withExceptions = viaExceptions();
        Summary withResult = viaResult();

        print("exceptions", withExceptions);
        print("results", withResult);
        System.out.println("same summary: "
                + withExceptions.equals(withResult));

        StringReader reader = new StringReader("ab");
        int count = 0;
        while (reader.read() != -1) { // EOF là điều kiện thông thường.
            count++;
        }
        System.out.println("characters: " + count);
        System.out.println("read after EOF: " + reader.read());
    }
}
~~~

Biên dịch và chạy với JDK 17 hoặc mới hơn:

~~~bash
javac ExceptionControlFlowDemo.java
java ExceptionControlFlowDemo
~~~

**Stdout chính xác:**

~~~text
exceptions: accepted=3 rejected=3 sum=50
results: accepted=3 rejected=3 sum=50
same summary: true
characters: 2
read after EOF: -1
~~~

Giải thích:

1. Dữ liệu hợp lệ `"42"`, `"7"` và `"001"` lần lượt cho 42, 7 và 1, tổng 50. `"x"`, `""` và `"2147483648"` bị từ chối.
2. `Integer.parseInt` ném `NumberFormatException` cho ba chuỗi không parse được. Đường B trả `OptionalInt.empty()`, không cần ném exception cho trường hợp từ chối.
3. Parser B kiểm tra ký tự và **tràn số trước khi nhân/cộng**. Nếu quên điều kiện overflow, `int` của Java có thể vòng giá trị âm mà không tự ném lỗi.
4. `OptionalInt.of(0)` là kết quả **thành công** khác `OptionalInt.empty()`. Nếu dùng một sentinel như `-1`, phải đảm bảo `-1` không nằm trong miền đầu ra hợp lệ; với số nguyên có thể âm, sentinel dễ gây mơ hồ.
5. `StringReader.read()` trả `-1` khi hết dữ liệu theo contract; đây là tín hiệu EOF bình thường, không phải lỗi phải tạo exception.
6. Chương trình **minh họa thiết kế và kết quả**, không phải benchmark hiệu năng. Nó không chứng minh đường B luôn chạy nhanh hơn đường A trên mọi JVM/dataset.

Nếu parser là một thành phần được dùng lại, hãy tài liệu hóa grammar rõ ràng: ký tự chấp nhận, dấu âm/dương, khoảng trắng, số 0 đầu, kích thước giới hạn, ký tự Unicode và hành vi với null. Việc “không throw khi input sai” không cho phép thay đổi ngầm tập dữ liệu được chấp nhận.

## 6. Dùng OptionalInt, Optional<T> và result type đúng ngữ nghĩa

### 6.1. OptionalInt khi kết quả có thể vắng mặt

`OptionalInt` biểu diễn **có một giá trị `int`** hoặc **không có giá trị**, tránh sentinel nằm trong miền dữ liệu. Nó có thể phù hợp với hàm `tryParse...`, tìm giá trị thống kê hoặc phép tìm kiếm.

~~~java
// Mã minh họa trong một phương thức.
OptionalInt result = parseUnsignedDecimal(userInput);
if (result.isPresent()) {
    use(result.getAsInt());
} else {
    showValidationError();
}
~~~

`userInput`, `use` và `showValidationError` là các thành phần ứng dụng giả định; đoạn này không phải chương trình độc lập. `OptionalInt` giúp caller nhìn thấy nhánh thất bại trong kiểu trả về nhưng chỉ mã hóa **có/không**, không nêu được *vì sao* thất bại.

### 6.2. Result type khi cần biết nguyên nhân từ chối

Nếu UI muốn báo “rỗng”, “không phải số” hay “vượt miền”, một `Result` có dữ liệu lỗi rõ nghĩa thường tốt hơn tạo exception mới cho mỗi chuỗi sai.

~~~java
// Các kiểu có thể đặt bên trong một lớp Java 17.
enum ParseError {
    EMPTY, NOT_DECIMAL, OVERFLOW
}

sealed interface ParseResult
        permits Parsed, Rejected {
}

record Parsed(int value) implements ParseResult {
}

record Rejected(ParseError reason) implements ParseResult {
}
~~~

Đây là **khai báo kiểu minh họa**, chưa có hàm parser đầy đủ. Caller có thể dùng `instanceof` hoặc pattern matching phù hợp Java 17 để phân nhánh theo kiểu. Một result type có thể mang message, offset ký tự sai hoặc mã lỗi ổn định, nhưng đừng nhồi stack trace vào mỗi kết quả từ chối bình thường.

### 6.3. Sentinel có hợp đồng rõ

`InputStream.read()` trả một số trong `0..255` khi đọc được byte, và `-1` khi EOF. `-1` an toàn vì không phải một giá trị byte hợp lệ của kết quả đọc đơn lẻ.

Trái lại, nếu một hàm tìm vị trí được phép trả vị trí âm, dùng `-1` làm “không tìm thấy” có thể gây mơ hồ. Sentinel chỉ tốt nếu **miền kết quả và tài liệu API** đảm bảo có một giá trị ngoài miền hợp lệ.

### 6.4. Null và trạng thái vắng mặt

`Map.get(key)` có thể trả `null` do thiếu key **hoặc** do key tồn tại và được ánh xạ tới `null` (với triển khai cho phép null). Vì thế khi cần phân biệt hai trạng thái, có thể cần `containsKey` hoặc một API có kiểu kết quả giàu ngữ nghĩa hơn.

Không thay tất cả exception thành null: null là tín hiệu yếu, và nếu không kiểm tra, nó có thể gây `NullPointerException` ở vị trí khó điều tra hơn. Đừng biến một lỗi bất ngờ thành null chỉ để “không dùng exception”.

## 7. Phân loại lỗi dự kiến theo tần suất và khả năng phục hồi

Cùng một tình huống có thể cần cách diễn đạt khác tùy bối cảnh:

| Hoạt động | Lỗi không parse được xuất hiện thế nào? | Gợi ý |
|---|---|---|
| Nhập từng ký tự vào ô số trên UI | Rất thường xuyên trong lúc người dùng đang gõ | Validator hoặc parse result, không log ERROR mỗi phím |
| Import một triệu bản ghi chưa được kiểm soát | Một tỷ lệ dự kiến không hợp lệ | Parse result + error code per record, thống kê theo batch |
| Đọc biến môi trường bắt buộc lúc startup | Lỗi hiếm, cấu hình không được sai | Exception fail fast với tên cấu hình và nguyên nhân |
| Giải mã một token đã ký từ nguồn không tin cậy | Nhiều token sai có thể xuất hiện do client | Xác thực/decoder API có kết quả phù hợp, giới hạn tài nguyên, không log secret |
| Chuyển kiểu giá trị mà code đã kiểm soát | Sai kiểu là bug hoặc vi phạm invariant | Exception giúp lộ lỗi lập trình |
| Đọc dữ liệu qua socket sau khi kết nối mất | Sự cố I/O cần caller xử lý hoặc retry | `IOException`/loại lỗi kết nối thích hợp |

**Đừng đổi lỗi cấu hình nghiêm trọng thành giá trị mặc định im lặng** chỉ để tránh exception: điều đó có thể khiến ứng dụng chạy với trạng thái sai và khó điều tra hơn.

## 8. Tránh kiểm tra “đoán lỗi” trước rồi vẫn phải parse lại

Một ý tưởng phổ biến là chạy regex trước `Integer.parseInt`:

~~~java
// Minh họa, không phải parser tổng quát.
if (input.matches("[0-9]+")) {
    int value = Integer.parseInt(input);
}
~~~

Cần lưu ý:

- Regex này **không kiểm tra overflow**. Một chuỗi 100 chữ số chỉ gồm ký tự `0..9` vẫn khiến `parseInt` ném exception.
- `matches` phải xử lý biểu thức chính quy; với workload cụ thể, bước này có thể tốn thêm CPU hơn việc parse trực tiếp.
- Grammar có thể không khớp: `parseInt` chấp nhận dấu cộng/trừ (với đầu vào và radix phù hợp), regex `[0-9]+` thì không.
- Có nguy cơ kiểm tra hai lần trên đường thành công: regex duyệt chuỗi, sau đó parser lại duyệt.
- Nếu input rất dài và không tin cậy, kiểm soát độ dài và giới hạn tính toán cũng quan trọng như chọn kiểu lỗi.

Một parser chuyên biệt kiểu `tryParse` nên kiểm tra **đúng grammar trong một lượt**, kiểm soát overflow, không ném exception trên nhánh từ chối thông thường. Nhưng việc tự viết parser có nguy cơ bug; nếu API chuẩn chỉ được gọi vài lần ở ranh giới, `Integer.parseInt` với `catch` có thể vẫn là lựa chọn tốt hơn về đơn giản và bảo trì.

## 9. Điều kiện bất thường vẫn nên là exception

Không dùng exception cho nhánh thường xuyên **không đồng nghĩa từ bỏ exceptions**. Hãy ném khi đó là cách phù hợp để diễn đạt contract:

- Tham số không hợp lệ so với public API: `IllegalArgumentException`, `NullPointerException` tại ranh giới (ví dụ `Objects.requireNonNull`).
- Trạng thái đối tượng không cho phép thao tác: `IllegalStateException`.
- Lỗi I/O không phải EOF bình thường: `IOException`.
- Vi phạm invariant, bug lập trình hoặc dependency thất bại mà tầng hiện tại không giải quyết được.
- Một thư viện đặt exception làm hợp đồng cho tình huống cụ thể; adapter có thể chuyển sang result type ở ranh giới phù hợp.

Một API được thiết kế theo quy tắc **exceptional failure** có thể lựa chọn:

~~~java
// Trích đoạn trong phương thức xác nhận đơn hàng.
if (orderAlreadyCommitted) {
    throw new IllegalStateException("order already committed");
}
~~~

Nếu trạng thái `orderAlreadyCommitted` là một lỗi gọi API hiếm, exception rất rõ nghĩa. Nhưng nếu hệ thống nhận lại cùng một message nhiều lần theo cơ chế at-least-once, “đã xử lý trước đó” có thể là một kết quả idempotent dự kiến, nên một enum outcome như `ALREADY_APPLIED` phù hợp hơn.

Vì vậy, hãy hỏi: *Caller có cần và có thể xử lý trường hợp này như một kết quả bình thường không? Nó xuất hiện thường xuyên đến mức nào?*

## 10. Exception làm control flow gây vấn đề cả về khả năng đọc

Ngoài CPU, cách dùng exception sai làm thay đổi **cấu trúc suy luận**:

~~~java
// Phản ví dụ minh họa; các hàm là giả định.
try {
    Item item = repository.findOrThrow(id);
    render(item);
} catch (NoSuchElementException ex) {
    renderEmptyState();
}
~~~

Đoạn này có thể hợp lý nếu `findOrThrow` có contract “bắt buộc tồn tại”. Nhưng nếu tìm không thấy là tình huống thường xuyên của một hộp tìm kiếm, ý định rõ hơn là:

~~~java
// Mã minh họa.
Optional<Item> item = repository.find(id);
if (item.isPresent()) {
    render(item.get());
} else {
    renderEmptyState();
}
~~~

Những nhược điểm của việc dùng exception trong đường thường xuyên:

1. Đọc code phải tìm handler có thể ở xa call site mới biết kết quả thông thường.
2. Catch sai tầng hoặc catch quá rộng có thể che bug thật.
3. Exception thường mang ý nghĩa “đã xảy ra lỗi”, dễ dẫn tới log và alert sai.
4. Kết quả không được biểu diễn rõ trong chữ ký trả về, làm caller bất ngờ.
5. Khó compose nhiều trạng thái expected failure nếu chỉ dùng một kiểu exception mơ hồ.

Ngược lại, result type quá nhiều nhánh có thể khiến code rườm rà nếu failure thực sự rất hiếm và không thể phục hồi ở tầng hiện tại. **Chọn cấu trúc biểu đạt ý định của API, không chạy theo một khẩu hiệu tối ưu.**

## 11. Chi phí stack trace: hiểu đúng, không tắt mù quáng

`Throwable` có khả năng lưu stack trace giúp người điều tra biết ngoại lệ phát sinh ở đâu. Điều này rất quan trọng với lỗi bất ngờ.

Một số cách “tối ưu” sai:

- Tạo một exception duy nhất rồi dùng lại cho mọi lỗi để tránh allocation. Stack trace có thể trở nên lỗi thời, thông tin context không đúng request và khó hiểu khi có nhiều luồng.
- Gọi `setStackTrace(new StackTraceElement[0])` cho mọi exception: mất dữ liệu điều tra trong khi chi phí tạo stack có thể đã phát sinh.
- Tạo custom exception loại bỏ stack trace cho tất cả lỗi để chạy nhanh hơn: có thể tiết kiệm nhưng đánh đổi observability, cần contract/thử nghiệm rất rõ.
- Dựa vào cơ chế *fast throw* của HotSpot như một bảo đảm hiệu năng chung. Chi tiết tối ưu có thể thay đổi theo JVM/version/cấu hình.
- Chỉ đo thời gian `throw` bằng một vòng lặp microbenchmark thiếu warmup và kết luận rằng kết quả áp dụng cho production.

Nếu thật sự có một nhánh thất bại lặp lại dày đặc và việc ghi stack trace **không có giá trị**, thiết kế nó thành normal result thường rõ ràng hơn thao tác tùy biến stack trace của exception.

## 12. Không dựa vào catch để xử lý lỗi API bị dùng sai liên tục

Lấy ví dụ liên tục gọi `List.get(index)` với chỉ số có thể không hợp lệ:

~~~java
// Không lý tưởng nếu index ngoài miền là tình huống thông thường.
try {
    consume(items.get(index));
} catch (IndexOutOfBoundsException ex) {
    useDefault();
}
~~~

Trong code xử lý UI khi chỉ số đến từ người dùng và out-of-range là tình huống dự kiến, có thể:

~~~java
if (index >= 0 && index < items.size()) {
    consume(items.get(index));
} else {
    useDefault();
}
~~~

Tuy nhiên, với collection bị truy cập đồng thời, kiểm tra `size()` trước rồi `get()` **không tự bảo đảm nguyên tử**: một thread khác có thể thay đổi danh sách giữa hai lời gọi. Cần tuân contract thread-safety của collection, dùng snapshot hoặc cơ chế đồng bộ phù hợp. Đừng đánh đổi exception control flow lấy một lỗi race mới.

Với external resource như file, đọc/ghi và mạng, phép kiểm tra trước đôi khi không loại được failure do trạng thái thay đổi giữa check và use. Khi lỗi bất thường có thể xảy ra, vẫn phải có đường xử lý exception phù hợp.

## 13. Logging: không biến một kết quả bình thường thành sự cố

Nếu hàng triệu dòng import có 5% không hợp lệ, ghi một stack trace ERROR cho từng dòng là một dạng phí tổn đáng kể và gây nhiễu.

Thay vì:

~~~java
// Phản ví dụ minh họa, log và parseInt do ứng dụng cung cấp.
try {
    int value = Integer.parseInt(input);
    save(value);
} catch (NumberFormatException ex) {
    log.error("invalid input", ex);
}
~~~

Cân nhắc một parser kết quả và **tổng hợp thống kê có giới hạn**:

~~~java
// Minh họa: parseUnsignedDecimal và metrics là các thành phần đã khai báo.
OptionalInt parsed = parseUnsignedDecimal(input);
if (parsed.isPresent()) {
    save(parsed.getAsInt());
} else {
    metrics.incrementRejectedCount();
}
~~~

Nếu cần trợ giúp người dùng sửa dữ liệu, có thể lưu error code và vị trí dòng cho một số lỗi phù hợp, áp dụng giới hạn kích thước, không log raw payload chứa dữ liệu nhạy cảm. Một batch có thể ghi `importId`, `accepted`, `rejected`, `errorCategories` thay vì một triệu stack traces.

**Ghi log exception khi nó giúp điều tra lỗi thật**; phân biệt ERROR, WARN, INFO và metrics theo mức độ ảnh hưởng. “Không throw” không tự khiến hệ thống quan sát tốt hơn nếu bạn nuốt hết nguyên nhân và không đo kết quả từ chối.

## 14. Benchmarks: cách kiểm chứng thay vì suy đoán

Để quyết định một nhánh exception có gây vấn đề hiệu năng không, cần đo các trường hợp gần với production. **Không tự tạo một kết luận tốc độ từ số lần chạy `System.nanoTime()` trong một loop đơn giản**: JIT warmup, dead-code elimination, inlining, allocation elimination, constant folding và GC có thể làm kết quả sai lệch.

### Chọn tỷ lệ dữ liệu hợp lệ/thất bại

Benchmark nên có:

- 100% hợp lệ.
- 99,9% hợp lệ (lỗi rất hiếm).
- 95% hợp lệ, 5% từ chối.
- 50% hợp lệ, 50% từ chối.
- Các input dài ngắn và phân bố lỗi thực tế (ký tự sai ở đầu/cuối, overflow).
- Trường hợp dữ liệu biến đổi, không toàn constant để JIT tối ưu quá mức.

Nếu branch bình thường hầu như không bị lỗi, `parseInt` chuẩn có thể rất hiệu quả và đơn giản; parser riêng có thể gây thêm overhead. Nếu dữ liệu sai rất thường xuyên, chi phí exception có thể chi phối throughput. **Mức cụ thể phải đo**.

### Công cụ: JMH

Java Microbenchmark Harness (JMH, dự án OpenJDK) cung cấp warmup, nhiều lượt đo, fork JVM, tránh một số lỗi benchmark phổ biến. Một **khung mã minh họa phụ thuộc JMH**:

~~~java
// Minh họa: cần dependency org.openjdk.jmh, không phải Java SE độc lập.
// @State(Scope.Thread)
// public class ParseBenchmark {
//     @Param({"0", "5", "50"})
//     public int invalidPercent;
//
//     @Benchmark
//     public int exceptionPath() {
//         // Dùng input thay đổi với đúng tỷ lệ invalidPercent,
//         // gọi parser thật, tiêu thụ toàn bộ kết quả.
//     }
//
//     @Benchmark
//     public int resultPath() {
//         // Dùng cùng input, cùng grammar và cùng chính sách xử lý,
//         // nhưng biểu diễn thất bại không qua exception.
//     }
// }
~~~

Khung trên là **sơ đồ thực nghiệm**, không phải một benchmark đầy đủ và không có đầu ra/điểm số được bịa đặt. Khi triển khai JMH thật cần đo kết quả được sử dụng để tránh compiler bỏ code, điều chỉnh dữ liệu để hai nhánh làm **công việc tương đương** và tránh tạo input trong vùng đang đo nếu điều đó không thuộc workload thật.

Các thông số nên quan sát thêm:

| Chỉ số | Ý nghĩa |
|---|---|
| Throughput (ops/s) | Có thể xử lý bao nhiêu phần tử mỗi giây |
| Latency trung bình và phân vị | Nhánh lỗi có kéo dài tail latency không |
| Allocation rate (B/op) | Có bao nhiêu byte cấp phát mỗi thao tác |
| GC count/time | Có thêm áp lực thu gom rác không |
| CPU profile | Thời gian tập trung ở parser, Throwable hay logging |
| Error ratio | Tần suất thực của trường hợp thất bại |
| Độ rõ API và khả năng điều tra | Không đổi correctness/observability lấy vài phần trăm giả định |

Đừng chỉ so sánh đường lỗi mà bỏ qua chi phí đường thành công. Đồng thời đừng thay đổi semantics parser giữa hai benchmark: nếu một bên nhận `+1` còn bên kia không, phép so sánh đã không tương đương.

## 15. Ngoại lệ hiếm và EAFP: khi nào bắt lỗi trực tiếp lại đúng?

Một số tình huống không thể tránh race giữa kiểm tra và thực hiện. Ví dụ kiểm tra file có tồn tại, sau đó mở file:

~~~java
// Trích đoạn minh họa; không loại được race.
if (java.nio.file.Files.exists(path)) {
    // File vẫn có thể bị xóa/đổi quyền trước khi mở.
    readFrom(path);
}
~~~

Ở đây, dù đã kiểm tra, việc mở/đọc vẫn có thể thất bại bởi `IOException`. Thiết kế đúng vẫn phải xử lý lỗi thao tác thật. Nếu file bắt buộc phải có và lỗi mở file là bất thường, dùng exception **đúng mục đích**.

**EAFP** (easier to ask forgiveness than permission, thuật ngữ phổ biến trong lập trình) không phải lý do để lạm dụng exception cho EOF hoặc mỗi phần tử loop. Nó hữu ích khi:

- Điều kiện không thể kiểm tra đáng tin trước khi thao tác.
- Failure hiếm hoặc có ý nghĩa bất thường.
- API chỉ cung cấp exception làm hợp đồng chính thức.
- Cần giữ cause, cleanup tài nguyên và chính sách retry.

Ngược lại, **LBYL** (look before you leap, kiểm tra trước) cũng không luôn nhanh hơn hoặc an toàn hơn nếu tạo bước kiểm tra trùng lặp, làm sai grammar hoặc mắc lỗi TOCTOU.

Kết luận của phần này: chọn dựa trên **semantics của operation, thread-safety và thực nghiệm**, chứ không cố thay mọi try/catch bằng if.

## 16. Không che bug bằng exception catch quá rộng

Một vòng lặp kiểu:

~~~java
while (true) {
    try {
        processNext();
    } catch (Exception ignored) {
        continue;
    }
}
~~~

có thể nuốt:

- Lỗi dữ liệu dự kiến.
- `NullPointerException` do bug.
- Lỗi kết nối tạm thời cần backoff.
- `InterruptedException` từ thao tác chặn, làm chương trình không tôn trọng tín hiệu hủy.
- Lỗi khiến trạng thái đối tượng không còn hợp lệ.

Cách đúng là xác định loại kết quả expected và loại failure khác nhau. Nếu worker cần chạy tiếp sau dữ liệu không hợp lệ, dùng một result type để ghi nhận rejected record. Nếu I/O thất bại, thực hiện retry/backoff có giới hạn hoặc chuyển lỗi lên tầng điều phối. Nếu bị ngắt, truyền `InterruptedException` khi có thể; nếu không, thường cần `Thread.currentThread().interrupt()` rồi rời vòng lặp.

Ví dụ dưới đây là **mã minh họa**, không phải chương trình độc lập:

~~~java
while (!Thread.currentThread().isInterrupted()) {
    try {
        String raw = queue.take();
        OptionalInt parsed = parseUnsignedDecimal(raw);
        if (parsed.isEmpty()) {
            recordRejected();
            continue;
        }
        process(parsed.getAsInt());
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        break;
    } catch (java.io.IOException ex) {
        handleInfrastructureFailure(ex);
        break;
    }
}
~~~

Để đoạn code hợp lệ trong dự án, `process` phải khai báo phù hợp `throws IOException`, cùng với `queue`, `recordRejected` và `handleInfrastructureFailure` được định nghĩa. Mục đích là **giữ riêng expected rejection, cancellation và infrastructure failure**.

## 17. Những lỗi thiết kế thường gặp

1. **Coi EOF là exception:** dùng `read() == -1` hoặc `readLine() == null` theo API; giữ `IOException` cho lỗi đọc thật.
2. **Dùng `IndexOutOfBoundsException` làm điều kiện kết thúc:** thay bằng iterator/`for`/`hasNext()`.
3. **Dùng `NoSuchElementException` cho “không tìm thấy” thường xuyên:** cân nhắc `Optional` hoặc result type; nhưng nếu contract bắt buộc tồn tại, exception vẫn hợp lý.
4. **Coi input invalid là bug:** với UI/import, đó thường là kết quả dự kiến; phân biệt với sai cấu hình/invariant.
5. **Bắt `RuntimeException` cho mọi input:** nuốt cả lỗi lập trình không liên quan.
6. **Tự viết validator lệch với parser:** không đồng nhất dấu `+`/`-`, Unicode, whitespace hoặc overflow.
7. **Prevalidate rồi parse lại mà không đo:** quét chuỗi hai lần có thể chậm hơn; còn gặp race hoặc loại input không đồng nhất.
8. **Dùng sentinel nằm trong miền giá trị hợp lệ:** caller không phân biệt failure với kết quả thật.
9. **Thay exception bằng null vô tội vạ:** dễ phát sinh `NullPointerException` tại nơi xa hơn.
10. **Dùng Optional mọi nơi vì “nhẹ”:** có thể làm API phức tạp và tốn tài nguyên, cần lý do semantics rõ.
11. **Đo tốc độ bằng một loop `nanoTime` duy nhất:** kết quả có thể phản ánh JIT/GC chứ không phải code thật.
12. **Lấy kết quả microbenchmark làm lý do đổi public API ngay:** phải xét compatibility và chi phí chuyển đổi cho caller.
13. **Tắt stack trace cho mọi exception:** bỏ mất dữ liệu chẩn đoán lỗi hiếm, nghiêm trọng.
14. **Tái sử dụng exception object chung xuyên các request:** context/stack có thể sai và khó debug.
15. **Log ERROR cho mỗi bản ghi bị từ chối:** tăng nhiễu, tăng I/O và cardinality, cần thống kê có giới hạn.
16. **Catch rồi bỏ interrupt:** làm worker khó dừng và che dấu chính sách cancellation.
17. **Dùng exception để rollback rồi coi như “bình thường”:** việc ném lỗi không tự hoàn tác trạng thái; cần thiết kế commit/transaction riêng.

## 18. Chiến lược thay đổi code hiện có an toàn

Khi gặp một hot path đang dùng exception để phân nhánh:

1. **Xác định contract hiện tại:** lỗi có thể là một trạng thái “bình thường” được caller kỳ vọng không? Những loại exception nào đang bị bắt?
2. **Đo tần suất:** tỷ lệ lỗi, số lần gọi, thời gian dành cho Throwable construction, logs, allocation và GC.
3. **Chọn kiểu kết quả:** boolean, `OptionalInt`, `Optional<T>`, enum/status code hay sealed result theo thông tin caller cần.
4. **Bảo toàn grammar và miền dữ liệu:** thử input null, rỗng, khoảng trắng, dấu, overflow, Unicode, dữ liệu cực dài. Không phá compatibility của parser.
5. **Chuyển đổi tại ranh giới phù hợp:** nếu public API hiện có contract ném exception, có thể giữ phương thức cũ và thêm `tryParse...` thay vì thay đổi im lặng mọi caller.
6. **Đảm bảo đường lỗi bất thường vẫn có cause:** khi dependency thật sự lỗi, không ép nó thành giá trị “không tìm thấy”.
7. **Tách kết quả dự kiến khỏi logging ERROR:** ghi metrics/rejection count và sample có giới hạn khi phù hợp.
8. **Đo sau thay đổi:** kiểm tra throughput/latency/allocation/GC trên dữ liệu đại diện và phiên bản JVM mục tiêu.
9. **Kiểm thử đường thành công và lỗi:** kiểm tra cả semantics lẫn khả năng quan sát lỗi hiếm.
10. **Chỉ giữ tối ưu khi đáng giá:** code đơn giản, đúng contract và dễ bảo trì quan trọng hơn một kết quả benchmark không đại diện.

## 19. Các bài kiểm thử nên có

| Trường hợp | Kỳ vọng |
|---|---|
| Dữ liệu hợp lệ | Parse chính xác, không bị bỏ qua |
| Chuỗi rỗng hoặc null | Trả trạng thái từ chối theo API, không dùng NPE ngoài ý muốn |
| Ký tự không thuộc grammar | Từ chối đúng, giữ vị trí/mã lỗi khi cần |
| Giá trị `Integer.MAX_VALUE` và hơn 1 | Chấp nhận giới hạn, từ chối overflow không vòng số |
| Số có dấu, leading zero, whitespace | Hành vi đúng grammar tài liệu hóa |
| Dữ liệu sai với tần suất cao | Không tạo exception/log ồ ạt trên nhánh expected |
| Lỗi I/O thực sự | Exception được giữ lại, không biến thành EOF |
| Không tìm thấy record | Kết quả expected, không che lỗi của dependency |
| Nhiều thread dùng chung cấu trúc | Kiểm tra và truy cập tuân thread-safety, tránh TOCTOU |
| Cancellation/interruption | Worker tôn trọng tín hiệu, không catch rộng rồi chạy mãi |
| Hiệu năng dưới tải tương tự production | Đo được throughput, latency và allocation với tỷ lệ lỗi xác định |
| Tương thích API | Caller cũ vẫn nhận kết quả/lỗi đúng hợp đồng sau refactor |

Đặc biệt, **kiểm thử correctness phải đi trước benchmark**. Một parser nhanh nhưng chấp nhận số bị overflow hoặc từ chối dữ liệu hợp lệ không phải là một tối ưu thành công.

## 20. Tổng kết

**Không dùng ngoại lệ cho nhánh điều khiển thường xuyên** nghĩa là không dùng `throw/catch` như một cách diễn đạt thay cho điều kiện bình thường mà thuật toán có thể biểu diễn trực tiếp. Với EOF, vòng lặp, tra cứu không có kết quả và dữ liệu người dùng bị từ chối thường xuyên, một điều kiện hoặc result type rõ nghĩa thường dễ đọc, dễ quan sát và có tiềm năng hiệu năng tốt hơn việc liên tục tạo exception.

Điều đó **không có nghĩa phải tránh exception bằng mọi giá**. Lỗi hạ tầng, vi phạm hợp đồng hoặc trạng thái bất thường vẫn cần đường exception đúng ngữ nghĩa, với `cause` và cleanup thích hợp. Đừng hy sinh grammar, invariant, thread-safety hoặc khả năng điều tra chỉ để giảm một số lần `throw` chưa được đo.

Công thức ra quyết định thực tế là: **xác định điều kiện expected → chọn kênh kết quả phù hợp → giữ exception cho failure thật → đo hot path bằng benchmark đáng tin → xác minh lại correctness và observability**.

### Tài liệu tham khảo

- [Java Language Specification 11 — Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html)
- [Java SE 17 — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html)
- [Java SE 17 — NumberFormatException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NumberFormatException.html)
- [Java SE 17 — Integer.parseInt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#parseInt(java.lang.String))
- [Java SE 17 — OptionalInt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/OptionalInt.html)
- [Java SE 17 — InputStream.read](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html#read())
- [Java SE 17 — BufferedReader.readLine](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html#readLine())
- [OpenJDK — Java Microbenchmark Harness (JMH)](https://openjdk.org/projects/code-tools/jmh/)
