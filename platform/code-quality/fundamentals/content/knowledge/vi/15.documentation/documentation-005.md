# Ví dụ sử dụng đúng và giới hạn của ví dụ

Tài liệu API thường có một đoạn mã ngắn cho biết “gọi phương thức này như thế nào”. Đoạn mã có thể biên dịch thành công, trả kết quả đúng trong tình huống minh họa nhưng vẫn khiến người đọc hiểu sai nếu nó không nêu rõ **đầu vào hợp lệ, kết quả mong đợi, lỗi có thể xảy ra, trách nhiệm dọn dẹp hoặc những tình huống chưa được bao phủ**. Ví dụ sử dụng là một phần của hợp đồng giao tiếp giữa người viết thư viện và người dùng thư viện, không chỉ là phần trang trí cho tài liệu.

Trong chương **Tài liệu** của module **CODE_QUALITY_FUNDAMENTALS**, mục tiêu là hiểu những thuộc tính làm mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Bài này tập trung vào hai nhiệm vụ đi cùng nhau: **viết ví dụ sử dụng đúng** và **công bố giới hạn của ví dụ** để tránh biến một cách dùng rút gọn thành khuyến nghị sai cho môi trường thực tế.

## 1. Ví dụ sử dụng là một lời giải thích có thể kiểm chứng

Một ví dụ tốt giúp người đọc trả lời:

1. **Giải quyết việc gì?** Bài toán và hành vi cần đạt được là gì?
2. **Áp dụng khi nào?** Những tiền điều kiện nào phải đúng?
3. **Dùng ra sao?** Cần khởi tạo, gọi và nhận kết quả bằng cách nào?
4. **Điều gì xảy ra?** Giá trị, ngoại lệ, trạng thái hoặc tác dụng phụ mong đợi là gì?
5. **Ai chịu trách nhiệm?** Người gọi hay thư viện phải đóng tài nguyên, quản lý giao dịch và xử lý lỗi?
6. **Giới hạn ở đâu?** Điều gì không được chứng minh, không được hỗ trợ hoặc chỉ đúng theo giả định?

Một đoạn mã chỉ minh họa **cú pháp lời gọi** có thể trả lời câu thứ ba nhưng bỏ trống năm câu còn lại. Vì vậy không nên đánh giá ví dụ bằng độ ngắn hoặc khả năng sao chép đơn thuần.

| Thành phần | Ví dụ đủ thông tin | Ví dụ thiếu thông tin |
| --- | --- | --- |
| Mục tiêu | “Tính phí vận chuyển cho đơn hàng theo ngưỡng giá trị” | Chỉ gọi một hàm có tên lạ |
| Đầu vào | Có đơn vị VND, miền hợp lệ và giá trị cụ thể | Dùng các biến x, y không rõ ý nghĩa |
| Kết quả | Ghi rõ phí được tính hoặc assertion tương ứng | In giá trị nhưng không nói giá trị đúng là gì |
| Lỗi | Nêu cách xử lý giá trị âm hoặc lỗi I/O | Chỉ minh họa đường thành công |
| Tác dụng phụ | Nói rõ có ghi DB, gửi thông điệp hay không | Bỏ qua hiệu ứng bên ngoài |
| Vòng đời | Nêu ai đóng stream, connection hoặc executor | Mở tài nguyên nhưng không đóng |
| Giới hạn | Nói rõ phạm vi, phiên bản, giả định và điều chưa kiểm chứng | Khiến người đọc tưởng ví dụ dùng nguyên trạng ở production |

### 1.1. “Đúng” nghĩa là đúng theo hợp đồng

Không có một ví dụ luôn đúng cho mọi sản phẩm. Ví dụ một công thức tính tiền có thể đúng với **đơn hàng bằng VND nguyên**, nhưng không phù hợp với tiền tệ có đơn vị thập phân hoặc chính sách làm tròn khác. Một ví dụ JDBC dùng **PreparedStatement** đúng để bind dữ liệu vẫn có thể thiếu kiểm tra **quyền truy cập** nếu được bê nguyên vào một API công khai.

Vì vậy, muốn nhận xét một ví dụ đúng hay sai, trước tiên phải biết **hợp đồng của API** và **những giả định của tình huống**.

## 2. Các mức độ hoàn chỉnh của ví dụ

Không phải mọi đoạn mã trong tài liệu đều cần là một ứng dụng có thể chạy độc lập. Điều quan trọng là **ghi nhãn trung thực**.

