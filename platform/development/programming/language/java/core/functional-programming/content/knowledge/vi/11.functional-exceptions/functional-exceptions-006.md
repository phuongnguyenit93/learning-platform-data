# Chọn dừng toàn bộ hay biểu diễn kết quả thành công, thất bại cho từng phần tử trong Java

## 1. Tại sao cùng một lỗi lại cần hai chính sách khác nhau?

Khi xử lý tập dữ liệu bằng vòng lặp, lambda hoặc Stream, một phần tử có thể không hợp lệ: dòng CSV sai định dạng, số tiền âm, mã khách hàng không tồn tại, bản ghi không đáp ứng quy tắc nghiệp vụ. Câu hỏi quan trọng không chỉ là **ném exception nào**, mà còn là **lỗi của một phần tử phải ảnh hưởng đến toàn bộ công việc ra sao**.

Hai lựa chọn thường gặp:

1. **Dừng toàn bộ khi có lỗi** (*fail-fast / abort the batch*): một phần tử không xử lý được làm phép xử lý kết thúc bằng exception. Bên gọi nhận lỗi thay vì danh sách kết quả thành công.
2. **Biểu diễn kết quả thành công hoặc thất bại cho từng phần tử** (*per-item result*): mỗi phần tử được chuyển thành một giá trị mô tả thành công hoặc lỗi; bộ xử lý tiếp tục với phần tử còn lại nếu lỗi đó có thể xử lý cục bộ.

Đây là **quyết định về hợp đồng xử lý**, không đơn thuần là khác biệt cú pháp `try/catch`. Cùng một bộ dữ liệu có thể cần chính sách khác nhau trong những hệ thống khác nhau:

| Bối cảnh | Chính sách thường hợp lý | Lý do |
| --- | --- | --- |
| Tính giá trị cho một giao dịch tài chính phải hợp lệ toàn bộ | Dừng hoặc từ chối toàn bộ | Không chấp nhận dữ liệu nửa đúng nếu nghiệp vụ yêu cầu tính nhất quán |
| Import hàng nghìn dòng CSV độc lập | Kết quả từng phần tử | Báo rõ các dòng lỗi và tiếp tục nhập những dòng hợp lệ |
| Cập nhật cấu hình hệ thống có ràng buộc toàn cục | Xác thực tất cả rồi từ chối toàn bộ nếu có lỗi | Cần biết đầy đủ lỗi nhưng không áp dụng cấu hình chưa hợp lệ |
| Xử lý thông báo độc lập theo người nhận | Kết quả từng phần tử, có retry phù hợp | Một địa chỉ lỗi không nên che trạng thái của địa chỉ khác |
| Thao tác ghi dữ liệu theo một transaction nguyên tử | Chính sách all-or-nothing và transaction thực sự | Exception một mình không tự rollback mọi thay đổi |

**Phân biệt quan trọng:** “dừng tại lỗi đầu tiên” và “xử lý hết để thu thập lỗi, rồi quyết định từ chối toàn lô” là hai quy trình khác nhau, dù cả hai có thể áp dụng chính sách cuối cùng là **không chấp nhận bất kỳ kết quả nào khi có lỗi**.

## 2. Cách nhìn ở cấp hàm

Giả sử có một phép phân tích chuỗi thành số nguyên dương:

~~~java
static int parsePositive(String raw) {
    if (raw == null || raw.isBlank()) {
        throw new IllegalArgumentException("Giá trị trống");
    }
    int value;
    try {
        value = Integer.parseInt(raw.trim());
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException("Không phải số nguyên: " + raw, ex);
    }
    if (value <= 0) {
        throw new IllegalArgumentException("Phải lớn hơn 0: " + raw);
    }
    return value;
}
~~~

Đoạn trên là **phương thức minh họa đặt trong một class**, không phải file độc lập; chương trình chạy đầy đủ ở phần 6. Với các đầu vào:

~~~text
["10", "bad", "25", "0", "7"]
~~~

phép biến đổi có kết quả mong đợi theo từng phần tử:

| Vị trí (1-based) | Đầu vào | Kết quả |
| --- | --- | --- |
| 1 | `"10"` | Thành công, giá trị 10 |
| 2 | `"bad"` | Thất bại, không phải số nguyên |
| 3 | `"25"` | Thành công, giá trị 25 |
| 4 | `"0"` | Thất bại, phải lớn hơn 0 |
| 5 | `"7"` | Thành công, giá trị 7 |

Một phép xử lý có thể mô tả bằng một trong hai hợp đồng ở mức tư duy:

