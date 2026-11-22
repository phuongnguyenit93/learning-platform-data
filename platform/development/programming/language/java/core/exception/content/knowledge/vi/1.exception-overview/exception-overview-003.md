# Vì sao dùng ngoại lệ thay cho mã lỗi hoặc giá trị đặc biệt trong Java?

Trong một lời gọi phương thức, ta cần phân biệt **kết quả nghiệp vụ hợp lệ** với **việc không thể thực hiện thao tác như đã cam kết**. Nếu biểu diễn mọi thất bại bằng một số như `-1`, một chuỗi như `"ERROR"` hoặc `null`, người gọi có thể nhầm tín hiệu lỗi với dữ liệu hợp lệ. Ngoại lệ (exception) cho Java một **luồng xử lý lỗi riêng**: phương thức trả về giá trị khi thành công; khi gặp sự cố, nó `throw` ngoại lệ để người có trách nhiệm xử lý ở tầng phù hợp.

Ngoại lệ không phải lựa chọn đúng cho *mọi* trường hợp không có kết quả. Điểm quyết định là **đó có phải một kết quả bình thường theo hợp đồng của phương thức hay là một tình huống thất bại cần được xử lý?**

## 1. Vấn đề của mã lỗi và giá trị đặc biệt

Giả sử phương thức chuyển chuỗi thành nhiệt độ nguyên. Nhiệt độ `-1` hoàn toàn hợp lệ. Nếu trả về `-1` khi chuỗi không chuyển đổi được, hai tình huống trở nên không thể phân biệt:

- `parse("-1")` thành công với giá trị `-1`.
- `parse("abc")` thất bại nhưng cũng trả về `-1`.

Một giá trị đặc biệt (sentinel value) chỉ an toàn khi **được hợp đồng loại trừ khỏi toàn bộ miền giá trị hợp lệ**, và mọi người gọi đều biết phải kiểm tra nó. Các cách khác cũng có giới hạn:

- `null`: có thể là “không có dữ liệu” hoặc “đã lỗi”; bỏ kiểm tra còn có thể gây `NullPointerException` ở vị trí rất xa nguồn gốc.
- `false`: phù hợp với câu hỏi có/không đơn giản, nhưng không nói được *vì sao* thao tác thất bại.
- Mã trạng thái `0`/`1`/`2`: buộc người gọi kiểm tra mã và giữ chỗ khác để lấy kết quả hoặc thông tin lỗi; nếu bỏ quên kiểm tra, lỗi có thể bị che giấu.
- Giá trị `"ERROR"`: có thể trùng dữ liệu hợp lệ, phụ thuộc quy ước chuỗi và khó kiểm tra bằng kiểu dữ liệu.

**Không phải mã lỗi luôn sai.** Một kiểu kết quả tường minh chứa cả trạng thái và dữ liệu (ví dụ `Result<T, E>` tự định nghĩa), hay mã trạng thái ở giao thức HTTP, vẫn rất hữu ích. Vấn đề chủ yếu nằm ở **mã lỗi hoặc sentinel thiếu ngữ nghĩa, dễ bị bỏ qua hoặc trùng dữ liệu hợp lệ**.

## 2. Ngoại lệ giải quyết những gì?

### Tách luồng thành công khỏi luồng thất bại

Chữ ký `int parse(String text)` có nghĩa khi thành công sẽ thu được một `int`. Nếu nội dung không hợp lệ, phương thức có thể `throw NumberFormatException`; nó không cần “chiếm dụng” một giá trị `int` làm dấu hiệu lỗi. Người gọi dùng `try`/`catch` khi có cách phục hồi hoặc chuyển lỗi thành thông báo phù hợp.

### Giữ thông tin để chẩn đoán