| Loại | Đặc điểm | Cách giới thiệu đúng |
| --- | --- | --- |
| **Ví dụ chạy độc lập** | Đủ lớp, import, lời gọi và điều kiện để biên dịch/chạy trong phiên bản đã nêu | “Tạo tệp X.java, dùng JDK Y, chạy với các lệnh sau” |
| **Đoạn mã sử dụng API** | Giả định API đã được khai báo và có dependency | “Giả sử đã có service và đối tượng đầu vào như mô tả...” |
| **Đoạn mã minh họa ý tưởng** | Lược bớt một phần triển khai để nhấn mạnh cơ chế | “Pseudocode/minh họa, không phải chương trình hoàn chỉnh” |
| **Ví dụ đối chiếu sai–đúng** | Nêu rõ cách dùng có vấn đề rồi đưa cách thay thế | “Không dùng bản đầu trong ứng dụng thật” |
| **Ví dụ kiểm thử** | Đặt đầu vào, kỳ vọng và assertion cạnh nhau | “Yêu cầu dependency kiểm thử và không tự chứng minh tích hợp” |

Một đoạn mã dùng các tên như **repository**, **sender**, **transactionManager** nhưng không có khai báo vẫn có thể rất hữu ích để giải thích kiến trúc. Tuy nhiên, không nên nói nó **có thể sao chép và chạy ngay**. Tương tự, ví dụ có dấu ba chấm thay nội dung thực thi cần được coi là minh họa, không phải mã Java hoàn chỉnh.

**Nguyên tắc:** Đừng bắt người đọc phải suy đoán đoạn mã là lời giải có thể dùng ngay hay chỉ là sơ đồ tư duy.

## 3. Một ví dụ Java có thể sử dụng và kiểm tra kết quả

Giả sử API tính phí vận chuyển có hợp đồng nghiệp vụ:

- Tổng tiền hàng được biểu diễn bằng **long** với đơn vị **VND**, không được âm.
- Khách thành viên được miễn phí vận chuyển nếu tổng tiền hàng **từ 300.000 VND trở lên**.
- Khách không phải thành viên được miễn phí từ **500.000 VND trở lên**.
- Các đơn hợp lệ còn lại trả **30.000 VND**.
- Phương thức chỉ tính toán, **không** truy vấn DB, không thanh toán và không thay đổi trạng thái bên ngoài.

### 3.1. Cài đặt minh họa của API

Tệp **ShippingFeePolicy.java**, chạy được với JDK 17 trở lên:

~~~java
public final class ShippingFeePolicy {
    private static final long MEMBER_FREE_FROM_VND = 300_000L;
    private static final long REGULAR_FREE_FROM_VND = 500_000L;
    private static final long STANDARD_FEE_VND = 30_000L;

    private ShippingFeePolicy() {
    }

    /**
     * Returns shipping fee in VND for the given merchandise subtotal.
     *
     * @param subtotalVnd subtotal in whole VND, must be non-negative
     * @param member whether the customer is a member
     * @return shipping fee in whole VND
     * @throws IllegalArgumentException if subtotalVnd is negative
     */
    public static long feeVnd(long subtotalVnd, boolean member) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }

        if (member && subtotalVnd >= MEMBER_FREE_FROM_VND) {
            return 0L;
        }

        if (subtotalVnd >= REGULAR_FREE_FROM_VND) {
            return 0L;
        }

        return STANDARD_FEE_VND;
    }
}
~~~

Ở đây, **tên phương thức có đơn vị** và phần Javadoc nêu rõ tiền điều kiện, kết quả và ngoại lệ. Hàm được thiết kế độc lập với môi trường, nên cùng đầu vào luôn có cùng kết quả.

### 3.2. Ví dụ sử dụng ở phía người gọi

Tệp **ShippingFeeExample.java** đặt cùng thư mục nguồn:

~~~java
public final class ShippingFeeExample {
    public static void main(String[] args) {
        long regularSmallOrder =
                ShippingFeePolicy.feeVnd(200_000L, false);
        long memberAtThreshold =
                ShippingFeePolicy.feeVnd(300_000L, true);
        long regularAtThreshold =
                ShippingFeePolicy.feeVnd(500_000L, false);

        System.out.println(regularSmallOrder);
        System.out.println(memberAtThreshold);
        System.out.println(regularAtThreshold);
    }
}
~~~

Khi hai tệp ở cùng thư mục và không khai báo package, có thể dùng:

~~~text
javac ShippingFeePolicy.java ShippingFeeExample.java
java ShippingFeeExample
~~~

Đầu ra mong đợi:

~~~text
30000
0
0
~~~

**Điểm mạnh của ví dụ:** người đọc có thể xác định rõ tệp nào cần tạo, cách gọi API, đơn vị của tham số và ba kết quả cụ thể phải quan sát. Ví dụ không cần tài khoản dịch vụ, cổng thanh toán, kết nối mạng hay dữ liệu ngoài.

**Giới hạn của ví dụ:** số tiền hàng là một giá trị đã được tính sẵn; ví dụ **không** giải thích tính thuế, chiết khấu, phí vận chuyển theo khu vực, trọng lượng, tiền tệ khác, hoặc trường hợp nhiều chính sách vận chuyển. Nó chỉ chứng minh việc gọi đúng một hàm theo những quy tắc vừa công bố.

