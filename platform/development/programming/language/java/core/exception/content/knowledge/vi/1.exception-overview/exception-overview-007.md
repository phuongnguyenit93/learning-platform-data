# Kiến thức tiên quyết và trình tự học đề xuất — Java Core Exception

> **Ngữ cảnh:** Java Core → Exception → Tổng quan. Bài này trả lời hai câu hỏi: cần biết gì **trước khi học exception**, và nên học **theo thứ tự nào** để hiểu cơ chế, tự viết mã xử lý lỗi đúng và tiến tới thiết kế chương trình có thể bảo trì. Các ví dụ dùng Java 17 trở lên.

## 1. Đích học tập

Sau lộ trình này, người học cần có khả năng:

1. Đọc được một stack trace, nhận ra loại exception, thông báo, vị trí phát sinh và chuỗi lời gọi.
2. Giải thích luồng thực thi khi exception được ném: đoạn mã nào bị bỏ qua, nơi tìm `catch`, cách stack được tháo dần và ý nghĩa của `finally`.
3. Phân biệt `Error`, checked exception và unchecked exception; lựa chọn bắt hoặc chuyển tiếp dựa trên **khả năng xử lý thực sự**.
4. Dùng `try`/`catch`/`finally`, `throw`, `throws` và try-with-resources đúng ngữ cảnh.
5. Bảo toàn nguyên nhân lỗi, tránh che giấu lỗi và đặt ranh giới xử lý phù hợp với từng tầng chương trình.
6. Kiểm thử cả đường đi thành công lẫn đường đi thất bại, đặc biệt khi xử lý input và tài nguyên.

**Điểm xuất phát tối thiểu:** đã tự viết, biên dịch, chạy được một chương trình Java có phương thức, câu điều kiện và lớp đơn giản. Nếu chưa đạt, hoàn thành Mục 2 trước khi học Mục 4.

## 2. Kiến thức tiên quyết: cần tới đâu?

| Kiến thức | Mức cần thiết | Tự kiểm tra trước khi tiếp tục |
| --- | --- | --- |
| Cú pháp Java cơ bản, kiểu dữ liệu, biến, toán tử, `if/else`, vòng lặp | Bắt buộc | Viết được mã kiểm tra dữ liệu đầu vào và giải thích từng nhánh chạy. |
| Phương thức: tham số, kiểu trả về, `return`, phạm vi biến | Bắt buộc | Theo dõi được lời gọi `main() → methodA() → methodB()` và vị trí trở về của từng phương thức. |
| Lớp, đối tượng, constructor và các mức truy cập | Bắt buộc | Tạo được lớp có phương thức, khởi tạo đối tượng và gọi phương thức của nó. |
| Kế thừa, `extends`, ghi đè, đa hình và quan hệ “is-a” | Bắt buộc trước phần phân cấp exception | Giải thích được tại sao một `catch` của lớp cha có thể bắt đối tượng thuộc lớp con. |
| Cách dùng `javac`, `java`, tên tệp và `public class` | Bắt buộc | Chạy được ví dụ độc lập từ terminal và phân biệt lỗi biên dịch với lỗi khi chạy. |
| Call stack, luồng tuần tự và điểm gọi phương thức | Nên học ngay từ đầu | Vẽ được ba frame khi ba phương thức gọi lồng nhau; hiểu exception đi ngược chiều gọi. |
| Làm việc với file, stream, `AutoCloseable` | Cần trước try-with-resources | Biết vì sao tài nguyên như stream phải đóng, kể cả khi thao tác thất bại. |
| Unit test với JUnit, cách đọc log/debugger | Học song song ở giai đoạn sau | Kiểm tra được kết quả đúng và xác nhận trường hợp ném exception. |

**Không cần học trước:** đa luồng, Spring, JDBC, thiết kế microservice hay toàn bộ API I/O. Exception là kiến thức nền để học các chủ đề đó về sau.

### 2.1. Tự đánh giá nền tảng bằng một chương trình nhỏ