~~~text
Toàn lô:
List<Input> -> List<Value> HOẶC exception (không trả List<Value>)

Từng phần tử:
Input -> Result<Value, Error>
List<Input> -> List<Result<Value, Error>>
~~~

Trong Java chuẩn, ký hiệu `Result<Value, Error>` ở đây là **mô hình khái niệm**, không phải một class generic `Result` sẵn có trong `java.util`. Ta có thể tự khai báo kiểu kết quả, dùng thư viện hỗ trợ hoặc thiết kế API theo domain.

## 3. Chính sách A: dừng toàn bộ khi một phần tử ném exception

Một pipeline Stream thường trông như sau:

~~~java
List<Integer> values = input.stream()
        .map(BatchResultDemo::parsePositive)
        .toList();
~~~

Đoạn này giả định trong class `BatchResultDemo` đã có `parsePositive` và `input` là `List<String>`. Khi `map` áp dụng hàm phân tích trên đầu vào không hợp lệ, exception có thể lan ra từ phép toán kết thúc `toList()`. Nếu không có xử lý, đường thực thi hiện tại bị kết thúc bằng exception đó.

Nếu bên gọi cần kiểm soát thông báo lỗi:

~~~java
try {
    List<Integer> all = input.stream()
            .map(BatchResultDemo::parsePositive)
            .toList();
    System.out.println("Toàn lô: " + all);
} catch (IllegalArgumentException ex) {
    System.out.println("Toàn lô: lỗi - " + ex.getMessage());
}
~~~

Với Stream tuần tự và bộ dữ liệu mẫu, lỗi `"bad"` xuất hiện khi phép xử lý đến vị trí thứ hai. Không có một `List<Integer>` thành công được gán cho biến `all`. Các phần tử phía sau không được thực hiện trong **pipeline tuần tự cụ thể này** sau khi exception lan ra.

### 3.1. Điểm mạnh

- Dễ hiểu nếu **tất cả đầu vào đều phải hợp lệ** trước khi có kết quả thành công.
- Giữ chữ ký thuận tiện như `List<T> -> List<R>` với exception dùng cho trường hợp không thể hoàn tất.
- Bên gọi có một nơi xử lý thất bại của thao tác, chẳng hạn ở ranh giới service/API.
- Giảm nhu cầu tạo đối tượng mô tả lỗi cho từng phần tử nếu chính sách chỉ cần biết có lỗi.

### 3.2. Những giới hạn cần biết

- **Exception lan ra không tự hoàn tác tác dụng phụ.** Nếu phần tử trước đó đã được ghi vào database, gửi email, cập nhật biến chia sẻ hoặc xuất ra thiết bị, việc `toList()` thất bại không bảo đảm rollback.
- **Không tự có danh sách tất cả lỗi.** Với cách fail-fast thông thường, lỗi tiếp theo chưa được kiểm tra sẽ không được thu thập.
- **Pipeline Stream là lazy.** `filter`, `map` và những thao tác trung gian phần lớn chưa chạy ngay khi khai báo. Exception phát sinh khi dữ liệu thực sự được đánh giá bởi terminal operation tương ứng. Không nên quy mọi lỗi về chính dòng gọi `map`.
- **Không phải mọi terminal operation đều duyệt toàn bộ nguồn.** Ví dụ `findFirst`, `anyMatch` có thể ngừng sớm theo điều kiện; việc có lỗi ở phần tử không được thăm không đồng nghĩa lỗi sẽ xuất hiện trong mọi pipeline.
- **Trong parallel stream**, nhiều tác vụ có thể chạy đồng thời. Không nên hứa rằng lỗi luôn đến từ phần tử đầu tiên theo thứ tự gặp; cũng không được dùng exception để suy luận mọi công việc khác chắc chắn đã dừng ngay tức thì.

### 3.3. All-or-nothing thật sự cần thiết kế thêm

Nếu nghiệp vụ yêu cầu **toàn bộ thành công hoặc không có thay đổi nào được cam kết**, hãy kết hợp chính sách lỗi với biện pháp đảm bảo tính nguyên tử:

1. **Giai đoạn chuẩn bị/kiểm tra:** phân tích, xác thực, chuyển đổi dữ liệu mà không tạo tác dụng phụ không thể hoàn tác.
2. **Giai đoạn cam kết:** thực hiện thay đổi trong transaction hỗ trợ rollback hoặc một cơ chế commit phù hợp.
3. **Nếu lỗi trong lúc commit:** áp dụng rollback/compensation dựa trên hợp đồng của hệ thống bên ngoài.