Một đối tượng ngoại lệ có **kiểu cụ thể**, **thông điệp**, **stack trace** và có thể có **nguyên nhân gốc** (`cause`). Chẳng hạn, có thể phân biệt `NumberFormatException` (chuỗi không phải số), `IOException` (đọc/ghi gặp sự cố) và `IllegalArgumentException` (đối số vi phạm điều kiện).

Khi chuyển lỗi giữa các tầng, có thể giữ nguyên nguyên nhân: `throw new IllegalStateException("Không tải được cấu hình", cause);`. Nhờ vậy, lớp ngoài hiển thị thông báo ngắn, còn nhật ký chẩn đoán vẫn giữ được lỗi ban đầu. Một mã `-1` đơn độc không chứa thông tin tương đương.

### Truyền lỗi tới nơi chịu trách nhiệm xử lý

Nếu hàm A gọi B, B gọi C, và C không thể hoàn thành, ngoại lệ có thể lan từ C qua B tới A mà B không phải tự kiểm tra rồi trả tiếp một mã lỗi sau mọi lời gọi. Khi được `throw`, **các câu lệnh còn lại trên đường thực thi bình thường bị bỏ qua** cho đến khi tìm thấy `catch` phù hợp; các khối `finally` và việc đóng tài nguyên theo `try-with-resources` vẫn được xử lý theo quy tắc ngôn ngữ.

Điều này giúp lớp thư viện tập trung phát hiện lỗi, còn lớp giao diện/API quyết định phản hồi người dùng. Tuy nhiên, việc ném ngoại lệ **không tự động hoàn tác** mọi thay đổi đã thực hiện trước đó; rollback giao dịch hoặc bù trừ thao tác vẫn cần cơ chế riêng.

### Buộc một số hợp đồng lỗi được thể hiện rõ

Java phân biệt:

- **Checked exception** như `IOException`: lời gọi có thể buộc người viết mã phải bắt bằng `catch` hoặc khai báo `throws`. Đây là quy tắc kiểm tra của trình biên dịch, không phải bảo đảm lỗi đã được xử lý đúng.
- **Unchecked exception** như `NumberFormatException` và `IllegalArgumentException` (kế thừa `RuntimeException`): không bắt buộc khai báo hoặc bắt tại thời điểm biên dịch; phù hợp cho nhiều tình huống vi phạm tiền điều kiện hay dữ liệu không đúng định dạng.
- **`Error`** như `OutOfMemoryError`: nói chung biểu thị lỗi nghiêm trọng của môi trường/runtime; ứng dụng không nên coi đây là ngoại lệ nghiệp vụ thông thường để bắt rồi tiếp tục.

## 3. Ví dụ Java 17+: cùng `-1` nhưng hai ý nghĩa

Lưu toàn bộ ví dụ sau thành tệp **`ExceptionVsErrorCodeDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.OptionalInt;

public class ExceptionVsErrorCodeDemo {
    // Cách cũ: -1 vừa là nhiệt độ hợp lệ vừa là tín hiệu lỗi.
    static int parseLegacy(String text) {
        try {
            return Integer.parseInt(text);
        } catch (NumberFormatException ex) {
            return -1;
        }
    }

    // Cách dùng ngoại lệ: khi thành công luôn trả về số đã đọc.
    // Nếu sai định dạng, NumberFormatException lan tới người gọi.
    static int parseStrict(String text) {
        return Integer.parseInt(text);
    }

    // Không tìm thấy là tình huống bình thường, nên dùng OptionalInt.
    static OptionalInt firstEvenAbove(int[] values, int threshold) {
        return Arrays.stream(values)
                .filter(value -> value > threshold && value % 2 == 0)
                .findFirst();
    }

    // I/O có thể thất bại: khai báo checked exception.
    static String readConfiguration(Path file) throws IOException {
        return Files.readString(file);
    }

    public static void main(String[] args) {
        System.out.println("Cũ, hợp lệ -1: " + parseLegacy("-1"));
        System.out.println("Cũ, nhập sai: " + parseLegacy("abc"));

        System.out.println("Ngoại lệ, hợp lệ -1: " + parseStrict("-1"));
        try {
            parseStrict("abc");
        } catch (NumberFormatException ex) {
            System.out.println(
                    "Ngoại lệ, nhập sai: " + ex.getClass().getSimpleName());
        }

        OptionalInt found = firstEvenAbove(new int[] {1, 3, 4}, 4);
        System.out.println("Không thấy số chẵn > 4: " + found.isEmpty());
    }
}
```