### 3.3. Không dừng ở ba ví dụ “xanh”

Muốn minh họa đúng hợp đồng, cần đề cập ranh giới:

| Trường hợp | Lời gọi | Kết quả theo hợp đồng |
| --- | --- | --- |
| Khách thường dưới ngưỡng | feeVnd(499_999, false) | 30.000 VND |
| Khách thường đúng ngưỡng | feeVnd(500_000, false) | 0 VND |
| Khách thành viên dưới ngưỡng | feeVnd(299_999, true) | 30.000 VND |
| Khách thành viên đúng ngưỡng | feeVnd(300_000, true) | 0 VND |
| Tổng tiền hàng bằng 0 | feeVnd(0, false) | 30.000 VND |
| Tổng tiền hàng âm | feeVnd(-1, false) | IllegalArgumentException |

Các ngưỡng cần được viết thành số cụ thể; nếu tài liệu chỉ nói “đơn lớn được miễn phí” thì người đọc không biết trường hợp đúng **300.000** có được miễn hay không.

### 3.4. Ví dụ lỗi phải nêu cả cách phản hồi

~~~java
try {
    ShippingFeePolicy.feeVnd(-1L, false);
} catch (IllegalArgumentException invalidInput) {
    System.out.println("Không thể tính phí cho tổng tiền âm");
}
~~~

Đoạn này minh họa **bên gọi xử lý giá trị không hợp lệ**. Trong một API HTTP thật, việc chuyển lỗi thành mã phản hồi, thông điệp cho người dùng và log phải được quyết định ở tầng tiếp nhận yêu cầu. Không nên coi câu lệnh **System.out.println** ở đây là cách báo lỗi production.

## 4. Giới hạn phải được nói ngay cạnh ví dụ

Một ví dụ có thể được đọc bởi người mới, được chép vào một dự án khác hoặc được dùng làm mẫu trong code review. Nếu giới hạn chỉ nằm ở cuối một trang rất dài, người đọc có thể bỏ qua chúng và suy ra quá nhiều.

Một cách viết rõ ràng:

> Ví dụ này dùng số nguyên VND, áp dụng đúng hai ngưỡng miễn phí theo chính sách minh họa và chỉ tính toán trong bộ nhớ. Nó không xử lý thuế, đổi tiền tệ, truy cập DB, xử lý đồng thời hay cập nhật đơn hàng. Không dùng kết quả của ví dụ như một báo giá toàn bộ đơn hàng nếu hệ thống có các quy tắc khác.

Các loại giới hạn thường cần cân nhắc:

| Loại giới hạn | Câu hỏi nên trả lời |
| --- | --- |
| **Phiên bản** | Ví dụ chạy trên phiên bản Java, thư viện hoặc API nào? |
| **Giả định đầu vào** | Đơn vị, encoding, null, độ lớn, thời điểm hoặc dữ liệu nền là gì? |
| **Phạm vi chức năng** | Ví dụ thực hiện bước nào, chưa thực hiện bước nào? |
| **Lỗi** | Lỗi nào được trình bày và lỗi nào được lược bỏ? |
| **Tài nguyên** | Tệp, kết nối, executor hay stream được ai quản lý? |
| **Bảo mật** | Có cần xác thực, phân quyền, tham số hóa hoặc che dữ liệu nhạy cảm không? |
| **Đồng thời** | Ví dụ có giả định chạy một luồng hoặc dữ liệu không đổi trong lúc xử lý không? |
| **Hiệu năng** | Ví dụ có phù hợp với dữ liệu lớn hoặc lượng yêu cầu cao không? |
| **Tác dụng phụ** | Kết quả được commit, chỉ xếp hàng, hay mới ghi vào bộ nhớ? |
| **Tính tương thích** | Khi API hoặc chính sách thay đổi, điều gì khiến ví dụ phải cập nhật? |

Không cần lặp cả bảng ở mọi đoạn mã; chỉ nêu **những giới hạn có thể khiến người đọc hiểu sai hoặc dùng sai trong thực tế**.

## 5. Ví dụ tốt phải trung thực về phụ thuộc và khả năng chạy

### 5.1. Phân biệt JDK với thư viện ngoài

Ví dụ ở phần 3 dùng Java chuẩn nên không yêu cầu dependency ngoài JDK. Nhưng nếu tài liệu dùng **JUnit 5**, **Spring**, **Jackson**, **H2**, **JMH** hay **OWASP Java Encoder**, cần nêu rõ chúng **không phải thư viện có sẵn trong JDK** và cần cấu hình dependency tương ứng.

Đừng ghi “chỉ cần chạy Java” cho đoạn mã import một thư viện ngoài hoặc phụ thuộc một service chưa được tạo. Nếu đang minh họa ý tưởng ở mức kiến trúc, hãy nói rõ **đây là pseudocode hoặc mã rút gọn**.

### 5.2. Phân biệt giả định với bảo đảm