Một stream fail-fast không tương đương transaction. Với các API ngoài như gửi email, gọi thanh toán hoặc ghi file, khả năng đảo ngược có giới hạn và phải được thiết kế riêng.

## 4. Chính sách B: biểu diễn Success hoặc Failure cho từng phần tử

Khi các bản ghi có thể được xử lý **độc lập**, ta không muốn một đầu vào lỗi làm mất mọi thông tin về phần tử khác. Ý tưởng là chuyển lỗi có thể dự đoán thành **giá trị dữ liệu**, thay vì để exception thoát khỏi pipeline.

Java 17 có `sealed interface` và `record` giúp diễn đạt tập trạng thái đóng:

~~~java
sealed interface ParseResult permits Success, Failure {}

record Success(int index, String raw, int value)
        implements ParseResult {}

record Failure(int index, String raw, String reason)
        implements ParseResult {}
~~~

Đây là đoạn khai báo kiểu **nằm trong một class hoặc ở cấp top-level phù hợp**; ở phần 6 các kiểu được đặt lồng trong class để chương trình biên dịch độc lập.

- `Success` mang vị trí, dữ liệu gốc và giá trị phân tích thành công.
- `Failure` mang vị trí, dữ liệu gốc và lời giải thích tại sao phần tử không hợp lệ.
- `ParseResult` là kiểu chung của hai trường hợp. `sealed` giới hạn các implementation trực tiếp được phép, giúp mô hình domain rõ ràng hơn.
- `record` cho các thành phần dữ liệu ngắn gọn, có accessor và hỗ trợ so sánh theo giá trị. Record có **bất biến nông**; với các trường primitive và String trong ví dụ này, dữ liệu thực tế cũng ổn định.

Biến đổi một phần tử:

~~~java
static ParseResult parseOne(int index, String raw) {
    try {
        return new Success(index, raw, parsePositive(raw));
    } catch (IllegalArgumentException ex) {
        return new Failure(index, raw, ex.getMessage());
    }
}
~~~

Thay vì trả `int` hoặc ném lỗi đã dự đoán, phương thức này trả **một trong hai dạng kết quả**. Nó bắt `IllegalArgumentException` là loại lỗi validation được `parsePositive` chủ động sử dụng.

**Không bắt `Exception` hoặc `Throwable` bừa bãi trong mọi lambda.** Lỗi lập trình (ví dụ NullPointerException ngoài dự kiến), lỗi hạ tầng, vấn đề bảo mật, tình trạng ngắt luồng hoặc các `Error` nghiêm trọng không tự động được coi là “một dòng dữ liệu sai”. Hãy phân loại lỗi nào có thể tiếp tục và lỗi nào phải dừng toàn bộ hệ thống.

### 4.1. Ánh xạ toàn danh sách thành kết quả có nhãn

~~~java
List<ParseResult> results = IntStream.range(0, input.size())
        .mapToObj(i -> parseOne(i, input.get(i)))
        .toList();
~~~

Đoạn minh họa này cần import `java.util.List` và `java.util.stream.IntStream`, cùng class chứa `parseOne` và kiểu `ParseResult`.

- `IntStream.range(0, input.size())` tạo chỉ số từ 0 đến `size()-1`.
- `parseOne(i, input.get(i))` giữ lại **vị trí** để phân biệt cả khi hai dòng có cùng giá trị.
- `toList()` tạo danh sách kết quả (không cho phép chỉnh sửa cấu trúc danh sách trả về).
- Với ví dụ tuần tự, thứ tự kết quả tương ứng thứ tự các vị trí nguồn.

Lúc này các lỗi dữ liệu hợp lệ để báo cáo đã được **đóng gói** nên pipeline có thể hoàn tất. Điều này **không bảo đảm** không còn exception nào: ví dụ `input.get(i)` hoặc mã trong `parseOne` vẫn có thể lỗi theo cách chưa xử lý. Hợp đồng `Result` chỉ bền vững trong phạm vi các lỗi nó được thiết kế để biểu diễn.

### 4.2. Tính toán kết quả từ chỉ những phần tử thành công

Ví dụ:

~~~java
long successCount = results.stream()
        .filter(r -> r instanceof Success).count();
long failureCount = results.size() - successCount;

int sum = results.stream()
        .filter(r -> r instanceof Success)
        .mapToInt(r -> ((Success) r).value())
        .sum();
~~~

Trong chương trình mẫu, 10 + 25 + 7 = **42**, có 3 thành công và 2 thất bại. Cast ở biểu thức cuối là an toàn với kết quả của chính phép lọc `instanceof Success` ngay trước đó, khi danh sách không bị thay đổi bất ngờ trong pipeline.