Biên dịch và chạy (JDK 17 trở lên):

```bash
javac -encoding UTF-8 ExceptionVsErrorCodeDemo.java
java ExceptionVsErrorCodeDemo
```

Kết quả chuẩn:

```text
Cũ, hợp lệ -1: -1
Cũ, nhập sai: -1
Ngoại lệ, hợp lệ -1: -1
Ngoại lệ, nhập sai: NumberFormatException
Không thấy số chẵn > 4: true
```

**Phân tích:**

1. Hai dòng “Cũ” trả về cùng `-1` nên bên gọi không biết thao tác thành công hay thất bại. Không thể sửa nhược điểm này chỉ bằng cách kiểm tra `result == -1`, vì `-1` là dữ liệu hợp lệ.
2. Với `parseStrict`, `-1` vẫn được giữ như dữ liệu; chuỗi `"abc"` sinh `NumberFormatException` và đi vào nhánh `catch`. Ta chỉ in tên kiểu ngoại lệ nên kết quả không phụ thuộc nội dung stack trace.
3. Tìm số chẵn lớn hơn 4 trong mảng là một phép tìm kiếm **có thể không có kết quả**. `OptionalInt.empty()` biểu diễn rõ điều đó mà không cần ném ngoại lệ. `isEmpty()` trả về `true`.
4. `readConfiguration` minh họa hợp đồng **checked exception** của đọc tệp. Nó không được gọi trong `main`, nên ví dụ không phụ thuộc tệp có sẵn hay không. Nếu người gọi sử dụng phương thức này, người gọi phải xử lý hoặc khai báo `IOException`.

## 4. So sánh các lựa chọn thiết kế API

| Cách biểu diễn | Nên dùng khi | Điểm cần cân nhắc |
| --- | --- | --- |
| Giá trị bình thường (`int`, `String`, đối tượng) | Thành công có kết quả hợp lệ | Không dùng một giá trị hợp lệ làm mã lỗi |
| `boolean` hoặc enum trạng thái | Kết quả có/không là điều thường xuyên và đủ thông tin | Phải quy định rõ ý nghĩa trạng thái |
| `Optional<T>` / `OptionalInt` | “Không tìm thấy” là kết quả dự kiến | Không dùng để che giấu lỗi I/O, lỗi hệ thống; bản thân `Optional` không mang nguyên nhân lỗi |
| Kết quả tường minh như `Result<T, E>` | Thất bại dự kiến có nhiều kiểu, bên gọi cần xử lý như dữ liệu | Java 17 không có kiểu `Result<T, E>` chuẩn trong thư viện lõi; phải tự định nghĩa hoặc dùng thư viện phù hợp |
| Ngoại lệ cụ thể | Không đáp ứng được hợp đồng thao tác, vi phạm tiền điều kiện, hoặc có sự cố cần chuyển lên tầng xử lý | Phải chọn đúng loại, tài liệu hóa và xử lý tại đúng ranh giới |
| Mã lỗi của giao thức/API ngoài | HTTP, quy ước C/native, thiết bị, hệ thống kế thừa | Nên chuyển sang kiểu Java tường minh tại lớp tích hợp khi thích hợp |

Ví dụ định hướng: tìm sản phẩm theo bộ lọc có thể trả về danh sách rỗng; tra cứu một bản ghi không tồn tại có thể trả về `Optional.empty()` nếu hợp đồng cho phép vắng mặt; nhưng không đọc được cơ sở dữ liệu vì mất kết nối là **sự cố**, không nên giả làm “không có bản ghi”.