Ví dụ:

~~~java
Order order = repository.findById(orderId);
paymentGateway.charge(order.totalVnd());
repository.markPaid(orderId);
~~~

Đoạn này minh họa trình tự ba bước, nhưng **Order**, **repository** và **paymentGateway** là các thành phần giả định. Quan trọng hơn, nó **không bảo đảm tính nguyên tử** giữa thu tiền và lưu DB. Nếu thu tiền thành công rồi cập nhật DB thất bại, kết quả có thể bị cập nhật một phần.

Chú thích thích hợp:

> Đoạn mã chỉ minh họa thứ tự điều phối. Trong hệ thống thật cần xử lý mất kết nối, thanh toán có kết quả chưa xác định, idempotency và đối soát. Không coi ba lời gọi liên tiếp là một giao dịch nguyên tử.

Ngược lại, nói “ví dụ có thể làm mất tiền” mà không chỉ ra điểm lỗi cũng không giúp người đọc. **Giới hạn tốt phải cụ thể và liên quan trực tiếp đến cách dùng.**

### 5.3. Không khẳng định đã kiểm thử nếu chưa có bằng chứng

Một ví dụ có thể được người viết đánh giá là hợp lý nhưng chưa từng biên dịch. Tài liệu nên dùng từ ngữ chính xác:

- **“Mã minh họa”** khi đoạn mã được xây dựng để giải thích nhưng chưa có bằng chứng chạy thực.
- **“Đầu ra mong đợi”** khi số liệu được suy từ hợp đồng hoặc tính toán, không phải từ một lần chạy đã ghi nhận.
- **“Đã được chạy trong CI trên JDK 17”** chỉ khi thực sự có quy trình và kết quả kiểm chứng phù hợp.

Chỉ nói “đã được kiểm thử” nếu có thể truy ra **phiên bản mã, môi trường, thời điểm, bộ kiểm thử và kết quả thực tế**. Một đoạn tài liệu trông chuyên nghiệp không tạo ra bằng chứng kiểm thử.

## 6. Ví dụ xử lý tài nguyên: đúng cho một lượt dùng, không đúng cho mọi vòng đời

Tài liệu API thường hướng dẫn người đọc dùng **Files.lines**, **InputStream**, **Connection** hoặc **ExecutorService**. Những ví dụ này cần giải thích **ai đóng tài nguyên và khi nào**.

### 6.1. Đọc tệp theo luồng bằng try-with-resources

Giả sử cần đếm số dòng không trống trong một tệp UTF-8:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public final class TextFileExamples {
    public static long countNonBlankLines(Path file)
            throws IOException {
        try (Stream<String> lines =
                     Files.lines(file, StandardCharsets.UTF_8)) {
            return lines.filter(line -> !line.isBlank()).count();
        }
    }
}
~~~

Đoạn mã cho thấy:

- Tham số là một **Path** tới tệp mà bên gọi được phép đọc.
- Mã hóa đầu vào là **UTF-8**, không dựa vào charset mặc định.
- **Files.lines** tạo một Stream có tài nguyên nền cần đóng.
- **Try-with-resources** cố gắng đóng Stream cả khi pipeline xử lý thất bại.
- **IOException** khi mở tệp được truyền ra theo chữ ký.

**Giới hạn cần nêu:** đây là hàm đếm dòng không trống, không phải một parser CSV hoặc một hệ thống xử lý dữ liệu phân tán. Lỗi I/O có thể phát sinh **khi duyệt Stream**, đôi khi được bọc trong ngoại lệ unchecked theo API Stream; người gọi cần hiểu hợp đồng lỗi thực tế. Với dữ liệu cực lớn, cần đánh giá chi phí xử lý, thời gian, mã hóa và giới hạn tài nguyên.

Nếu ví dụ chuyển Stream ra ngoài phạm vi try rồi đọc ở nơi khác, Stream có thể đã bị đóng. Một ví dụ “trả Stream để bên gọi xử lý” phải **chuyển giao trách nhiệm close cho bên gọi** và nói rõ điều này trong tài liệu.

### 6.2. Kết nối DB: đóng lượt mượn, không đóng tài nguyên dùng chung

Ví dụ JDBC dùng connection pool:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

public final class UserLookup {
    private final DataSource dataSource;

    public UserLookup(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<String> findDisplayName(long userId)
            throws SQLException {
        if (userId <= 0) {
            throw new IllegalArgumentException("Invalid user ID");
        }

        String sql =
                "SELECT display_name FROM users WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement query =
                     connection.prepareStatement(sql)) {
            query.setLong(1, userId);

            try (ResultSet rows = query.executeQuery()) {
                if (!rows.next()) {
                    return Optional.empty();
                }
                return Optional.of(rows.getString("display_name"));
            }
        }
    }
}
~~~