Với code production, có thể thiết kế helper/accessor hoặc collector chuyên biệt để tránh lặp điều kiện và cast. Không nên cố biến mọi kiểm tra kết quả thành một chuỗi Stream khó đọc; vòng lặp phân loại kết quả cũng hoàn toàn hợp lý.

## 5. Còn một lựa chọn thứ ba: xử lý hết nhưng vẫn từ chối toàn lô

Chính sách **xử lý tất cả để tổng hợp lỗi, rồi quyết định chấp nhận hay từ chối** thường phù hợp với form nhiều trường, cấu hình hoặc file import cần kiểm tra đầy đủ trước khi commit.

Sau khi tạo `List<ParseResult> results`:

~~~java
boolean hasFailure = results.stream()
        .anyMatch(r -> r instanceof Failure);

if (hasFailure) {
    // Tổng hợp và trả về danh sách lỗi; không commit kết quả nào.
} else {
    // Trích toàn bộ Success và tiến hành commit theo chính sách nghiệp vụ.
}
~~~

Đây là **đoạn minh họa**. Nó khác fail-fast ở chỗ đã kiểm tra mọi phần tử và có đầy đủ thông tin để phản hồi. Nhưng nó cũng khác partial success: hệ thống **không chấp nhận phần tử thành công** nếu lô có bất kỳ thất bại nào.

Có thể tóm tắt bằng bảng:

| Quy trình | Có thể thấy những lỗi nào? | Có trả thành công từng phần tử? | Có tự rollback không? |
| --- | --- | --- | --- |
| Fail-fast và exception lan ra | Thường là lỗi đầu tiên làm pipeline thất bại | Không có kết quả toàn lô thành công | Không |
| Mỗi phần tử trả Result | Các lỗi dự đoán được ở từng phần tử đã xử lý | Có thể có, theo chính sách | Không |
| Thu thập hết Result rồi từ chối all-or-nothing | Các lỗi dự đoán được ở mọi phần tử | Có thể ghi nhận nội bộ, nhưng không commit | Không; vẫn cần transaction/commit design |

**Đừng nhầm:** thu thập mọi kết quả là một **chiến lược chẩn đoán**; cho phép kết quả từng phần tử được ghi vào hệ thống là một **quyết định nghiệp vụ riêng**.

## 6. Chương trình Java 17 hoàn chỉnh và stdout đã kiểm chứng

Tạo file **BatchResultDemo.java** như dưới đây. Ví dụ chạy cả hai chính sách trên cùng dữ liệu để người học thấy sự khác biệt một cách trực tiếp.

~~~java
import java.util.List;
import java.util.stream.IntStream;

public class BatchResultDemo {
    sealed interface ParseResult permits Success, Failure {}
    record Success(int index, String raw, int value) implements ParseResult {}
    record Failure(int index, String raw, String reason) implements ParseResult {}

    static int parsePositive(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("Giá trị trống");
        }
        int value;
        try {
            value = Integer.parseInt(raw.trim());
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("Không phải số nguyên: " + raw, ex);
        }
        if (value <= 0) {
            throw new IllegalArgumentException("Phải lớn hơn 0: " + raw);
        }
        return value;
    }

    static ParseResult parseOne(int index, String raw) {
        try {
            return new Success(index, raw, parsePositive(raw));
        } catch (IllegalArgumentException ex) {
            return new Failure(index, raw, ex.getMessage());
        }
    }

    public static void main(String[] args) {
        List<String> input = List.of("10", "bad", "25", "0", "7");

        try {
            List<Integer> all = input.stream()
                    .map(BatchResultDemo::parsePositive)
                    .toList();
            System.out.println("Toàn lô: " + all);
        } catch (IllegalArgumentException ex) {
            System.out.println("Toàn lô: lỗi - " + ex.getMessage());
        }

        List<ParseResult> results = IntStream.range(0, input.size())
                .mapToObj(i -> parseOne(i, input.get(i)))
                .toList();

        System.out.println("Từng phần tử:");
        for (ParseResult result : results) {
            if (result instanceof Success s) {
                System.out.println("OK #" + (s.index() + 1)
                        + " " + s.raw() + " -> " + s.value());
            } else if (result instanceof Failure f) {
                System.out.println("FAIL #" + (f.index() + 1)
                        + " " + f.raw() + " -> " + f.reason());
            }
        }

        long successCount = results.stream()
                .filter(r -> r instanceof Success).count();
        long failureCount = results.size() - successCount;
        int sum = results.stream()
                .filter(r -> r instanceof Success)
                .mapToInt(r -> ((Success) r).value())
                .sum();

        System.out.println("Tổng kết: " + successCount
                + " thành công, " + failureCount
                + " thất bại, tổng=" + sum);
    }
}
~~~