Tương tự, dữ liệu biểu mẫu sai định dạng có thể được hệ thống xác thực thu thập thành nhiều lỗi trường để người dùng sửa cùng lúc. Một ngoại lệ vẫn có thể được sử dụng tại ranh giới chuyển đổi dữ liệu, nhưng không nên ném rồi bắt ngoại lệ cho từng nhánh kiểm tra thông thường nếu kết quả xác thực tường minh dễ hiểu hơn.

## 5. Cách sử dụng ngoại lệ có trách nhiệm

### Ném lỗi tại nơi phát hiện, xử lý tại nơi biết phải làm gì

Một phương thức nên kiểm tra tiền điều kiện và ném loại ngoại lệ thể hiện chính xác sai phạm, ví dụ `IllegalArgumentException` cho đối số âm trong thao tác yêu cầu số dương. Lớp thấp thường **không biết** cách hiển thị thông báo cho người dùng; lớp ngoài có thể chuyển ngoại lệ thành thông báo giao diện, phản hồi HTTP, retry có kiểm soát hoặc cảnh báo vận hành.

Không cần `catch` ở mọi cấp. Chỉ bắt khi có khả năng **phục hồi, bổ sung ngữ cảnh, chuyển đổi có chủ đích, hoặc kết thúc thao tác một cách an toàn**.

### Giữ nguyên nguyên nhân gốc khi chuyển kiểu ngoại lệ

Đoạn sau là **một phương thức minh họa**, cần đặt trong lớp Java có các import `java.io.IOException`, `java.nio.file.Files` và `java.nio.file.Path`; không phải chương trình độc lập:

```java
static String loadRequiredConfig(Path file) {
    try {
        return Files.readString(file);
    } catch (IOException cause) {
        throw new IllegalStateException(
                "Không thể tải cấu hình bắt buộc: " + file, cause);
    }
}
```

Nếu hợp đồng của lớp đang thiết kế cho phép người gọi tự phục hồi lỗi I/O, giữ `throws IOException` có thể hợp lý hơn chuyển sang `IllegalStateException`. Chỉ chuyển kiểu khi tầng hiện tại có đủ ngữ cảnh để quyết định.

### Đóng tài nguyên ngay cả khi có ngoại lệ

Khi thao tác trên luồng/tệp/kết nối, ưu tiên `try-with-resources` cho đối tượng thực thi `AutoCloseable`:

```java
static String readFirstLine(Path file) throws IOException {
    try (var reader = Files.newBufferedReader(file)) {
        return reader.readLine();
    }
}
```

Đây là đoạn phương thức minh họa, cần import `java.io.IOException`, `java.nio.file.Files` và `java.nio.file.Path`. Reader được đóng khi rời khối, kể cả khi đọc gặp ngoại lệ. Giá trị `null` của `readLine()` trong trường hợp tệp rỗng là một **kết quả đã được hợp đồng API quy định**, khác với `IOException` do đọc lỗi. Khi cả thao tác chính và thao tác đóng đều ném ngoại lệ, Java có thể lưu ngoại lệ lúc đóng dưới dạng **suppressed exception**.

### Tài liệu hóa và phân loại nhất quán

Mô tả rõ ngoại lệ có thể gặp bằng JavaDoc (`@throws`), dùng thông điệp chứa bối cảnh hữu ích nhưng không đưa mật khẩu, token hoặc dữ liệu nhạy cảm vào lỗi. Nếu có nhiều kiểu thất bại nghiệp vụ cần xử lý riêng, có thể tạo loại ngoại lệ riêng; không tạo một lớp ngoại lệ mới chỉ để thay tên cho một loại có sẵn đã diễn đạt chính xác.

## 6. Các sai lầm thường gặp