Giả định rõ của ví dụ: bảng **users** tồn tại, cột **id** xác định duy nhất bản ghi, **display_name** không null, driver hỗ trợ kiểu dữ liệu tương ứng, và **DataSource** đã được cấu hình bởi ứng dụng.

**Đúng trong phạm vi ví dụ:** truy vấn bind **userId** như một giá trị; **ResultSet**, **PreparedStatement** và lượt mượn **Connection** được đóng khi phương thức kết thúc.

**Chưa được bảo đảm:** người gọi có quyền đọc người dùng có ID đó hay không; DB có sẵn không; kết nối có timeout phù hợp không; phương thức có nằm trong giao dịch rộng hơn không. Nếu ứng dụng dùng một transaction manager sở hữu connection, phải theo **hợp đồng quản lý giao dịch của framework** thay vì tùy tiện đóng một connection do framework quản lý.

Không nên biến một ví dụ đọc dữ liệu thành lời khuyên “mọi phương thức repository phải tự mở/đóng Connection” mà bỏ qua kiến trúc đang sử dụng.

## 7. Ví dụ bất đồng bộ: phải chỉ rõ khi nào hoàn tất

Một phương thức trả về **Future** hoặc **CompletableFuture** thường làm người đọc hiểu nhầm rằng công việc đã hoàn tất hoặc có thể hủy tức thì.

Ví dụ dùng Java chuẩn với executor do phương thức tạo riêng:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public final class FutureExample {
    public static void main(String[] args) throws Exception {
        ExecutorService executor =
                Executors.newSingleThreadExecutor();
        try {
            Future<String> future =
                    executor.submit(() -> "ready");

            try {
                String result =
                        future.get(1, TimeUnit.SECONDS);
                System.out.println(result);
            } catch (TimeoutException timeout) {
                future.cancel(true);
                System.out.println("Timed out while waiting");
            }
        } finally {
            executor.shutdownNow();
        }
    }
}
~~~

**Mục tiêu của ví dụ:** minh họa cách submit công việc, lấy kết quả có giới hạn thời gian chờ và đóng vòng đời executor do chính phương thức tạo.

**Giới hạn bắt buộc nêu:**

- **Future.get(timeout)** giới hạn **thời gian chờ của người gọi**, không tự hủy tác vụ.
- **Future.cancel(true)** chỉ cố gắng hủy/ngắt; tác vụ có thể không dừng ngay, nhất là khi I/O hoặc mã nền không phản hồi interruption.
- **shutdownNow()** yêu cầu dừng công việc và không bảo đảm mọi tác vụ đã kết thúc hay giải phóng tài nguyên tức thì.
- Kết quả thực tế phụ thuộc lịch chạy; **ready** là kết quả mong đợi nếu tác vụ kết thúc trong hạn. Không nên dùng một kết quả chưa được quan sát làm bằng chứng chắc chắn về hiệu năng.
- Ví dụ không xử lý tác dụng phụ bên ngoài như thanh toán hoặc gửi email; hủy một Future không hoàn tác những tác dụng phụ đã xảy ra.

Trong hệ thống thật, executor có thể được **dùng chung** và do ứng dụng sở hữu. Phương thức xử lý một request **không được tự shutdown executor dùng chung**. Một ví dụ ngắn về Future không thể thay thế thiết kế deadline, cancellation, retry và resource lifecycle cho toàn bộ dịch vụ.

## 8. Ví dụ an toàn phải tránh dạy thói quen nguy hiểm

Ví dụ “chỉ để cho dễ hiểu” dễ được sao chép sang mã production. Vì vậy không nên bỏ qua những cơ chế bảo mật cơ bản nếu thiếu chúng làm người đọc học sai cách dùng API.

### 8.1. Không ghép dữ liệu vào SQL

Một ví dụ nên tránh:

~~~java
// Không dùng cách này với giá trị đầu vào bên ngoài:
String sql = "SELECT id FROM users WHERE name = '"
        + userInput + "'";
~~~

Thay bằng bind parameter:

~~~java
String sql = "SELECT id FROM users WHERE name = ?";
try (PreparedStatement query =
             connection.prepareStatement(sql)) {
    query.setString(1, userInput);
    // Xử lý ResultSet trong phạm vi tương ứng.
}
~~~

Đoạn an toàn vẫn chỉ minh họa việc **truyền dữ liệu tách khỏi cấu trúc SQL**. Nó không xác nhận quyền truy cập hay độ đúng của toàn bộ truy vấn.

### 8.2. Không đặt bí mật thật trong ví dụ

Không đưa mật khẩu, API token, khóa riêng hoặc URL chứa bí mật thật vào tài liệu. Nếu ví dụ cần khóa truy cập, dùng **giá trị giả không có khả năng đăng nhập**, biến môi trường hoặc trình quản lý bí mật theo môi trường. Phải nói rõ biến nào người đọc cần cấu hình và **không nên ghi token vào log hoặc commit lên repository**.

### 8.3. Mẫu đơn giản không đồng nghĩa đầy đủ bảo mật