Lưu thành `PrerequisiteCheck.java`:

```java
public class PrerequisiteCheck {
    public static void main(String[] args) {
        System.out.println(describe(8));
        System.out.println(describe(-3));
    }

    static String describe(int value) {
        if (value >= 0) {
            return "Không âm: " + value;
        }
        return "Âm: " + value;
    }
}
```

Chạy:

```bash
javac PrerequisiteCheck.java
java PrerequisiteCheck
```

Kết quả chính xác:

```text
Không âm: 8
Âm: -3
```

Nếu chưa giải thích được lý do chương trình in hai dòng này, hãy ôn `main`, kiểu trả về, tham số, `if` và `return`. Nếu đã vững, thử tự vẽ stack tại thời điểm đang ở trong `describe`. Bài exception kế tiếp sẽ dùng chính quan hệ giữa các lời gọi như vậy.

## 3. Mô hình tinh thần cần nắm trước khi học cú pháp

Trong Java, một exception là một đối tượng đại diện cho tình huống bất thường. Khi thực thi lệnh `throw`, hoặc khi thư viện/JVM phát sinh exception, luồng bình thường tại vị trí đó dừng lại. Runtime tìm handler phù hợp: từ khối `try` hiện tại, rồi đến các phương thức gọi phía ngoài nếu cần. Khi không có handler xử lý được, exception thoát tới đầu luồng thực thi và có thể kết thúc luồng đó với stack trace.

Ví dụ chuỗi lời gọi:

```text
main()
  └── loadProfile()
        └── parseAge()
              └── Integer.parseInt("abc")
                   → NumberFormatException
```

Nếu `parseAge` không bắt exception, nó truyền ra `loadProfile`; nếu `loadProfile` cũng không bắt, tiếp tục tới `main`. Đây gọi là **exception propagation** và **stack unwinding**. Code nằm sau thao tác thất bại trên đường đi bình thường không tiếp tục chạy, còn các khối dọn dẹp liên quan (chẳng hạn `finally` hoặc đóng tài nguyên bằng try-with-resources) vẫn được thực thi theo quy tắc tương ứng.

Không nên hiểu “exception = lỗi hệ thống luôn phải kết thúc chương trình”. Nhiều tình huống có thể dự đoán và xử lý tại đúng ranh giới: người dùng nhập sai, file không tồn tại, yêu cầu không hợp lệ. Ngược lại, **bắt được** exception về mặt cú pháp không có nghĩa là **khôi phục được** về mặt nghiệp vụ.

### 3.1. Nhìn đúng hệ phân cấp

```text
Throwable
├── Error
└── Exception
    ├── RuntimeException
    │   ├── IllegalArgumentException
    │   │   └── NumberFormatException
    │   └── NullPointerException
    └── IOException
        └── FileNotFoundException
```

- **Checked exception:** các lớp con của `Exception`, ngoại trừ `RuntimeException` và các lớp con của nó. Compiler buộc code phải bắt hoặc khai báo `throws`, ví dụ `IOException`. Đây là quy tắc của Java về kiểu ngoại lệ, không bảo đảm rằng người gọi có thể tự khôi phục.
- **Unchecked exception:** `RuntimeException` và lớp con; `Error` và lớp con. Compiler không bắt buộc bắt/khai báo. Ví dụ `NumberFormatException` khi chuỗi không phải số.
- **`Error`:** thường biểu thị vấn đề nghiêm trọng của môi trường/runtime (ví dụ `OutOfMemoryError`). Mã ứng dụng thông thường không nên dùng `catch (Error)` hoặc `catch (Throwable)` làm cách cứu mọi tình huống.

Lưu ý quan trọng: `NumberFormatException` **là một** `IllegalArgumentException`. Vì thế khi dùng nhiều `catch`, nhánh loại con phải đứng trước loại cha. Đọc quan hệ kế thừa trước sẽ giúp hiểu lỗi compiler báo “exception has already been caught”.

## 4. Trình tự học đề xuất: từ cơ chế đến thiết kế

