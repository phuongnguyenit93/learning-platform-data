# Phân biệt quy tắc checked với khả năng phục hồi thực tế trong Java

Trong Java, *checked exception* và *unchecked exception* mô tả cách **trình biên dịch kiểm soát việc khai báo hoặc xử lý ngoại lệ**. Trong khi đó, **khả năng phục hồi** (recoverability) là câu hỏi ở thời điểm chạy: chương trình có thể thực hiện hành động cụ thể nào để tiếp tục đúng đắn sau thất bại?

Hai khái niệm có liên quan khi thiết kế API, nhưng **không đồng nhất**:

- Ngoại lệ *checked* vẫn có thể là lỗi mà phương thức hiện tại hoặc cả ứng dụng không thể khắc phục.
- Ngoại lệ *unchecked* vẫn có thể biểu diễn một tình huống dự kiến và có phương án xử lý an toàn, chẳng hạn dữ liệu người dùng không thể chuyển thành số.
- `catch` làm chương trình **chặn và xử lý luồng điều khiển** tại một điểm; riêng việc bắt được đối tượng ngoại lệ **không chứng minh đã khôi phục thành công**.

Mục tiêu bài học là phân biệt nghĩa vụ của ngôn ngữ với quyết định xử lý lỗi dựa trên nghiệp vụ, trạng thái và ranh giới trách nhiệm.

## 1. Phân cấp ngoại lệ và ý nghĩa của checked/unchecked

~~~text
java.lang.Throwable
├── java.lang.Error                           [unchecked]
│   └── java.lang.OutOfMemoryError            [unchecked]
└── java.lang.Exception                       [checked]
    ├── java.io.IOException                   [checked]
    ├── java.text.ParseException              [checked]
    └── java.lang.RuntimeException            [unchecked]
        ├── java.lang.IllegalArgumentException[unchecked]
        │   └── java.lang.NumberFormatException [unchecked]
        └── java.lang.IllegalStateException   [unchecked]
~~~

Đây là một phần của cây, không phải toàn bộ phân cấp. Đặc biệt, `NumberFormatException` là **lớp con của `IllegalArgumentException`**, không phải một nhánh ngang hàng.

Theo quy tắc Java, các lớp kế thừa `Throwable` **trừ** `RuntimeException` và `Error` cùng mọi lớp con của hai nhánh đó là *checked*. Vì vậy:

- `IOException` và `ParseException` là checked.
- `RuntimeException`, `NumberFormatException`, `IllegalStateException` và `Error` là unchecked.
- `RuntimeException` **vẫn kế thừa `Exception`**, nhưng được miễn quy tắc checked.
- Phân loại này không phải mức độ nghiêm trọng và không đo khả năng khôi phục.

### Quy tắc của trình biên dịch

Khi một thao tác **có thể ném checked exception** theo thông tin kiểu mà trình biên dịch thấy, mã bao quanh phải xử lý hoặc khai báo ngoại lệ theo luật Java. Hai cách thông dụng:

1. Bắt ngoại lệ bằng `try/catch` ở tầng đủ khả năng quyết định.
2. Cho phép lan truyền bằng cách khai báo `throws` ở chữ ký phương thức.

Ví dụ:

~~~java
static String readConfig(java.nio.file.Path path) throws java.io.IOException {
    return java.nio.file.Files.readString(path);
}
~~~

Đây là **đoạn phương thức minh họa**, chưa phải chương trình chạy độc lập. `Files.readString` có thể ném `IOException`; ví dụ cho phép chuyển tiếp qua `throws IOException`. Nếu nơi gọi không bắt hoặc khai báo checked exception tương ứng, trình biên dịch có thể báo `unreported exception ...; must be caught or declared to be thrown`.

Ngược lại:

~~~java
static int parsePort(String text) {
    return Integer.parseInt(text);
}
~~~

`Integer.parseInt` có thể ném `NumberFormatException`, nhưng không phải thêm `throws NumberFormatException`. Ngoại lệ vẫn xảy ra và lan truyền **khi chạy** nếu đầu vào không hợp lệ.

**`throws` là hợp đồng tĩnh**, không phải lệnh thực hiện khôi phục. **`throw` là lệnh phát sinh ngoại lệ**. **`catch` là nơi có thể xử lý ngoại lệ**, nhưng hành động trong khối `catch` mới quyết định hậu quả.