Một ví dụ đọc tệp bằng **Files.readString(path)** có thể đúng cú pháp nhưng chưa kiểm tra người dùng được phép đọc đường dẫn đó. Một ví dụ trả dữ liệu với **PreparedStatement** có thể tránh SQL injection nhưng vẫn thiếu ràng buộc tenant. Một ví dụ hiển thị văn bản trong HTML cần tránh dùng nội dung không đáng tin làm cấu trúc DOM.

Khi lược bớt bảo mật để tập trung vào cơ chế khác, tài liệu phải nêu **phần bảo mật nào đã được lược bỏ** và không được dán nhãn ví dụ là “production-ready”.

## 9. Ví dụ cần làm rõ cả trường hợp biên và lỗi

Một ví dụ sử dụng đủ tốt không nhất thiết trình bày hàng trăm ca kiểm thử. Nhưng nó nên chỉ ra **những biên quan trọng để tránh hiểu sai API**.

Với **ShippingFeePolicy.feeVnd**, hãy phân biệt:

- **Đầu vào bình thường:** đơn dưới ngưỡng phải trả phí.
- **Giá trị biên:** đúng ngưỡng miễn phí và ngay dưới ngưỡng.
- **Đầu vào không hợp lệ:** tổng tiền âm bị từ chối.
- **Dữ liệu bất thường nhưng hợp lệ:** tổng bằng 0 hoặc rất lớn trong giới hạn long.

Ví dụ kiểm thử JUnit 5 (dependency kiểm thử không nằm sẵn trong JDK):

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class ShippingFeePolicyTest {
    @Test
    void regularCustomerPaysBelowThreshold() {
        assertEquals(30_000L,
                ShippingFeePolicy.feeVnd(499_999L, false));
    }

    @Test
    void regularCustomerGetsFreeShippingAtThreshold() {
        assertEquals(0L,
                ShippingFeePolicy.feeVnd(500_000L, false));
    }

    @Test
    void memberGetsFreeShippingAtOwnThreshold() {
        assertEquals(0L,
                ShippingFeePolicy.feeVnd(300_000L, true));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> ShippingFeePolicy.feeVnd(-1L, false));
    }
}
~~~

Các assertion được suy ra từ **hợp đồng đã nêu**, không nên sao chép công thức triển khai để tự tạo kết quả mong đợi. Ví dụ kiểm thử này cung cấp bằng chứng cho **một hàm tính toán**, không chứng minh cả hệ thống bán hàng xử lý giao dịch, giảm giá hoặc tính tồn kho đúng.

## 10. Tài liệu minh họa khác tài liệu tham chiếu

Tài liệu thường có nhiều lớp:

| Loại tài liệu | Vai trò | Điều không nên giả định |
| --- | --- | --- |
| **Quick start** | Giúp hoàn thành tác vụ đầu tiên nhanh | Không bao phủ mọi lỗi và mọi cấu hình |
| **Ví dụ sử dụng** | Diễn đạt một cách dùng đúng trong ngữ cảnh xác định | Không phải giải pháp hoàn chỉnh cho mọi tình huống |
| **API reference/Javadoc** | Quy định tham số, kết quả, ngoại lệ, tác dụng phụ và hợp đồng | Không thay thế ví dụ theo quy trình nghiệp vụ |
| **Hướng dẫn vận hành** | Trình bày triển khai, cấu hình, bảo mật, backup, monitoring | Không tự xác nhận logic trong mã nguồn |
| **Kiểm thử có thể chạy** | Kiểm chứng một tập điều kiện và kết quả | Không phải chứng minh tuyệt đối cho mọi đầu vào |

Một ví dụ ngắn nên **dẫn người đọc tới hợp đồng và các giới hạn liên quan**, thay vì bắt nó kiêm luôn toàn bộ tài liệu hệ thống. Ngược lại, API reference chỉ có tên phương thức và vài định nghĩa chung chung cũng chưa đủ giúp người dùng chọn đúng cách dùng.

### 10.1. Một mẫu mô tả ngắn đặt cạnh ví dụ

~~~text
Tên ví dụ: Tính phí vận chuyển cơ bản

Mục tiêu:
  Tính phí với tổng tiền hàng VND nguyên và loại khách hàng.

Điều kiện:
  subtotalVnd >= 0; dữ liệu thuộc đúng chính sách vận chuyển này.

Cách dùng:
  Gọi ShippingFeePolicy.feeVnd(subtotalVnd, member).

Kết quả:
  Phí VND nguyên; 0 nếu đạt ngưỡng, 30000 nếu chưa đạt.

Lỗi:
  IllegalArgumentException khi tổng tiền hàng âm.

Tác dụng phụ:
  Không có I/O hoặc cập nhật trạng thái.

Giới hạn:
  Không bao gồm thuế, chiết khấu, nhiều loại tiền tệ hoặc giao dịch.