Nên đi theo thứ tự các chặng dưới đây. Chỉ chuyển chặng khi làm được bài kiểm tra nhỏ; số buổi là gợi ý, tùy kinh nghiệm có thể nhanh hoặc chậm.

| Chặng | Chủ đề theo thứ tự | Phải làm được trước khi sang chặng sau |
| --- | --- | --- |
| 0 | Ôn điều kiện, phương thức, đối tượng, kế thừa, call stack | Chạy `PrerequisiteCheck` và vẽ được chuỗi lời gọi. |
| 1 | Exception là gì; `Throwable`/`Exception`/`RuntimeException`/`Error`; đọc stack trace | Nêu được loại lỗi, thông báo, dòng đầu tiên liên quan đến code mình và đường truyền lỗi. |
| 2 | `try`, `catch`, nhiều `catch`, `finally`, luồng điều khiển | Dự đoán chính xác nhánh chạy, nhánh bị bỏ qua và đầu ra với input hợp lệ/sai. |
| 3 | Checked/unchecked; `throw`, `throws`; lan truyền qua phương thức | Biết khi nào cần `throws IOException`, khi nào ném `IllegalArgumentException`. |
| 4 | Try-with-resources, `AutoCloseable`, đóng tài nguyên, suppressed exceptions | Đọc file/stream an toàn mà không cần tự đóng ở mọi nhánh. |
| 5 | Exception tùy biến; message, cause; ném lại và bọc lỗi | Giữ được nguyên nhân gốc khi chuyển lỗi từ tầng thấp lên tầng cao. |
| 6 | Quyết định vị trí bắt; lỗi người dùng và lỗi lập trình; logging | Không nuốt lỗi, không dùng exception để thay câu điều kiện thông thường. |
| 7 | Test các trường hợp lỗi, debug stack trace, tổng hợp | Viết test cho giá trị thường, input sai, lỗi I/O và giải phóng tài nguyên. |

### Chặng 0 — Xác nhận nền tảng

Tự viết ít nhất một phương thức gọi phương thức khác. Khi chương trình gặp một giá trị bất hợp lệ, xác định được nó do điều kiện nào tạo ra. Ôn tính kế thừa với hai lớp cha/con và thử truyền đối tượng con qua biến kiểu cha. Đây là chuẩn bị trực tiếp cho cơ chế bắt exception theo kiểu đối tượng.

**Tiêu chí qua chặng:** biết `return` kết thúc một lời gọi bình thường; hiểu `throw` sẽ thay đổi luồng đó theo một cách khác.

### Chặng 1 — Bắt đầu từ stack trace, sau đó mới học cú pháp

Chạy một ví dụ gây `NumberFormatException` từ `Integer.parseInt("abc")`. Quan sát dòng đầu chứa tên exception, thông điệp và các frame `at ...` bên dưới. Tìm frame đầu tiên thuộc mã của mình và truy ngược chuỗi caller. Vị trí ngoài cùng không nhất thiết là nơi xuất hiện nguyên nhân đầu tiên, đặc biệt khi lỗi được bọc bằng exception khác.

**Thực hành:** giải thích sự khác nhau giữa “nơi lỗi phát sinh”, “nơi lỗi được bắt” và “nơi thông báo được in ra”. Không nên học cách xóa stack trace khỏi màn hình trước khi hiểu nó.

### Chặng 2 — Học bắt lỗi và luồng đi qua `finally`

Học `try` với một `catch` cụ thể, rồi nhiều `catch` theo thứ tự từ kiểu con đến kiểu cha; cuối cùng học `finally`. Hiểu rằng `finally` thường chạy dù có exception hay `return`, nhưng không được dùng như cơ chế bảo đảm tuyệt đối trong mọi trường hợp như JVM bị dừng đột ngột. Không nên `return` hoặc `throw` mới trong `finally` vì có thể che mất kết quả hoặc lỗi ban đầu.