## 2. Hai trục độc lập: phân loại và khả năng phục hồi

Có thể hình dung mỗi ngoại lệ theo hai câu hỏi riêng:

1. **Compiler:** Kiểu ngoại lệ này thuộc checked hay unchecked?
2. **Runtime và nghiệp vụ:** Ở vị trí đang xét, có cách an toàn nào để đạt mục tiêu, đưa trạng thái về hợp lệ hoặc thông báo thất bại đúng cách không?

| | Có phương án phục hồi phù hợp | Không có phương án phục hồi tại đây |
| --- | --- | --- |
| **Checked** | `IOException` khi có bản cấu hình dự phòng hợp lệ; đọc lại tài nguyên khi chính sách cho phép | `IOException` do mất tệp bắt buộc mà không có nguồn thay thế; `SQLException` khi giao dịch không còn hợp lệ |
| **Unchecked** | `NumberFormatException` khi giao diện yêu cầu người dùng nhập lại số hợp lệ | `IllegalStateException` khi thao tác vi phạm trạng thái nội bộ; `NullPointerException` do lỗi logic chưa được sửa |

**Các ô trong bảng là ví dụ phụ thuộc ngữ cảnh, không phải tính chất cố định của lớp ngoại lệ.** Cùng một `IOException` có thể phục hồi được ở một màn hình có chức năng chọn lại tệp, nhưng không thể phục hồi trong một bước khởi tạo bắt buộc. Cùng một `NumberFormatException` có thể là lỗi dữ liệu dự kiến ở UI, nhưng là lỗi lập trình nếu chuỗi là hằng số do chính chương trình định nghĩa và đáng lẽ luôn hợp lệ.

Cần phân biệt thêm ba kết quả:

- **Phục hồi để hoàn thành mục tiêu:** Dùng nguồn dự phòng đã kiểm chứng; yêu cầu nhập lại và nhận giá trị đúng; thử lại theo chính sách an toàn.
- **Xử lý thất bại có kiểm soát:** Dừng thao tác, trả lỗi có nghĩa, giữ giao dịch nhất quán, giải phóng tài nguyên. Đây là *error handling* đúng đắn, **chưa chắc là recovery**.
- **Che giấu thất bại:** Bắt ngoại lệ rồi bỏ qua, trả giá trị giả không có hợp đồng, hoặc tiếp tục khi trạng thái đã hỏng. Cách này có thể làm hậu quả khó phát hiện hơn.

Khả năng phục hồi thuộc về **ngữ cảnh tầng gọi và chính sách hệ thống**. Không nên gán một thuộc tính `recoverable=true/false` cố định cho toàn bộ lớp ngoại lệ.

## 3. Chương trình Java 17+ thể hiện đủ bốn trường hợp

Ví dụ giả lập nguồn cấu hình chính bị lỗi theo cách có thể dự đoán. Một quy trình có bản dự phòng nên khôi phục được; quy trình khác phải dừng bước khởi tạo. Sau đó chương trình xử lý giá trị tuổi người dùng nhập sai (unchecked nhưng có hướng khắc phục) và một lỗi trạng thái đối tượng (unchecked, không thể tiếp tục thao tác đó).

Tạo tệp **`RecoveryDemo.java`**:

~~~java
import java.io.IOException;

public class RecoveryDemo {
    public static void main(String[] args) {
        System.out.println("1. Checked - có bản dự phòng");
        loadWithFallback();

        System.out.println("2. Checked - không có bản dự phòng");
        loadWithoutFallback();

        System.out.println("3. Unchecked - có giá trị nhập lại");
        int age = parseAgeWithCorrection("hai mươi", "20");
        System.out.println("Tuổi hợp lệ: " + age);

        System.out.println("4. Unchecked - trạng thái không hợp lệ");
        try {
            requireReady(false);
        } catch (IllegalStateException e) {
            System.out.println("Hủy thao tác: " + e.getMessage());
        }
    }

    // IOException vẫn là checked dù dữ liệu được giả lập cho ví dụ.
    static String readConfiguration(String source) throws IOException {
        if ("primary".equals(source)) {
            throw new IOException("nguồn chính không phản hồi");
        }
        if ("backup".equals(source)) {
            return "SAFE";
        }
        throw new IOException("nguồn cấu hình không tồn tại");
    }