- **Nuốt lỗi:** `catch (Exception e) { return null; }` biến sự cố thành một kết quả mơ hồ, làm mất ngữ cảnh. Chỉ cung cấp giá trị dự phòng khi đó là chính sách đã xác định rõ và dữ liệu dự phòng thực sự an toàn.
- **Bắt quá rộng:** bắt `Exception` hoặc `Throwable` ở mọi phương thức làm che khuất lỗi lập trình và có thể bắt cả lỗi hệ thống. Ưu tiên kiểu ngoại lệ cụ thể; đừng bắt `Error` để xử lý như lỗi nghiệp vụ.
- **Dùng ngoại lệ để điều khiển luồng thường xuyên:** thử truy cập phần tử rồi bắt lỗi để kết thúc vòng lặp, hoặc ném ngoại lệ mỗi khi tìm không thấy trong một phép tìm kiếm bình thường, khiến mã khó đọc và có thể tốn chi phí tạo stack trace.
- **Làm mất nguyên nhân:** `throw new RuntimeException("Lỗi")` sau khi bắt `IOException` nhưng không truyền `cause` sẽ làm giảm khả năng truy vết.
- **Vừa ghi log ở mọi tầng vừa ném tiếp:** một lỗi có thể tạo nhiều bản ghi trùng lặp. Xác định tầng chịu trách nhiệm ghi log, thêm ngữ cảnh hoặc phản hồi.
- **Gắn tất cả vào một loại chung:** chỉ dùng `RuntimeException` với cùng thông báo cho lỗi đầu vào, mất kết nối và vi phạm trạng thái làm người gọi không phân biệt được hành động xử lý.
- **Cho rằng ngoại lệ thay thế kiểm tra dữ liệu:** kiểm tra yêu cầu nghiệp vụ vẫn cần thiết. Ngoại lệ thông báo thất bại; nó không tự xác định đâu là dữ liệu hợp lệ và không tự rollback các tác động đã xảy ra.

Về hiệu năng, **ném và tạo ngoại lệ thường tốn chi phí hơn một nhánh điều kiện đơn giản**, nhất là khi cần dựng stack trace; nhưng không nên tránh ngoại lệ bằng mã lỗi trong mọi trường hợp chỉ vì hiệu năng. Hãy lựa chọn theo hợp đồng API và đo đạc nếu luồng thất bại diễn ra với tần suất cao.

## 7. Quy tắc chọn nhanh theo tình huống

1. **Hợp lệ nhưng không có giá trị?** Trả `Optional`, tập rỗng, hoặc một trạng thái tường minh nếu đó là kết quả bình thường. Ví dụ: tìm kiếm không thấy.
2. **Tham số vi phạm hợp đồng?** Cân nhắc `IllegalArgumentException` hoặc loại ngoại lệ cụ thể. Ví dụ: tham số phải dương nhưng nhận số âm.
3. **Thao tác không thực hiện được do tài nguyên bên ngoài?** Dùng kiểu ngoại lệ biểu đạt sự cố, chẳng hạn `IOException`, và để lớp có trách nhiệm xử lý hoặc phục hồi.
4. **Nhiều lỗi dự kiến cần trả đồng thời hoặc tích lũy?** Cân nhắc kiểu kết quả có cấu trúc, đặc biệt cho xác thực đầu vào.
5. **Giao tiếp qua HTTP hay native API dùng mã trạng thái?** Tuân thủ hợp đồng giao thức ở ranh giới đó và chuyển đổi hợp lý sang mô hình lỗi Java ở bên trong.

**Điểm cần ghi nhớ:** giá trị trả về nên mô tả **kết quả thành công**; ngoại lệ nên biểu đạt **thao tác không thể hoàn thành như hợp đồng** và mang thông tin để xử lý/chẩn đoán. Mã trạng thái và `Optional` vẫn đúng khi tình huống đó là một phần bình thường, được mô hình hóa rõ ràng của API.