Môi trường:
  JDK 17+, ví dụ độc lập không yêu cầu thư viện ngoài.
~~~

Đây là mẫu **diễn giải hợp đồng**, không phải cấu hình mà mọi hệ thống bắt buộc dùng. Với API I/O, cần bổ sung thông tin về timeout, quyền truy cập, trách nhiệm đóng tài nguyên hoặc trạng thái sau lỗi.

## 11. Giữ ví dụ và hành vi thực tế không bị lệch nhau

Một ví dụ có thể đúng khi được viết lần đầu nhưng trở nên sai sau khi API thay đổi:

- Phương thức đổi tên hoặc chuyển từ trả giá trị sang trả **Future**.
- Đầu vào bắt buộc từ số nguyên chuyển sang một **value object**.
- Chính sách ngưỡng thay đổi từ **500.000** sang **600.000**.
- API bắt đầu ném ngoại lệ mới hoặc thay đổi chính sách retry.
- Framework thay đổi quyền sở hữu connection hoặc executor.
- Tên trường trong JSON hoặc schema DB đổi.

Quy trình bảo trì:

1. **Gắn ví dụ với phiên bản API hoặc chính sách** mà nó minh họa.
2. **Đặt đoạn mã quan trọng trong kiểm thử hoặc ví dụ được build tự động** khi điều kiện dự án cho phép.
3. **Dùng giá trị đầu ra cụ thể** để phát hiện thay đổi hành vi.
4. **Review ví dụ khi sửa API**, không chỉ review mã triển khai.
5. **Kiểm tra đường lỗi**, tài nguyên và bảo mật sau khi thay đổi.
6. **Cập nhật giới hạn** nếu một cơ chế trước đây chưa được hỗ trợ nay đã có, hoặc ngược lại.

Không phải mọi đoạn mã minh họa đều dễ đưa vào CI: đoạn pseudocode hoặc ví dụ cần tài nguyên ngoài có thể phải dùng môi trường giả lập và bước kiểm thử khác. Khi đó, hãy **ghi rõ mức độ kiểm chứng** thay vì im lặng để người đọc hiểu nhầm.

## 12. Checklist khi viết và review ví dụ

Hãy dùng các câu hỏi sau:

1. **Bài toán:** Có nói rõ ví dụ đang giúp người dùng thực hiện việc gì không?
2. **Tính đầy đủ:** Người đọc có biết phải khai báo/import/cấu hình gì để chạy không?
3. **Phiên bản:** Ví dụ dựa trên JDK hoặc thư viện nào?
4. **Đầu vào:** Đơn vị, phạm vi hợp lệ, null và các giả định có rõ không?
5. **Kết quả:** Đầu ra hoặc trạng thái mong đợi có thể kiểm chứng độc lập không?
6. **Lỗi:** Ngoại lệ, timeout và trường hợp thất bại có được mô tả đúng không?
7. **Tác dụng phụ:** Ví dụ có ghi dữ liệu, gửi thông điệp hoặc làm thay đổi trạng thái mà chưa nói tới không?
8. **Tài nguyên:** Ai đóng stream/connection, ai sở hữu executor, khi nào cần cleanup?
9. **Bảo mật:** Có bind tham số, kiểm tra quyền, bảo vệ bí mật hoặc mã hóa đầu ra phù hợp không?
10. **Đồng thời:** Ví dụ có giả định chỉ chạy một request hoặc không có tranh chấp dữ liệu không?
11. **Giới hạn:** Người đọc có biết điều gì chưa được giải quyết và không nên suy rộng không?
12. **Khả năng duy trì:** Có cách kiểm tra lại ví dụ khi API thay đổi không?

Một ví dụ **dài hơn đôi chút nhưng khai báo rõ hợp đồng** thường hữu ích hơn một đoạn rất ngắn khiến người đọc phải đoán các điều kiện quan trọng. Tuy nhiên, không cần chèn mọi chi tiết sản xuất vào từng ví dụ; nên giữ ví dụ tập trung và liên kết tới tài liệu chuyên sâu khi cần.

## 13. Những hiểu nhầm thường gặp

**“Có mã nguồn là đủ, không cần giải thích.”** Mã chỉ thể hiện một luồng thực thi; người đọc còn cần đầu ra, đầu vào hợp lệ và giới hạn.

**“Ví dụ chạy được là production-ready.”** Biên dịch được không chứng minh phân quyền, tính đúng khi nhiều request đồng thời, retry hoặc khả năng phục hồi sau lỗi.

**“Ví dụ càng ngắn càng tốt.”** Ngắn có ích khi giảm nhiễu, nhưng rút bỏ cleanup, validation hay mô tả tác dụng phụ có thể tạo thói quen sử dụng sai.

**“Cứ in giá trị là đã có kết quả mong đợi.”** Câu lệnh in chỉ là quan sát; tài liệu còn cần nói giá trị đúng là gì và tại sao.