Chạy từ thư mục chứa tệp bằng JDK 17 trở lên:

~~~bash
javac --release 17 BatchResultDemo.java
java BatchResultDemo
~~~

**Stdout chính xác:**

~~~text
Toàn lô: lỗi - Không phải số nguyên: bad
Từng phần tử:
OK #1 10 -> 10
FAIL #2 bad -> Không phải số nguyên: bad
OK #3 25 -> 25
FAIL #4 0 -> Phải lớn hơn 0: 0
OK #5 7 -> 7
Tổng kết: 3 thành công, 2 thất bại, tổng=42
~~~

Chương trình trên đã được biên dịch bằng `javac --release 17` và chạy độc lập; kết quả phù hợp với phép tính trong phần 2.

**Đọc output theo hợp đồng:**

- Trong nhánh **toàn lô**, pipeline ném `IllegalArgumentException` tại `"bad"`; thay vì trả danh sách kết quả, bên gọi bắt exception và xuất một dòng lỗi.
- Trong nhánh **từng phần tử**, cùng lỗi đó được chuyển thành `Failure(index=1,...)`. Phần tử vị trí 3, 4 và 5 vẫn được xử lý.
- `"0"` là số nguyên parse được nhưng **không đáp ứng điều kiện > 0**, vì vậy nhận `Failure` nghiệp vụ khác với `"bad"`.
- Kết quả được đánh chỉ số **hiển thị từ 1**, còn nội bộ dùng chỉ số từ 0.
- Tổng 42 chỉ tính `Success`; không coi lỗi bằng 0 hoặc bỏ qua âm thầm khi báo cáo số lượng.

**Ý nghĩa của `IllegalArgumentException` trong ví dụ:** đây là lỗi validation được chủ động sử dụng làm hợp đồng của `parsePositive`. Trong code production, có thể định nghĩa exception chuyên ngành hoặc trả trực tiếp cấu trúc lỗi để tránh bắt nhầm `IllegalArgumentException` phát sinh do bug trong các logic khác. Việc dùng kiểu exception này trong bài nhằm làm rõ hai chiến lược, không áp đặt một ngoại lệ chung cho mọi hệ thống.

## 7. Chọn kiểu dữ liệu của Success/Failure như thế nào?

### 7.1. Lưu đầy đủ ngữ cảnh để người dùng sửa lỗi

Một đối tượng thất bại hữu ích thường chứa:

- **Vị trí**: chỉ số, số dòng hoặc ID bản ghi, để xác định phần tử nguồn.
- **Mã lỗi ổn định**: chẳng hạn `INVALID_NUMBER`, `NON_POSITIVE`, `UNKNOWN_CUSTOMER`, giúp UI hoặc hệ thống khác xử lý tự động.
- **Thông điệp**: giải thích đủ rõ, có thể bản địa hóa ở tầng hiển thị.
- **Giá trị đầu vào hoặc tham chiếu nguồn** khi an toàn và cần thiết.

Đoạn minh họa khái niệm (không phải file độc lập):

~~~java
record ValidationError(
        int index,
        String code,
        String message) {}
~~~

Một lỗi có mã ổn định thường tốt hơn việc parsing văn bản từ `Exception.getMessage()`. Không dùng message của exception như giao thức duy nhất giữa các dịch vụ, vì nội dung/locale có thể thay đổi.

### 7.2. Có cần giữ nguyên Throwable trong Failure không?

Không phải lúc nào cũng cần. Giữ nguyên `Throwable` có thể giúp log/diagnostics tại boundary nội bộ, nhưng cũng kéo theo stack trace, dữ liệu nhạy cảm và phụ thuộc công nghệ. Trong payload trả cho client, ưu tiên **mã lỗi + vị trí + thông điệp an toàn**; nếu cần lưu nguyên nhân sâu hơn, sử dụng logging/correlation ID ở tầng phù hợp.

Đặc biệt không đưa trực tiếp input nhạy cảm như mật khẩu, token hoặc dữ liệu cá nhân vào message công khai. Ví dụ dùng chuỗi số đơn giản chỉ nhằm minh họa.

### 7.3. Generic Result<T,E> hay kiểu nghiệp vụ cụ thể?

Trong một dự án lớn, có thể định nghĩa một cấu trúc:

~~~java
sealed interface Result<T, E> permits Ok, Err {}