**Thực hành:** dự đoán kết quả với chuỗi `"15"`, `"abc"` và một số âm. Đối chiếu kết quả thực tế ở Mục 5.1.

### Chặng 3 — Tách trách nhiệm: tạo lỗi, khai báo lỗi và xử lý lỗi

- `throw new IllegalArgumentException("...")`: **ném một đối tượng** exception ở một vị trí cụ thể.
- `throws IOException` trong chữ ký phương thức: **khai báo khả năng** exception thoát khỏi phương thức; bản thân nó không ném lỗi.
- `catch (IOException e)`: xử lý tại đây khi có hành động hợp lý, như trả thông báo phù hợp cho caller, bổ sung ngữ cảnh hoặc phục hồi bằng phương án dự phòng.

Checked exception là ràng buộc compile-time đối với API; unchecked exception không bị ràng buộc khai báo. Cả hai đều có thể truyền qua nhiều lớp gọi khi runtime chạy. `throws` cho unchecked exception là tùy chọn, có thể hữu ích để diễn đạt hợp đồng nhưng không thay thế tài liệu API.

**Thực hành:** thử bỏ `throws IOException` khỏi phương thức đọc `BufferedReader.readLine()` ở Mục 5.2 mà không thêm `catch`; giải thích lỗi biên dịch. Đừng cố “sửa” bằng cách bắt rồi bỏ qua exception.

### Chặng 4 — Quản lý tài nguyên an toàn

Học `try (resource = ...) { ... }` với đối tượng triển khai `AutoCloseable`. Tài nguyên đóng khi ra khỏi khối, cả khi có exception; nếu nhiều tài nguyên khai báo trong ngoặc, chúng đóng theo thứ tự ngược. Nếu thao tác trong `try` đã ném exception và đóng tài nguyên cũng lỗi, lỗi đóng thường được giữ ở `getSuppressed()` thay vì thay thế lỗi chính. Một đối tượng được đưa vào try-with-resources phải tuân theo các yêu cầu của cú pháp khai báo/tham chiếu resource trong Java.

**Thực hành:** chạy Mục 5.2, sau đó thử thay `StringReader` bằng tài nguyên `AutoCloseable` tự viết để quan sát thao tác đóng khi khối ném lỗi.

### Chặng 5 — Thiết kế và truyền ngữ cảnh lỗi

Chỉ tạo exception riêng khi bên gọi cần phân biệt một loại lỗi có ý nghĩa, ví dụ `InvalidQuantityException`. Chọn checked hay unchecked dựa trên hợp đồng API và khả năng xử lý của bên gọi; không có quy tắc “lỗi nghiệp vụ luôn checked” áp dụng cho mọi ứng dụng. Khi chuyển đổi ngoại lệ, dùng constructor có `cause` nếu có thể, chẳng hạn `new IllegalStateException("Không nạp được cấu hình", e)`, để giữ đường truy vết nguồn gốc.

**Thực hành:** viết một exception tên có ý nghĩa và bắt đúng loại đó ở tầng trình bày. So sánh với việc bắt `Exception` chung rồi hiển thị một thông báo không chứa ngữ cảnh.

### Chặng 6 — Xử lý lỗi tại ranh giới phù hợp

Một tầng thấp thường không biết người dùng cuối cần thấy thông báo gì; tầng giao tiếp (CLI, UI, API) thường biết cách chuyển tình trạng thất bại thành thông báo/kết quả phù hợp. Nơi phát sinh lỗi nên cung cấp ngữ cảnh đủ; nơi có khả năng xử lý mới quyết định thử lại, yêu cầu nhập lại, báo thất bại hoặc dừng.

Phân biệt **giá trị đầu vào bất hợp lệ thường gặp** với **tình huống bất thường**: có thể dùng điều kiện `if` để kiểm tra thiếu input trước khi gọi API, và dùng exception cho việc báo hiệu vi phạm hợp đồng hoặc thất bại thực thi. Đừng dùng exception làm đường điều khiển chính cho vòng lặp bình thường.