**“Các trường hợp lỗi để người dùng tự xử lý.”** Không cần trình bày tất cả lỗi, nhưng các lỗi quan trọng phải được mô tả, nhất là khi chúng làm thay đổi trạng thái hoặc trách nhiệm dọn dẹp.

**“Một ví dụ đúng ở JDK mới nhất sẽ đúng ở mọi phiên bản.”** Cú pháp Java và hành vi thư viện có thể thay đổi; cần nói rõ môi trường mục tiêu.

**“Javadoc là đủ thay cho ví dụ.”** Javadoc định nghĩa hợp đồng, còn ví dụ làm rõ luồng sử dụng; hai loại tài liệu bổ trợ nhau.

**“Không cần cập nhật ví dụ vì mã thư viện đã có unit test.”** Ví dụ có thể sai tên API, thiếu dependency, hoặc mô tả kết quả cũ dù logic bên trong đã được kiểm thử.

## 14. Tình huống thực hành

Một nhóm viết tài liệu cho API xuất báo cáo như sau:

~~~java
// Giả sử service được tạo ở nơi khác.
var future = service.export(customerId);
System.out.println("Xuất báo cáo thành công");
~~~

Nhóm muốn người đọc dùng đoạn này cho chức năng xuất báo cáo theo yêu cầu, nhưng **export** thực sự gửi công việc vào executor và trả một **CompletableFuture<Path>**. Công việc có thể đọc DB, ghi tệp tạm, upload tệp và thất bại ở một bước bất kỳ.

Hãy trả lời:

1. Thông báo “thành công” ngay sau lời gọi có được bảo đảm không?
2. Cần mô tả rõ những trạng thái hoặc mốc hoàn thành nào?
3. Nếu người dùng yêu cầu hủy Future, có thể khẳng định đã xóa tệp tạm và không còn upload không?
4. Nếu xuất báo cáo cho khách hàng khác, kiểm tra quyền thuộc trách nhiệm nào?
5. Đoạn mã có cần giải thích **quyền sở hữu executor** và vòng đời tệp tạm không?
6. Nên ghi ví dụ là “chạy độc lập” hay “minh họa giả định đã có service”?
7. Hãy đề xuất một ví dụ ngắn có thể phân biệt **đã gửi công việc**, **thành công**, **thất bại** và giới hạn của việc hủy.

**Một cách viết trung thực hơn về luồng kết quả** (đoạn mã minh họa, giả định service và quyền truy cập đã được thiết lập):

~~~java
CompletableFuture<Path> result = service.export(customerId);
System.out.println("Đã gửi yêu cầu xuất báo cáo");

result.whenComplete((path, error) -> {
    if (error != null) {
        System.out.println("Tạo báo cáo thất bại");
        return;
    }
    System.out.println("Báo cáo đã sẵn sàng: " + path);
});
~~~

**Giới hạn của ví dụ sửa:** callback chỉ minh họa cách quan sát kết quả Future. Nó không định nghĩa thread chạy callback, cách chuyển lỗi sang người dùng, quyền đọc báo cáo, tính bền vững của tệp hay cơ chế hủy và cleanup. Nếu tiến trình kết thúc sớm, callback không tự bảo đảm được chạy tới cùng; hệ thống thực cần quản lý vòng đời của service và cách lưu kết quả.

**Gợi ý đối chiếu:** Lời gọi đầu có thể chỉ gửi yêu cầu xử lý, không chứng minh đã hoàn tất. Hủy Future không mặc nhiên dừng I/O hoặc hoàn tác những bước đã chạy. Cần mô tả điểm hoàn tất (tệp được tạo, upload xong hay link đã sẵn sàng), bảo vệ phân quyền, xác định bên sở hữu tệp/executor và kiểm thử các đường lỗi quan trọng. Ví dụ phải được dán nhãn **minh họa** vì phụ thuộc vào service, executor và hạ tầng chưa khai báo.

## 15. Ghi nhớ

- **Ví dụ sử dụng đúng** phải thể hiện mục tiêu, điều kiện đầu vào, cách gọi, kết quả mong đợi và những trách nhiệm liên quan.
- **Giới hạn của ví dụ** cho biết những giả định, môi trường và hành vi chưa được xử lý; chúng giúp người đọc không suy rộng một mẫu ngắn thành giải pháp production.
- Phải **phân biệt ví dụ chạy độc lập, đoạn mã dùng API, mã minh họa kiến trúc và ví dụ kiểm thử**.
- Với I/O, bất đồng bộ và tài nguyên, cần nói rõ **tác dụng phụ, lỗi, điểm hoàn thành, quyền sở hữu và trách nhiệm cleanup**.
- Ví dụ là một phần của tài liệu có thể thay đổi cùng API. **Kết quả và lời tuyên bố kiểm chứng phải có căn cứ**, không được biến đầu ra mong đợi thành kết quả đã chạy.