    static void loadWithFallback() {
        try {
            String mode = readConfiguration("primary");
            System.out.println("Chế độ: " + mode);
        } catch (IOException primaryFailure) {
            try {
                String mode = readConfiguration("backup");
                System.out.println("Đã chuyển sang bản dự phòng: " + mode);
            } catch (IOException backupFailure) {
                backupFailure.addSuppressed(primaryFailure);
                System.out.println(
                        "Không tải được cấu hình: " + backupFailure.getMessage());
            }
        }
    }

    static void loadWithoutFallback() {
        try {
            readConfiguration("primary");
            System.out.println("Khởi tạo thành công");
        } catch (IOException e) {
            System.out.println("Dừng bước khởi tạo: " + e.getMessage());
        }
    }

    static int parseAgeWithCorrection(String first, String corrected) {
        try {
            return Integer.parseInt(first);
        } catch (NumberFormatException e) {
            System.out.println("Giá trị nhập sai: " + first);
            return Integer.parseInt(corrected);
        }
    }

    static void requireReady(boolean ready) {
        if (!ready) {
            throw new IllegalStateException("đối tượng chưa sẵn sàng");
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac RecoveryDemo.java
java RecoveryDemo
~~~

Kết quả chuẩn:

~~~text
1. Checked - có bản dự phòng
Đã chuyển sang bản dự phòng: SAFE
2. Checked - không có bản dự phòng
Dừng bước khởi tạo: nguồn chính không phản hồi
3. Unchecked - có giá trị nhập lại
Giá trị nhập sai: hai mươi
Tuổi hợp lệ: 20
4. Unchecked - trạng thái không hợp lệ
Hủy thao tác: đối tượng chưa sẵn sàng
~~~

### Phân tích từng nhánh

**Trường hợp 1 — checked và phục hồi được:** `readConfiguration("primary")` ném `IOException`. `loadWithFallback` đã có nguồn `"backup"` được chấp nhận nên đọc thành công và in `SAFE`. Điều làm phục hồi được là **nguồn thay thế cùng chính sách dùng nguồn thay thế**, không phải từ khóa `checked`.

**Trường hợp 2 — checked và không phục hồi ở bước hiện tại:** Cùng kiểu `IOException`, cùng nguồn lỗi. `loadWithoutFallback` không có giải pháp thay thế nên báo hỏng và dừng bước khởi tạo. Phương thức có `catch` nhưng **không hoàn tất mục tiêu tải cấu hình**. Trong ứng dụng thực, bên gọi phải hiểu kết quả thất bại; có thể chuyển tiếp ngoại lệ hoặc trả kết quả thể hiện rõ trạng thái thay vì in rồi tiếp tục như ví dụ trình diễn.

**Trường hợp 3 — unchecked và phục hồi được:** `Integer.parseInt("hai mươi")` ném `NumberFormatException`. Phần xử lý cung cấp giá trị mới `"20"` và hoàn thành mục tiêu. Chương trình không cần khai báo checked exception để thực hiện nhánh phục hồi. Ví dụ giả lập người dùng nhập lại; ở ứng dụng thực, cần xác thực giá trị mới và cho phép nhập lại an toàn, tránh giả định mọi lần nhập lại sẽ đúng.

**Trường hợp 4 — unchecked và không phục hồi:** `requireReady(false)` phát hiện tiền điều kiện về trạng thái không được đáp ứng. Khối `catch` hủy thao tác đó và hiển thị lý do. Nó không biến trạng thái đối tượng thành hợp lệ; muốn thực hiện lại phải sửa quy trình khởi tạo ở nơi có thẩm quyền.

Ở nhánh nguồn dự phòng lỗi tiếp, lệnh `backupFailure.addSuppressed(primaryFailure)` giữ thất bại ban đầu để phục vụ chẩn đoán. Nhánh này **không xảy ra trong lần chạy minh họa** vì nguồn `backup` hoạt động. Cơ chế suppressed exceptions hữu ích khi cần giữ nhiều lỗi có liên quan; trong hệ thống thực thường cần chuyển tiếp hoặc ghi nhận lỗi tổng hợp theo hợp đồng thay vì chỉ in thông báo.

## 4. Nghĩa vụ của `catch/throws` không tương đương chính sách lỗi

Xem hai cách dùng với checked exception:

~~~java
static String load(java.nio.file.Path path) throws java.io.IOException {
    return java.nio.file.Files.readString(path);
}
~~~

Phương thức `load` chọn **chuyển trách nhiệm ra ngoài**. Đây có thể là lựa chọn tốt vì tầng gọi biết có tệp dự phòng hay có nên hiện thông báo chọn tệp khác. Khai báo `throws IOException` thể hiện loại thất bại mà người gọi phải cân nhắc, chứ không hứa rằng có thể khôi phục.

~~~java
static String loadOrDefault(java.nio.file.Path path)
        throws java.io.IOException {
    try {
        return java.nio.file.Files.readString(path);
    } catch (java.nio.file.NoSuchFileException e) {
        return "default";
    }
}
~~~

Đây là hai **đoạn phương thức độc lập**, chưa có `main`. Đoạn thứ hai chỉ đúng về nghiệp vụ nếu **hợp đồng cho phép dùng giá trị mặc định khi tệp không tồn tại**. Các lỗi I/O khác vẫn có thể lan qua `throws IOException`. Nếu tệp là bí mật cấu hình bắt buộc, việc dùng `"default"` im lặng có thể nguy hiểm hoặc tạo cấu hình sai.

Khi checked exception lan qua nhiều lớp, có thể chọn khai báo kiểu cụ thể; không nên mặc định dùng `throws Exception` cho mọi API. Một số framework hoặc ranh giới kiến trúc quyết định chuyển ngoại lệ thấp tầng thành loại lỗi miền (*domain exception*) để diễn đạt hợp đồng ở tầng cao hơn. Khi chuyển, nên giữ nguyên nhân:

~~~java
static String loadRequired(java.nio.file.Path path) {
    try {
        return java.nio.file.Files.readString(path);
    } catch (java.io.IOException e) {
        throw new IllegalStateException(
                "Không thể nạp cấu hình bắt buộc", e);
    }
}
~~~

Đây là đoạn phương thức minh họa. Việc chuyển `IOException` sang `IllegalStateException` làm **thay đổi yêu cầu kiểm tra tại thời điểm biên dịch của người gọi**, không làm lỗi biến mất và không khiến nó tự phục hồi. `getCause()` của ngoại lệ mới trả về `IOException` gốc.

## 5. Tiêu chí thực tế để quyết định có phục hồi hay không

Trước khi bắt một ngoại lệ nhằm tiếp tục hoạt động, hãy kiểm tra:

1. **Mục tiêu có còn đạt được không?** Có tệp khác, nguồn dự phòng, cách xác thực lại dữ liệu hoặc cách chạy lại thao tác hay không?
2. **Dữ liệu và trạng thái có còn nhất quán không?** Nếu giao dịch đã có thay đổi một phần, cần rollback hoặc cơ chế bù trừ trước khi thử lại.
3. **Thao tác có an toàn khi lặp lại không?** Đọc tài nguyên có thể thử lại; ghi tiền, gửi yêu cầu hoặc tạo bản ghi có thể gây tác dụng phụ lặp, cần cơ chế idempotency hoặc kiểm soát giao dịch.
4. **Lỗi có tạm thời không?** Timeout mạng có thể là tạm thời; tệp cấu hình sai định dạng thường không tự đúng sau một lần retry. Phải giới hạn số lần thử, thời gian chờ và ngân sách tài nguyên.
5. **Tầng này có đủ thẩm quyền không?** Hàm đọc tệp có thể không biết dùng bản mặc định hay buộc khởi động thất bại. Chuyển lỗi lên tầng điều phối thường chính xác hơn.
6. **Có giữ được nguyên nhân và ngữ cảnh không?** Thông báo, cause, suppressed exception, mã lỗi hoặc log có cấu trúc giúp phân tích khi không thể khôi phục.

Các câu hỏi này áp dụng cho **cả checked lẫn unchecked**.

### Ví dụ theo ranh giới ứng dụng

| Ranh giới | Ngoại lệ có thể gặp | Cách ứng xử phù hợp |
| --- | --- | --- |
| Màn hình nhập biểu mẫu | `NumberFormatException` (unchecked) | Hiển thị trường nhập sai, giữ dữ liệu khác, yêu cầu sửa |
| Bộ nạp cấu hình | `IOException` (checked) | Dùng nguồn dự phòng **nếu hợp đồng cho phép**, hoặc báo không thể khởi tạo |
| Dịch vụ nghiệp vụ | `IllegalArgumentException` (unchecked) | Trả thông tin đầu vào không hợp lệ; không thử lại cùng dữ liệu vô hạn |
| Tầng truy cập tài nguyên | `IOException` (checked) | Cung cấp lỗi có ngữ cảnh, đóng tài nguyên, để tầng trên quyết định |
| Bộ điều phối tác vụ | Ngoại lệ bất ngờ chưa xử lý | Ghi nhận, hủy hoặc đánh dấu tác vụ thất bại; không âm thầm coi tác vụ thành công |

“Xử lý phù hợp” không nhất thiết mang nghĩa “chạy tiếp bình thường”. Một kết quả **thất bại minh bạch, trạng thái an toàn** thường tốt hơn việc che giấu lỗi để trả về thành công giả.

## 6. Các bẫy thường gặp

### Bẫy 1: “Checked nghĩa là chắc chắn phục hồi được”

Không. `IOException` là checked dù mất tệp bắt buộc không có dự phòng. `catch` có thể chỉ thêm ngữ cảnh và chuyển tiếp; yêu cầu biên dịch không cung cấp giải pháp nghiệp vụ.

### Bẫy 2: “Unchecked luôn là bug, đừng bao giờ bắt”

Không. `NumberFormatException` từ dữ liệu do người dùng nhập là tình huống hợp lệ để xử lý ở lớp UI. `IllegalArgumentException` từ yêu cầu ngoài hệ thống cũng có thể được ánh xạ thành lỗi xác thực. Tuy nhiên, nếu nguyên nhân là sai invariant nội bộ, nên sửa mã hoặc quy trình thay vì coi mọi lỗi là dữ liệu không hợp lệ.

### Bẫy 3: “Đã `catch` thì hệ thống đã phục hồi”

Ví dụ sai:

~~~java
try {
    saveImportantData();
} catch (Exception ignored) {
    // Tiếp tục và coi như lưu thành công.
}
~~~

Đây là đoạn **phản ví dụ về chính sách lỗi**, không phải chương trình chạy độc lập; `saveImportantData()` đại diện cho thao tác của ứng dụng. Bắt rồi bỏ qua có thể khiến bên gọi hiểu nhầm dữ liệu đã lưu. Hãy xử lý kết quả thất bại đúng hợp đồng: retry có kiểm soát, rollback, trả trạng thái lỗi hoặc chuyển tiếp ngoại lệ.

### Bẫy 4: “Đổi checked sang runtime là giải quyết vấn đề”

Bọc `IOException` trong `RuntimeException` loại bỏ nghĩa vụ `catch/throws` của người gọi nhưng **không khôi phục tài nguyên**. Nếu có lý do thiết kế để chuyển đổi, cần dùng loại lỗi có ý nghĩa và giữ `cause`.

### Bẫy 5: “Retry mọi ngoại lệ một vài lần là ổn”

Retry có ích khi lỗi có khả năng tạm thời, thao tác được phép lặp và vẫn còn ngân sách thời gian. Retry `NumberFormatException` trên cùng chuỗi `"abc"` không khiến chuỗi trở thành số. Retry `IllegalStateException` khi chưa sửa trạng thái có thể chỉ tạo vòng lặp vô ích. Retry lệnh ghi có tác dụng phụ không có bảo vệ idempotency có thể nhân đôi kết quả.

### Bẫy 6: “`catch (Exception e)` là ranh giới khôi phục an toàn”

`catch (Exception e)` bắt cả phần lớn checked exception **và** `RuntimeException` vì quan hệ kế thừa. Khi dùng ở ranh giới hệ thống, phải tránh gộp lỗi lập trình với lỗi có thể dự kiến rồi áp chung cách tiếp tục. Nó cũng không bắt `Error`. Nên bắt loại cụ thể nơi có cách xử lý rõ ràng, và chỉ có xử lý tổng quát ở ranh giới đã định nghĩa chính sách lỗi.

### Bẫy 7: “InterruptedException là tín hiệu cứ retry tiếp”

`InterruptedException` là checked, nhưng thường biểu thị yêu cầu gián đoạn hoặc hủy công việc. Không nên vô điều kiện nuốt ngoại lệ rồi retry. Khi không thể chuyển tiếp trong hợp đồng hiện tại, một cách thường dùng là khôi phục cờ interrupt bằng `Thread.currentThread().interrupt()` và chấm dứt bước đang thực hiện theo chính sách của ứng dụng. Ngữ cảnh quản lý tác vụ quyết định hành động đúng.

## 7. Một quy trình quyết định ngắn khi thiết kế API

Có thể dùng trình tự sau khi bắt gặp thao tác có khả năng thất bại:

~~~text
Thao tác thất bại
       │
       ▼
Có cách đáp ứng mục tiêu an toàn, hợp đồng cho phép?
       ├── Có → Thực hiện fallback / nhập lại / retry có giới hạn
       │         └── Kiểm tra kết quả và trạng thái sau xử lý
       │
       └── Không
             ▼
        Tầng hiện tại có nghĩa vụ thông báo hay chuyển tiếp?
             ├── Có → Gắn ngữ cảnh, giữ cause, trả lỗi hoặc ném tiếp
             └── Không → Đưa lỗi đến ranh giới chịu trách nhiệm
~~~

Sơ đồ nói về **chính sách chạy thật**, độc lập với checked/unchecked. Sau khi chọn cách ứng xử, mới thực hiện cú pháp Java cần thiết: `try/catch`, `throws`, hoặc `throw` theo kiểu ngoại lệ và hợp đồng phương thức.

Nếu thiết kế **loại ngoại lệ riêng**:

- Chọn checked exception khi muốn các bên gọi Java bắt buộc *xét đến* tình huống thất bại trong hợp đồng API. Điều này không bảo đảm họ sẽ có cách phục hồi.
- Chọn unchecked exception khi hợp đồng không yêu cầu cơ chế xử lý bắt buộc ở mọi điểm gọi, ví dụ vi phạm tiền điều kiện, trạng thái, hoặc một loại lỗi miền theo quy ước của hệ thống.
- Ưu tiên loại cụ thể và thông điệp rõ ràng; mô tả trong JavaDoc khi API có tác động quan trọng. Không quyết định checked/unchecked chỉ dựa vào nhãn “lỗi bên ngoài” hay “lỗi lập trình”.

## 8. Tự kiểm tra kiến thức

1. `IOException` xảy ra khi đọc tệp. Vì sao cùng một kiểu ngoại lệ có thể phục hồi được ở màn hình chọn tệp nhưng không thể phục hồi ở giai đoạn khởi tạo bắt buộc?
2. `NumberFormatException` là unchecked. Người dùng nhập `"xyz"` vào trường tuổi. Bạn có thể bắt và yêu cầu nhập lại không? Trình biên dịch có buộc bạn bắt không?
3. Một phương thức bắt `IOException`, ghi log rồi trả `"OK"` dù chưa hoàn thành việc ghi dữ liệu. Đây có phải phục hồi hay không? Rủi ro gì?
4. Khi chuyển `IOException` thành `IllegalStateException`, ngoại lệ gốc nên được lưu ở đâu? Việc chuyển có giúp hoạt động thành công không?
5. Tại sao không nên retry một yêu cầu thanh toán chưa có cơ chế chống xử lý trùng, ngay cả khi lỗi mạng có vẻ tạm thời?
6. Với `InterruptedException`, tại sao “bắt rồi tiếp tục vô hạn” thường là một quyết định sai?
7. Phân biệt: “trình biên dịch bắt buộc xử lý” và “chương trình có thể khôi phục” trả lời hai câu hỏi nào?

**Gợi ý đáp án:** (1) Vì có hay không có phương án dự phòng và chính sách cho phép; (2) có thể bắt để nhập lại, compiler không bắt buộc; (3) không, đây là che giấu thất bại; (4) lưu trong `cause`, không tự sửa lỗi; (5) có thể tạo tác dụng phụ trùng; (6) bỏ qua ý nghĩa hủy/gián đoạn; (7) nghĩa vụ kiểu tại biên dịch so với khả năng tiếp tục đúng đắn khi chạy.

**Ghi nhớ:** *Checked/unchecked là đặc tính của kiểu ngoại lệ trong hệ thống kiểm tra biên dịch Java. Recoverability là đặc tính của tình huống, mục tiêu và chính sách xử lý tại một tầng cụ thể.* Đánh giá hai trục riêng rẽ giúp viết API rõ hợp đồng và xử lý lỗi không làm sai trạng thái ứng dụng.