**Thực hành:** với nhập tuổi từ người dùng, hãy bắt `NumberFormatException` ở tầng nhập liệu, nêu yêu cầu nhập lại; không đặt `System.out.println` ở sâu trong hàm chuyển chuỗi thành số rồi trả về giá trị giả như `-1`.

### Chặng 7 — Kiểm thử và đọc lỗi trong tình huống thực tế

Với mỗi hàm có thể thất bại, chuẩn bị ít nhất một đường thành công và các ca thất bại có ý nghĩa. Trong JUnit 5, `assertThrows(IllegalArgumentException.class, () -> method(...))` thường phù hợp để xác nhận exception; kiểm thêm message/cause khi chúng là một phần hợp đồng. Kiểm tra tài nguyên được đóng ở cả đường thành công và thất bại. Dùng debugger hoặc stack trace để xác định chính xác nơi xảy ra vấn đề; log lỗi **một cách có chủ đích** ở ranh giới xử lý, tránh log lặp cùng stack trace ở nhiều tầng.

**Tiêu chí kết thúc:** có thể giải thích cho người khác không chỉ *exception gì xảy ra*, mà còn *vì sao bắt tại vị trí đó*, *bên gọi nhận được gì*, *tài nguyên được giải phóng ra sao*.

## 5. Hai bài thực hành Java 17 chạy độc lập

Hai chương trình được thiết kế để học theo đúng trình tự: đầu tiên là unchecked exception và chọn nhánh `catch`; tiếp theo là checked exception và vòng đời tài nguyên. Mỗi code fence `java` là một tệp độc lập, lưu theo đúng tên ở đầu phần.

### 5.1. Bắt ngoại lệ cụ thể và hiểu quan hệ kế thừa

Lưu thành `FirstExceptions.java`:

```java
public class FirstExceptions {
    public static void main(String[] args) {
        for (String input : new String[] {"12", "x", "-5"}) {
            try {
                int age = parseAge(input);
                System.out.println("OK: " + age);
            } catch (NumberFormatException e) {
                System.out.println("Không phải số: " + input);
            } catch (IllegalArgumentException e) {
                System.out.println("Tuổi âm: " + input);
            }
        }
    }

    static int parseAge(String text) {
        int age = Integer.parseInt(text);
        if (age < 0) {
            throw new IllegalArgumentException("Tuổi không hợp lệ");
        }
        return age;
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 FirstExceptions.java
java FirstExceptions
```

Stdout:

```text
OK: 12
Không phải số: x
Tuổi âm: -5
```

Diễn giải: `"12"` được parse và trả về bình thường; `"x"` khiến `Integer.parseInt` ném `NumberFormatException`; `"-5"` parse thành công rồi bị kiểm tra nghiệp vụ từ chối bằng `IllegalArgumentException`. Vì `NumberFormatException extends IllegalArgumentException`, phải đặt nhánh bắt hẹp trước nhánh rộng. Đảo vị trí hai nhánh sẽ gây lỗi biên dịch do nhánh hẹp không còn khả năng được chọn.

**Bài tập tăng dần:** thêm input `"0"`; đổi điều kiện thành `age <= 0` và dự đoán đầu ra; tạo lời gọi `parseAge(null)` rồi phân tích exception thực tế. Không mặc định rằng mọi giá trị `null` đều gây `NullPointerException`: hành vi phụ thuộc vào API được gọi.

### 5.2. Checked exception và try-with-resources