record Ok<T, E>(T value) implements Result<T, E> {}
record Err<T, E>(E error) implements Result<T, E> {}
~~~

Đây là **đoạn minh họa ở cấp kiểu** (không có `public`, không bao gồm phương thức chạy). Java 17 có thể dùng generic `sealed interface` và record như vậy nếu đặt trong đơn vị biên dịch và phạm vi cho phép. Ưu điểm: có thể tái sử dụng logic thành công/thất bại cho nhiều kiểu dữ liệu và nhiều loại lỗi.

Nhưng một kiểu chung không tự động đảm bảo mọi nhánh đã được xử lý hoặc mọi giá trị đều non-null. API cần quy ước rõ về null, generic variance, kiểu exception và bất biến đối tượng. Với domain nhỏ, `ParseResult` và hai record cụ thể có thể dễ đọc hơn một abstraction tổng quát.

Thư viện như **Vavr** có kiểu `Either<L,R>` và `Try<T>` để biểu diễn các ý tưởng gần nhau; đó là **thư viện ngoài JDK**, không mặc định có trong Java chuẩn. Chọn thư viện khi phù hợp với hệ thống và quy tắc team, không cần thêm dependency chỉ cho một ví dụ nhỏ.

## 8. Checked exception trong lambda và Stream

Các functional interface thường dùng trong Stream, chẳng hạn `Function<T,R>` và `Predicate<T>`, không khai báo checked exception tổng quát trong phương thức SAM. Vì vậy đoạn sau **cố ý không biên dịch** nếu một phương thức `load(...)` khai báo `throws IOException`:

~~~java
// Giả định: static String load(Path path) throws IOException { ... }
//
// List<String> lines = paths.stream()
//         .map(path -> load(path)) // lỗi checked exception chưa được xử lý
//         .toList();
~~~

Các kiểu như `Path`, `IOException` ở đây chỉ là mô tả ngữ cảnh. Có hai hướng có chủ đích:

1. **Toàn lô:** thực hiện phép đọc trong lớp service/helper có hợp đồng ngoại lệ rõ, và để caller/hệ thống quyết định dừng.
2. **Từng phần tử:** bắt **đúng loại checked exception có thể xử lý cục bộ** bên trong hàm ánh xạ và trả `Failure` mang mã lỗi thích hợp.

Ví dụ minh họa theo hướng Result:

~~~java
// map(path -> {
//     try {
//         return new Success<>(read(path));
//     } catch (IOException ex) {
//         return new Failure<>(safeError(ex));
//     }
// })
~~~

Đây là **pseudocode Java dùng tên kiểu/hàm giả định** để minh họa ý tưởng, không phải chương trình biên dịch độc lập. Nếu triển khai thật, hãy dùng các kiểu Result/Success/Failure đã định nghĩa và đúng chữ ký. Không bắt mọi `Exception` chỉ để bảo đảm pipeline “luôn chạy hết”.

### 8.1. Cancellation, InterruptedException và lỗi không thể tiếp tục

Nếu xử lý có thao tác chặn và gặp `InterruptedException`, đó thường là **tín hiệu hủy** cần được tôn trọng, không phải dữ liệu sai của một phần tử. Khi chọn bắt để chuyển tiếp một cách phù hợp, nhiều API yêu cầu khôi phục interrupt flag bằng `Thread.currentThread().interrupt()` trước khi thoát hoặc trả trạng thái hủy. Quyết định phụ thuộc vào hợp đồng API, nhưng không nên nuốt hẳn interrupt rồi tiếp tục xử lý im lặng.

Cũng không nên chuyển `OutOfMemoryError` và những lỗi VM nghiêm trọng thành `Failure` thông thường. “Tiếp tục xử lý” chỉ hợp lý với **lỗi đã phân loại là có thể tiếp tục**, không phải mọi thứ có thể bị ném trong Java.

## 9. Những quyết định bổ sung thường bị bỏ quên

### 9.1. Thứ tự và tính xác định

Ví dụ phần 6 dùng `List.of`, `IntStream.range` và pipeline tuần tự; kết quả giữ thứ tự đầu vào. Nếu chuyển sang `parallel()`, cần xem xét lại side effects, thứ tự và cách thu thập lỗi. Không dựa vào exception đầu tiên được quan sát trong môi trường song song để khẳng định đó là dòng lỗi sớm nhất theo vị trí.

Nếu phải trả báo cáo theo thứ tự nguồn, giữ `index` trong mỗi kết quả rồi sắp xếp/thu thập theo index nếu kiến trúc xử lý không bảo đảm thứ tự gặp.