Lưu thành `ResourceExample.java`:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class ResourceExample {
    public static void main(String[] args) {
        try {
            System.out.println(firstLine("Java\nException"));
        } catch (IOException e) {
            System.out.println("Lỗi đọc: " + e.getMessage());
        }
    }

    static String firstLine(String text) throws IOException {
        try (BufferedReader reader =
                     new BufferedReader(new StringReader(text))) {
            return reader.readLine();
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ResourceExample.java
java ResourceExample
```

Stdout:

```text
Java
```

`BufferedReader.readLine()` khai báo có thể ném `IOException`. Vì vậy `firstLine` khai báo `throws IOException` và `main` bắt loại đó, dù input in-memory cụ thể ở ví dụ này đọc thành công. Try-with-resources đóng `BufferedReader` khi rời khối; với stream/file thật, việc đóng đúng cách tránh rò rỉ tài nguyên.

**Bài tập tăng dần:** thay nội dung bằng chuỗi rỗng và dự đoán giá trị trả về; thêm một `AutoCloseable` đơn giản in thông báo trong `close()` để thấy thứ tự đóng. Nếu thay bằng `FileReader`, phải quan tâm đường dẫn/tồn tại của file và encoding, không dùng stdout của ví dụ in-memory làm dự báo cho môi trường file thật.

## 6. Lịch học thực hành gợi ý

Đối với người đã chắc Java cơ bản, có thể chia thành **năm buổi**, mỗi buổi dành một phần cho đọc, một phần cho viết/đánh lỗi và một phần cho giải thích lại:

| Buổi | Trọng tâm | Sản phẩm kiểm chứng |
| --- | --- | --- |
| 1 | Ôn call stack, phân cấp `Throwable`, tạo lỗi và đọc stack trace | Sơ đồ 3 tầng lời gọi; giải thích 1 stack trace của chính mình. |
| 2 | `try`, `catch`, `finally`, checked và unchecked | Chạy `FirstExceptions`; dự đoán kết quả trước khi chạy. |
| 3 | `throw`, `throws`, propagation; xử lý lỗi theo trách nhiệm caller | Viết 2–3 phương thức gọi nhau và quyết định nơi bắt có lý do. |
| 4 | Try-with-resources, tài nguyên, suppressed exceptions | Chạy `ResourceExample`; chứng minh resource đóng khi xảy ra lỗi. |
| 5 | Custom exception, cause, ranh giới bắt lỗi, kiểm thử | Hoàn thành bài tổng hợp Mục 7 và giải thích mọi quyết định xử lý. |

Nếu chưa biết kế thừa hoặc phương thức, thêm một đến hai buổi nền tảng trước Buổi 1. Nếu đã dùng exception trong dự án, vẫn nên kiểm tra Chặng 1, 4 và 6 vì đọc stack trace, giữ cause và vòng đời resource là những kỹ năng dễ bị bỏ sót.

## 7. Bài tổng hợp để xác nhận thực sự hiểu

**Đề bài:** viết chương trình nhận danh sách chuỗi đại diện cho số lượng đặt hàng. Chương trình cố chuyển từng chuỗi thành số nguyên dương và in kết quả cho từng phần tử. Với chuỗi không parse được hoặc số không hợp lệ, nêu lỗi cụ thể và tiếp tục phần tử kế tiếp. Phần chuyển đổi nên là một phương thức độc lập, không tự in ra console.

Yêu cầu thực hiện:

1. Viết `parseQuantity(String text)` trả về `int`; dùng `Integer.parseInt` và `throw new IllegalArgumentException(...)` cho số không dương.
2. Ở `main`, bắt riêng `NumberFormatException` và `IllegalArgumentException` theo thứ tự đúng; không dùng `catch (Exception e)` để bỏ qua mọi lỗi.
3. Kiểm với `"3"`, `"0"`, `"-2"`, `"abc"`. Chỉ `"3"` là input được chấp nhận.
4. Bổ sung một hàm đọc dữ liệu qua `BufferedReader` trong try-with-resources, khai báo/bắt `IOException` hợp lý.
5. Giải thích bằng lời nếu lỗi xuất hiện trong hàm chuyển đổi thì mã đi qua những phương thức nào trước khi tới `catch`.
6. Kiểm tra rằng exception phát sinh ngoài dự kiến không bị âm thầm nuốt, và thông điệp hiển thị cho người dùng không lộ dữ liệu nhạy cảm.

Không cần framework để hoàn thành bài này. Khi đã làm được, bạn có nền tảng để học xử lý exception trong I/O thực tế, thư viện Java và các framework.

## 8. Lỗi học tập phổ biến và cách sửa

| Nhầm lẫn | Điều cần ghi nhớ |
| --- | --- |
| “Bất cứ exception nào cũng phải `catch` ngay tại nơi phát sinh.” | Chỉ bắt khi tầng hiện tại có cách xử lý phù hợp. Nếu không, truyền ra ngoài và giữ ngữ cảnh. |
| “`throws` tự tạo ra exception.” | `throws` khai báo hợp đồng; `throw` mới là câu lệnh ném một đối tượng exception. |
| “Checked nghĩa là nghiêm trọng hơn unchecked.” | Đó là phân loại ràng buộc của compiler, không phải thang mức độ nghiêm trọng. |
| “`finally` luôn chạy trong mọi trường hợp.” | Nó thường chạy theo quy tắc điều khiển của Java, nhưng JVM/process có thể chấm dứt bất thường. |
| “`catch (Exception e) {}` làm ứng dụng an toàn.” | Bắt rồi bỏ qua làm mất tín hiệu lỗi, khiến dữ liệu/hành vi sai khó phát hiện. |
| “In `e.getMessage()` là đủ để debug.” | Thông báo không luôn có đầy đủ chuỗi gọi hoặc nguyên nhân; cần giữ stack trace và cause phù hợp. |
| “Lỗi parse số là `IOException`.” | `Integer.parseInt` ném `NumberFormatException` (unchecked); lỗi đọc nguồn có thể là `IOException` (checked). |
| “Luôn dùng exception tùy biến cho mọi trường hợp.” | Chỉ thêm kiểu mới khi có ngữ nghĩa hoặc nhu cầu xử lý riêng rõ ràng. |
| “Catch `RuntimeException`/`Throwable` ở khắp nơi để tránh crash.” | Có thể che lỗi lập trình hoặc lỗi hệ thống. Chỉ dùng handler rộng ở ranh giới đã cân nhắc. |
| “Đóng stream ở cuối phương thức là đủ.” | Nếu thao tác giữa chừng thất bại, đoạn cuối có thể bị bỏ qua; ưu tiên try-with-resources. |
| “Sau khi `throw`, các câu lệnh phía sau trong cùng đường đi vẫn chạy.” | Lệnh `throw` chuyển điều khiển bất thường; đường chạy bình thường không tiếp tục từ vị trí đó. |

## 9. Checklist hoàn thành lộ trình

Tự đánh dấu **đạt** khi có thể trả lời và thực hiện mà không nhìn tài liệu:

- [ ] Tự chạy được hai chương trình Java 17 trong bài và giải thích stdout từng dòng.
- [ ] Vẽ được caller chain và nói chính xác nơi exception được ném, lan truyền và bắt.
- [ ] Giải thích được vì sao bắt lớp cha trước lớp con có thể làm lỗi biên dịch.
- [ ] Phân biệt được `Error`, checked exception và unchecked exception với ví dụ đúng.
- [ ] Viết đúng `try`/`catch`/`finally`, `throw` và `throws`; nêu chức năng riêng của từng cấu trúc.
- [ ] Không sử dụng `catch` rỗng hoặc chuyển mọi lỗi thành giá trị giả mà không có hợp đồng rõ ràng.
- [ ] Dùng try-with-resources cho tài nguyên cần đóng và hiểu lỗi phát sinh khi đóng có thể được suppressed.
- [ ] Khi bọc một exception, giữ được `cause` thay vì chỉ giữ text thông báo.
- [ ] Biết tại sao từng loại lỗi được bắt tại tầng hiện tại hoặc truyền cho caller.
- [ ] Kiểm thử được cả ca thành công và ca lỗi, rồi đọc stack trace để tìm nguyên nhân.

**Sau lộ trình:** chuyển sang những chủ đề áp dụng exception cụ thể (Java I/O/NIO, xử lý dữ liệu, API, concurrent programming), nơi các nguyên tắc trên được dùng với nguồn lỗi và tài nguyên thực tế.