### 9.2. Tiếp tục xử lý hay thử lại?

`Failure` không nhất thiết là trạng thái cuối cùng. Lỗi validation thường cần người dùng sửa input; lỗi mạng tạm thời có thể retry với backoff và idempotency key, nhưng retry không được áp dụng vô hạn hoặc gây gửi/ghi lặp. Nếu dùng per-item result, trạng thái “đang chờ/thử lại” có thể cần một kiểu riêng hoặc workflow riêng, thay vì coi mọi lỗi là thất bại vĩnh viễn.

### 9.3. Giới hạn số lỗi và bộ nhớ

Thu thập toàn bộ `List<Result>` giúp phản hồi chi tiết nhưng có chi phí bộ nhớ tỷ lệ với số phần tử. Với batch rất lớn, có thể xử lý theo từng chunk, lưu kết quả vào hệ thống theo lô, hoặc đặt ngưỡng số lỗi được báo cáo. Việc ngừng sau N lỗi là một **chính sách riêng**; không còn là “đã kiểm tra mọi phần tử”.

### 9.4. Giao thức trả về từ API

Nếu HTTP API chỉ trả một status cho toàn request, dùng các trạng thái HTTP phù hợp với contract; còn báo cáo từng phần tử cần một body mô tả rõ từng outcome, ID/vị trí và tổng hợp. Không chọn một HTTP status duy nhất rồi suy ra ngầm mọi bản ghi đều thành công. Với việc cho phép partial success, tài liệu API phải nói rõ “bao nhiêu đã cam kết, bao nhiêu thất bại, có retry hay không”.

### 9.5. Tránh để side effects nằm trong map/filter

Trong pipeline mô hình hóa dữ liệu, nên tách **chuyển đổi/kiểm tra** khỏi **ghi ra hệ thống ngoài**. Dùng `map` để tạo kết quả rồi tiến hành commit theo chính sách. Việc ghi database hoặc gửi email ngay trong `map` khiến fail-fast khó rollback và retry dễ gây lặp. Đặc biệt không dùng `parallelStream()` với biến gom lỗi mutable chia sẻ không đồng bộ một cách tùy tiện.

## 10. So sánh với Optional và việc nuốt lỗi

Một cách “tiếp tục” trông có vẻ ngắn:

~~~java
// Không khuyến nghị nếu cần chẩn đoán lỗi:
// List<Integer> values = input.stream()
//     .map(x -> {
//         try { return parsePositive(x); }
//         catch (IllegalArgumentException ex) { return null; }
//     })
//     .filter(java.util.Objects::nonNull)
//     .toList();
~~~

Đây là **đoạn minh họa đặt trong class có parsePositive**; mã đã comment vì nó thể hiện chiến lược làm mất thông tin. Kết quả chỉ còn các số hợp lệ, **không biết có bao nhiêu bản ghi lỗi, lý do và vị trí** nếu không có kênh báo cáo riêng.

`Optional<Integer>` có thể biểu diễn **có hoặc không có giá trị** nhưng mặc định không chứa mã lỗi/vị trí/nguyên nhân. Nếu chỉ cần loại bỏ phần tử không hợp lệ và điều đó được cho phép, `Optional` hoặc `filter` có thể đủ. Nếu cần phản hồi lỗi chi tiết, `Result` hoặc kiểu nghiệp vụ tương đương thích hợp hơn.

Tránh cố tình gán lỗi bằng 0, chuỗi rỗng hoặc giá trị giả nếu chúng có thể là dữ liệu hợp lệ. Điều này làm sai thống kê và che giấu bất thường.

## 11. Chọn chính sách bằng một checklist

Trước khi thiết kế hàm xử lý hàng loạt, hãy trả lời:

1. **Đầu vào có độc lập không?** Một phần tử thất bại có làm các phần tử khác trở nên vô nghĩa hoặc không nhất quán không?
2. **Nghiệp vụ có cho phép partial success không?** Nếu không, cần fail-fast hay kiểm tra hết rồi từ chối toàn lô?
3. **Người dùng cần xem mọi lỗi hay chỉ một lỗi đủ để sửa?** Với upload form/batch, báo hết lỗi thường cải thiện trải nghiệm.
4. **Lỗi nào là dữ liệu sai, lỗi nào là hạ tầng/hủy?** Chỉ lỗi có thể phục hồi cục bộ mới nên được chuyển thành Failure và tiếp tục.
5. **Đã có tác dụng phụ chưa?** Nếu có, exception không bảo đảm rollback; cần transaction, idempotency hoặc compensation.
6. **Có yêu cầu thứ tự, ID và log đối chiếu không?** Nên giữ index/ID nguồn trong mọi kết quả.
7. **Số lượng phần tử và lỗi có lớn không?** Có cần chunking, streaming kết quả hoặc giới hạn dung lượng?
8. **Hợp đồng API có rõ?** Có thể phân biệt “đã xử lý”, “hợp lệ”, “đã commit”, “sẽ retry” hay không?

Một nguyên tắc thực dụng:

- **Cần toàn bộ hợp lệ và không phải báo tất cả lỗi:** xét fail-fast với hợp đồng exception rõ, nhưng bảo đảm transaction nếu có yêu cầu all-or-nothing.
- **Cần phản hồi tất cả lỗi nhưng không cho phép áp dụng một phần:** thu thập Result của toàn bộ đầu vào, rồi chỉ commit nếu không có Failure.
- **Mỗi phần tử độc lập và cho phép kết quả một phần:** trả Result cho từng phần tử, báo cáo tổng hợp, và quản lý retry/commit đúng hợp đồng.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Với danh sách `["10","bad","25"]` và `input.stream().map(BatchResultDemo::parsePositive).toList()`, kết quả là gì?

**Trả lời:** trên pipeline tuần tự dùng hàm trong bài, `"bad"` làm ném `IllegalArgumentException`; không có List<Integer> thành công được trả cho bên gọi. Nếu có tác dụng phụ đã thực hiện trước lỗi, chúng không tự bị rollback.

**Câu 2.** Vì sao kiểu Result cho từng phần tử tốt hơn việc bắt exception và trả `null`?

**Trả lời:** giữ được ngữ cảnh thất bại (vị trí, mã lỗi, lý do) và có thể phân biệt rõ với thành công; cách trả null rồi filter sẽ mất thông tin nếu không bổ sung kênh khác.

**Câu 3.** Thu thập toàn bộ Result có đồng nghĩa cho phép partial success không?

**Không.** Hệ thống có thể tổng hợp tất cả lỗi để phản hồi rồi từ chối toàn lô, không commit giá trị thành công nào.

**Câu 4.** Nếu xử lý file CSV cần hiển thị mọi dòng sai, nên ưu tiên gì?

**Trả lời:** per-row result hoặc cơ chế validation aggregate có vị trí, thông điệp và mã lỗi; sau đó quyết định có nhập bản ghi đúng hay từ chối toàn lô theo nghiệp vụ.

**Câu 5.** Vì sao không nên bắt `Throwable` trong `map` để mọi phần tử đều có Failure?

**Trả lời:** vì `Throwable` bao gồm các lỗi nghiêm trọng và tín hiệu cần để cấp trên xử lý. Tiếp tục không phân loại có thể gây dữ liệu sai hoặc che giấu lỗi hệ thống.

**Câu 6.** Có thể dùng Result để bảo đảm rollback database không?

**Không.** Result là mô hình thông báo outcome. Cần transaction hoặc cơ chế commit/rollback riêng để bảo đảm tính nguyên tử.

**Câu 7.** Parallel stream có bảo đảm exception quan sát được luôn thuộc dòng lỗi đầu tiên không?

**Không.** Thứ tự và thời điểm xử lý có thể khác nhau; cần chiến lược rõ ràng nếu phải xác định lỗi sớm nhất theo thứ tự nguồn.

**Câu 8.** Khi nào chỉ dùng `Optional<T>` là hợp lý?

**Trả lời:** khi nghiệp vụ chỉ cần biết có/không có giá trị và không cần phân biệt nguyên nhân, số dòng hay cách sửa lỗi.

## 13. Tài liệu tham khảo

- [Java SE 17 — Stream API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html).
- [Java SE 17 — Function<T,R>](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html).
- [Java SE 17 — Optional<T>](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html).
- [Java Language Specification 17, §14.20 — try statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20).
- [Java Language Specification 17, §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10).
- [Java Language Specification 17, §9.1.4 — Sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4).

**Ghi nhớ:** Chọn **fail-fast** khi lỗi làm toàn bộ phép xử lý không còn có kết quả hợp lệ; chọn **Success/Failure cho từng phần tử** khi các lỗi dự đoán được cần được báo cáo riêng và những phần tử khác có thể tiếp tục xử lý. Cần **biết mọi lỗi nhưng không chấp nhận partial success** thì thu thập Result trước rồi quyết định ở ranh giới commit. Không đánh đồng exception, transaction, rollback và lỗi có thể tiếp tục; chính sách nghiệp vụ phải được diễn đạt tường minh trong API.
