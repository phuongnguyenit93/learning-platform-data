# Tài liệu hóa bằng @throws và điều kiện phát sinh

Một phương thức Java có thể thất bại theo nhiều cách: đầu vào sai, trạng thái đối tượng không cho phép thao tác, quy tắc nghiệp vụ bị vi phạm hoặc tài nguyên bên ngoài không khả dụng. Người sử dụng API cần biết **exception nào có ý nghĩa với họ, chính xác điều kiện nào gây ra exception và họ có thể làm gì tiếp theo**. Thẻ Javadoc `@throws` giúp mô tả hợp đồng này ngay cạnh chữ ký phương thức hoặc constructor.

Tài liệu tốt không chỉ liệt kê tên lớp exception. Nó liên kết **điều kiện phát sinh → loại lỗi → cách hiểu của caller**, đồng thời nhất quán với implementation và test. Đây là một phần thiết kế API ổn định, đặc biệt quan trọng với thư viện và public service dùng lại ở nhiều nơi.

## 1. Phân biệt ba khái niệm dễ nhầm

Trong Java, từ `throw`, `throws` và `@throws` xuất hiện gần nhau nhưng có ba vai trò khác nhau.

| Cú pháp | Vị trí | Vai trò |
| --- | --- | --- |
| `throw new SomeException(...)` | Thân phương thức hoặc constructor | **Ném** một exception ở thời điểm thực thi. |
| `throws SomeException` | Chữ ký phương thức hoặc constructor | **Khai báo** loại exception được phép truyền ra. Với checked exception, đây là một phần cơ chế kiểm tra ở thời điểm biên dịch. |
| `@throws SomeException ...` | Khối Javadoc `/** ... */` | **Mô tả** trường hợp ném exception cho người đọc tài liệu API; không thay đổi việc biên dịch hoặc tự tạo hành vi ném lỗi. |

Ví dụ minh họa cú pháp, chưa phải chương trình độc lập:

```java
/**
 * Tìm số phần tử trong trang.
 *
 * @param pageSize số phần tử yêu cầu
 * @return số phần tử được chấp nhận
 * @throws IllegalArgumentException nếu pageSize không dương
 */
public int validatePageSize(int pageSize) {
    if (pageSize <= 0) {
        throw new IllegalArgumentException("pageSize phải dương");
    }
    return pageSize;
}
```

`IllegalArgumentException` kế thừa `RuntimeException` nên thuộc loại **unchecked**. Phương thức không cần khai báo `throws IllegalArgumentException` để biên dịch, nhưng vẫn có lý do rõ ràng để viết `@throws` vì người gọi cần biết ràng buộc đầu vào.

Ngược lại, với checked exception như `IOException` (không phải subtype của `RuntimeException`), phương thức ném hoặc để exception đó truyền ra thường phải khai báo `throws IOException` hoặc xử lý bằng `catch` theo quy tắc compile-time. **Thẻ `@throws` không thay thế được khai báo `throws`**.

## 2. Cú pháp và ý nghĩa của @throws

Một thẻ Javadoc chuẩn có dạng:

```java
/**
 * ...
 * @throws ExceptionType điều kiện chính xác làm exception phát sinh
 */
```

`ExceptionType` là tên lớp exception mà Javadoc có thể phân giải từ ngữ cảnh import/package; nên sử dụng kiểu mà API thực sự công khai. Phần mô tả đi sau cần chỉ ra **tình huống quan sát được**, thay vì chỉ lặp lại “when an exception occurs”.

Cùng một phương thức có thể có nhiều thẻ `@throws` cho các loại lỗi khác nhau:

```java
/**
 * @throws IllegalArgumentException nếu mã đơn hàng không hợp lệ
 * @throws IllegalStateException nếu phiên làm việc đã đóng
 * @throws OrderNotFoundException nếu không tìm thấy đơn hàng
 */
```

Đây là đoạn Javadoc minh họa, với `OrderNotFoundException` giả định là kiểu exception của ứng dụng; chưa phải ví dụ Java đầy đủ.

`@exception` là bí danh được công cụ Javadoc chấp nhận cho `@throws`. Trong code mới, dùng nhất quán `@throws` giúp người đọc dễ nhận diện hơn.

Đối với toán tử `<` hoặc `>` trong văn bản Javadoc, đặt biểu thức trong `{@code ...}` để công cụ sinh tài liệu hiển thị đúng ký tự đặc biệt. Ví dụ:

```java
/**
 * @param amount lượng yêu cầu
 * @throws IllegalArgumentException nếu {@code amount <= 0}
 */
```

Nếu cần trỏ đến một kiểu Java trong câu văn, có thể dùng `{@link IllegalArgumentException}`. Javadoc phân tích các thẻ inline này, tạo phần trình bày code/link thích hợp trong HTML. Khối Markdown đang đọc là nội dung giảng dạy; những thẻ `{@code}` và `{@link}` có ý nghĩa đặc biệt **bên trong comment Javadoc của mã Java**.

## 3. “Điều kiện phát sinh” phải cụ thể đến đâu?

Mô tả tốt trả lời các câu hỏi: **đầu vào hoặc trạng thái nào làm lỗi xảy ra, lỗi có thuộc trách nhiệm caller hay hạ tầng, và ngoại lệ đó được bảo đảm trong hợp đồng không?**

So sánh:

| Mô tả yếu | Mô tả hữu ích |
| --- | --- |
| “Ném `IllegalArgumentException` khi đối số sai.” | “Ném `IllegalArgumentException` nếu `quantity <= 0`.” |
| “Ném `IllegalStateException` khi trạng thái không đúng.” | “Ném `IllegalStateException` nếu gọi `send()` sau `close()`.” |
| “Ném `NoSuchElementException` nếu không có phần tử.” | “Ném `NoSuchElementException` nếu bộ lặp đã hết phần tử và vẫn gọi `next()`.” |
| “Ném `IOException` nếu có lỗi.” | “Ném `IOException` nếu không thể đọc nội dung tệp do lỗi I/O.” |
| “Ném `QuotaExceededException` khi thất bại.” | “Ném `QuotaExceededException` nếu số bản ghi yêu cầu vượt hạn mức của tài khoản ở thời điểm gọi.” |

Không phải lúc nào cũng xác định được chính xác nguyên nhân sâu bên trong. Với `IOException`, tài liệu có thể nói “nếu xảy ra lỗi I/O khi đọc” vì đây là abstraction đủ rộng; không nên cam kết từng lỗi hệ điều hành hoặc từng subtype do implementation tình cờ ném.

Khi lỗi phụ thuộc vào trạng thái thay đổi theo thời gian, nêu thời điểm áp dụng quy tắc. Ví dụ “nếu hạn mức còn lại **ở thời điểm xử lý** không đủ” chính xác hơn “nếu tài khoản có hạn mức thấp”, bởi caller không kiểm soát được giao dịch đồng thời.

Nếu có nhiều điều kiện, có thể ghi rõ chúng trong một thẻ khi cùng một hành động khắc phục:

```java
/**
 * @throws IllegalArgumentException nếu tên rỗng hoặc độ dài tên
 *         vượt giới hạn 100 ký tự
 */
```

Nếu các điều kiện dẫn đến **cách phục hồi khác nhau**, cân nhắc exception hoặc mã lỗi riêng thay vì một mô tả quá rộng.

## 4. Ví dụ hoàn chỉnh Java 17: cả checked và unchecked exception

Ví dụ thiết kế `ReservationService.reserve(int)` với hai điều kiện rõ ràng:

- Số lượng không dương là lỗi đối số và ném `IllegalArgumentException` (unchecked).
- Số lượng lớn hơn giới hạn của ví dụ là lỗi quy tắc nghiệp vụ và ném `ReservationLimitException` (checked).

API dùng `@param`, `@return` và `@throws` để diễn đạt cả đầu vào, kết quả và điều kiện thất bại. File dưới đây độc lập, có thể biên dịch và chạy bằng Java 17+.

Tạo file `ThrowsDocumentationDemo.java`:

```java
/**
 * Minh họa hợp đồng exception qua thẻ Javadoc @throws.
 */
public class ThrowsDocumentationDemo {

    /**
     * Lỗi checked khi yêu cầu vượt giới hạn đặt chỗ.
     */
    public static final class ReservationLimitException extends Exception {
        /**
         * @param message mô tả lỗi nghiệp vụ
         */
        public ReservationLimitException(String message) {
            super(message);
        }
    }

    /**
     * Dịch vụ đặt chỗ đơn giản, không truy cập cơ sở dữ liệu.
     */
    public static final class ReservationService {

        private static final int MAX_PER_REQUEST = 5;

        /**
         * Chấp nhận yêu cầu đặt chỗ với số lượng hợp lệ.
         *
         * @param quantity số chỗ cần đặt, phải lớn hơn 0
         * @return thông báo xác nhận số chỗ
         * @throws IllegalArgumentException nếu {@code quantity <= 0}
         * @throws ReservationLimitException nếu
         *         {@code quantity > MAX_PER_REQUEST}
         */
        public String reserve(int quantity) throws ReservationLimitException {
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                    "quantity phải lớn hơn 0"
                );
            }
            if (quantity > MAX_PER_REQUEST) {
                throw new ReservationLimitException(
                    "Tối đa 5 chỗ mỗi yêu cầu"
                );
            }
            return "Đã đặt " + quantity + " chỗ";
        }
    }

    /**
     * Chạy ba tình huống để quan sát hợp đồng đã mô tả.
     *
     * @param args tham số dòng lệnh, không sử dụng
     * @throws ReservationLimitException nếu yêu cầu hợp lệ ở ví dụ
     *         bất ngờ vượt giới hạn; sẽ được truyền ra main
     */
    public static void main(String[] args)
            throws ReservationLimitException {
        ReservationService service = new ReservationService();

        System.out.println(service.reserve(2));

        try {
            service.reserve(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("INPUT: " + ex.getMessage());
        }

        try {
            service.reserve(7);
        } catch (ReservationLimitException ex) {
            System.out.println("LIMIT: " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ThrowsDocumentationDemo.java
java ThrowsDocumentationDemo
```

Kết quả chuẩn:

```text
Đã đặt 2 chỗ
INPUT: quantity phải lớn hơn 0
LIMIT: Tối đa 5 chỗ mỗi yêu cầu
```

Các điểm cần đối chiếu với hợp đồng:

1. `reserve(2)` hợp lệ vì `0 < 2 <= 5`, nên trả về thông báo xác nhận.
2. `reserve(0)` gặp điều kiện `quantity <= 0` đầu tiên, ném `IllegalArgumentException`; caller bắt unchecked exception để phản hồi lỗi đầu vào.
3. `reserve(7)` vượt `MAX_PER_REQUEST`, ném `ReservationLimitException`; caller bắt checked exception theo quyết định xử lý nghiệp vụ.
4. `reserve` khai báo `throws ReservationLimitException` để thỏa quy tắc Java cho checked exception; dù không khai báo `throws IllegalArgumentException`, Javadoc vẫn mô tả unchecked exception đó.
5. `main` khai báo `throws ReservationLimitException` vì lời gọi `reserve(2)` nằm ngoài `try/catch`. Trong ví dụ, số lượng `2` không thể gây lỗi giới hạn theo implementation hiện tại; khai báo vẫn hợp lệ và cho thấy compiler kiểm tra exception theo **kiểu và luồng mã**, không chứng minh điều kiện runtime luôn xảy ra.
6. Giới hạn `5` là quy tắc **được cố ý chọn riêng cho ví dụ**. Nếu public API thực sử dụng hạn mức cấu hình hoặc thay đổi theo tài khoản, Javadoc phải mô tả chính xác quy tắc thực tế.

Có thể tạo HTML Javadoc cho file:

```bash
javadoc -encoding UTF-8 -charset UTF-8 -d api-docs ThrowsDocumentationDemo.java
```

Mở `api-docs/index.html` để xem trang tài liệu. Trong tài liệu của `ReservationService.reserve`, phần **Throws** sẽ gồm hai exception và mô tả điều kiện tương ứng. Lệnh `javadoc` có thể phát cảnh báo ở những nơi công cụ yêu cầu thêm mô tả; sự tồn tại của cảnh báo (nếu có) không tự thay đổi runtime behavior.

## 5. @throws không phải là cơ chế kiểm tra hợp đồng tại runtime

Công cụ biên dịch và JVM **không đọc câu mô tả trong `@throws` để kiểm tra điều kiện**. Viết:

```java
/**
 * @throws IllegalArgumentException nếu số lượng nhỏ hơn 0
 */
```

không làm Java tự ném exception khi caller truyền số âm. Người triển khai vẫn phải kiểm tra điều kiện hoặc dựa vào hành vi được bảo đảm bởi API được gọi.

Do đó, tài liệu có thể **sai hoặc lỗi thời** so với code. Những trường hợp hay gặp:

- Comment hứa “ném khi `quantity < 0`” nhưng code kiểm tra `quantity <= 0`.
- Comment ghi “tệp không tồn tại” cho mọi `IOException`, dù thực tế còn có lỗi quyền truy cập và lỗi đọc.
- Comment ghi “đã đóng” nhưng implementation còn cho phép một số thao tác sau `close()`.
- Code thay đổi thứ tự validation khiến một đầu vào vi phạm nhiều quy tắc nhận exception khác trước.

Cần đối chiếu tài liệu với logic và test khi thay đổi điều kiện. Với hợp đồng public có client bên ngoài, thay đổi loại exception hoặc điều kiện ném có thể ảnh hưởng khả năng tương thích ngay cả khi chữ ký Java giữ nguyên.

## 6. Nên tài liệu hóa exception nào?

Với **checked exception**, tài liệu `@throws` thường cần giải thích loại đã khai báo và điều kiện khiến nó truyền ra. Chữ ký `throws IOException` chỉ cho biết có khả năng lỗi I/O; người gọi vẫn cần biết thao tác I/O nào thất bại.

Với **unchecked exception**, không cần ghi toàn bộ `RuntimeException` có thể phát sinh do bug. Nên ưu tiên loại được **cố ý định nghĩa là một phần hành vi của API**:

- `IllegalArgumentException` khi caller vi phạm precondition được chỉ rõ.
- `NullPointerException` khi tham số bắt buộc non-null bị truyền `null`, nếu đây là lựa chọn thiết kế và nhất quán với hợp đồng.
- `IllegalStateException` khi đối tượng ở trạng thái cấm thao tác.
- `UnsupportedOperationException` khi một thao tác tùy chọn không được implementation hỗ trợ.
- Exception miền nghiệp vụ để caller phân biệt lỗi có thể phục hồi.

Không phải mọi `NullPointerException` bất ngờ đều đáng ghi trong `@throws`. NPE do lỗi lập trình nội bộ không phải một điều kiện hữu ích hay lời hứa hành vi dành cho caller. Tương tự, không hứa mọi tên exception do thư viện phụ thuộc ném nếu chúng là chi tiết triển khai mà API muốn che giấu.

### Các exception bọc và truyền tiếp

Nếu API bắt `SQLException` và cố ý chuyển thành `RepositoryUnavailableException`, tài liệu public nên mô tả exception **sau khi chuyển nghĩa** và tình huống có ý nghĩa với caller. Có thể giữ exception gốc làm `cause` để chẩn đoán, nhưng không cần liệt kê subtype của driver như một hợp đồng public.

Ngược lại, nếu API công khai `IOException` như một phần abstraction đọc file, có thể viết `@throws IOException` mà không cần tạo exception tự định nghĩa. Mục tiêu là đúng ranh giới API, không phải thay tất cả ngoại lệ JDK bằng loại mới.

## 7. Viết điều kiện đủ rõ cho người gọi hành động

Một cách thực tế là lập bảng trước khi viết Javadoc:

| Điều kiện có thể quan sát | Kiểu exception public | Người gọi có thể làm gì? |
| --- | --- | --- |
| `quantity <= 0` | `IllegalArgumentException` | Sửa tham số trước khi gọi lại. |
| `quantity > limit` | `ReservationLimitException` | Giảm số lượng hoặc thay đổi quy trình đặt chỗ. |
| Gọi `send()` sau khi `close()` | `IllegalStateException` | Tạo đối tượng/phiên mới theo contract. |
| Không tìm thấy đối tượng với ID hợp lệ | `ResourceNotFoundException` | Kiểm tra ID hoặc thông báo không tìm thấy. |
| Đọc stream bị lỗi I/O | `IOException` | Xử lý lỗi đọc, xem xét retry phù hợp. |

Bảng là công cụ suy nghĩ, không nhất thiết phải lặp nguyên trong Javadoc. Khi viết thẻ `@throws`, chọn câu ngắn nêu **điều kiện chính**; giải thích retry, giao dịch, trạng thái sau lỗi hoặc cách phục hồi trong phần mô tả dài nếu những điều ấy quan trọng.

Một ví dụ Javadoc **minh họa chữ ký API**, không phải chương trình hoàn chỉnh:

```java
/**
 * Gửi gói tin qua phiên đang mở.
 *
 * <p>Thao tác không tự thử lại khi truyền thất bại.
 *
 * @param payload dữ liệu cần gửi, không được null
 * @throws NullPointerException nếu {@code payload == null}
 * @throws IllegalStateException nếu phiên đã đóng
 * @throws IOException nếu gặp lỗi I/O trong khi gửi
 */
public void send(byte[] payload) throws IOException;
```

Ví dụ có thân chữ ký kết thúc bằng `;` như khai báo trong interface; khi đưa vào source code độc lập phải đặt trong interface hoặc khai báo abstract method phù hợp. Các mô tả ở đây là **hợp đồng giả định của interface đó**, không phải khẳng định chung cho mọi API gửi dữ liệu.

Chú ý: `IOException` không tự có nghĩa là gửi thất bại hoàn toàn hoặc chưa có byte nào đến nơi. Nếu caller cần biết liệu có thể thử lại an toàn, API phải nói rõ thêm về khả năng gửi một phần hoặc idempotency.

## 8. Khi một lời gọi vi phạm nhiều điều kiện

Giả sử phương thức `update(record, token)` vừa nhận `record == null`, vừa được gọi khi dịch vụ đã đóng. Nếu code hiện tại kiểm tra `record` trước, caller có thể thấy `NullPointerException`; nếu kiểm tra trạng thái trước, caller có thể thấy `IllegalStateException`.

Không nên hứa thứ tự ưu tiên của lỗi trừ khi nó thực sự cần thiết cho người gọi. Nếu thứ tự được bảo đảm, có thể ghi rõ:

> Kiểm tra đối số được thực hiện trước kiểm tra trạng thái phiên; nếu cả hai đều sai, phương thức báo lỗi đối số.

Nếu không bảo đảm, tài liệu nên nêu điều kiện riêng cho từng loại và tránh khẳng định một thứ tự không được kiểm soát. Khi đổi thứ tự validation, test và Javadoc cần được xem lại.

Với thao tác nhiều bước, cũng phải cân nhắc **thời điểm** lỗi có thể xảy ra. Nếu validation thành công nhưng I/O thất bại, caller cần biết phương thức có thể đã cập nhật một phần trạng thái hay không. `@throws` mô tả điều kiện ném; đoạn mô tả chính nên chứa ràng buộc về trạng thái sau thất bại.

## 9. @throws ở interface, lớp triển khai và phương thức override

Đối với API có interface hoặc base class, hợp đồng lỗi nên đặt ở **điểm người gọi thực sự phụ thuộc**. Nếu caller biết đối tượng qua interface, Javadoc của interface là nơi thích hợp để mô tả loại lỗi và điều kiện mà mọi implementation phải tuân thủ.

Ví dụ minh họa cấu trúc, các class cụ thể không được khai báo đầy đủ ở đây:

```java
public interface Storage {
    /**
     * Đọc tài nguyên theo khóa.
     *
     * @param key khóa không được null
     * @return nội dung tài nguyên
     * @throws NullPointerException nếu {@code key == null}
     * @throws IOException nếu không thể đọc do lỗi I/O
     */
    byte[] read(String key) throws IOException;
}
```

Một implementation có thể dùng cơ chế lưu trữ khác mà vẫn đáp ứng hợp đồng này. Khi override:

- Java **không cho phép** phương thức override mở rộng danh sách checked exception thành checked exception không tương thích với `throws` của phương thức cha. Ví dụ implementation không thể tự thêm `throws SQLException` vào `read` khi interface chỉ khai báo `throws IOException` và `SQLException` không là subtype của `IOException`.
- Java **cho phép** phương thức override ném unchecked exception không có trong `throws`; song hành vi mới vẫn phải phù hợp hợp đồng mà caller được hứa. “Compiler cho phép” không đồng nghĩa với “thiết kế tương thích”.
- Javadoc hỗ trợ kế thừa tài liệu của phương thức được override; `{@inheritDoc}` có thể được dùng khi thích hợp để lấy nội dung đã có. Cần xem kết quả HTML và bổ sung mô tả cho ràng buộc thật sự khác biệt hoặc riêng biệt của implementation, tránh copy tài liệu rồi để lệch.
- Nếu implementation thực sự không đáp ứng một lời hứa hành vi ở interface, sửa thiết kế hoặc làm rõ abstraction; đừng chỉ thêm `@throws` để hợp thức hóa việc phá contract.

Constructor cũng có thể dùng `@throws` để nêu điều kiện khởi tạo thất bại (ví dụ đường dẫn không tồn tại, tham số cấu hình thiếu). Đảm bảo tài liệu phản ánh lỗi thực sự truyền đến caller, không chỉ lỗi xảy ra bên trong.

## 10. Phân biệt Javadoc với tài liệu về xử lý lỗi toàn hệ thống

Thẻ `@throws` thích hợp cho **hợp đồng của từng phương thức**. Những vấn đề lớn hơn có thể cần mô tả ở cấp type, module hoặc API guide:

- Phân loại lỗi thống nhất trong toàn thư viện; mã lỗi hoặc subclass stable.
- Chính sách retry, backoff, idempotency và trạng thái sau lỗi.
- Hành vi rollback hoặc side effect trước khi exception truyền ra.
- Quy tắc xử lý interrupt/cancellation ở API concurrent.
- Biên giới bảo mật: message gửi cho client không được chứa token, SQL hay stack trace.

Một Javadoc như `@throws IOException if an I/O error occurs` có thể hoàn toàn hợp lý cho đọc stream, nhưng không đủ làm tài liệu cho giao dịch upload nhiều phần có tính nhất quán và khả năng retry phức tạp.

Ngược lại, đừng biến mỗi thẻ `@throws` thành một đoạn văn dài mô tả lại toàn bộ kiến trúc. Giữ phần điều kiện ngắn, bổ sung link hoặc phần diễn giải khi người gọi cần.

## 11. Kiểm tra Javadoc và hành vi cùng nhau

### 11.1. Kiểm tra bằng công cụ

Có thể biên dịch source, chạy test và sinh Javadoc như hai loại kiểm chứng khác nhau:

```bash
javac -encoding UTF-8 ThrowsDocumentationDemo.java
java ThrowsDocumentationDemo
javadoc -encoding UTF-8 -charset UTF-8 -d api-docs ThrowsDocumentationDemo.java
```

`javac` xác nhận mã hợp lệ về mặt Java và kiểm tra checked exception. `javadoc` phân tích tài liệu, cố gắng phân giải `@throws` và tạo HTML. Một số lựa chọn doclint giúp phát hiện lỗi về cú pháp tài liệu, tham số hoặc tham chiếu; tuy vậy, **không có công cụ nào tự chứng minh rằng câu “nếu quantity <= 0” đúng với tất cả đường chạy**.

### 11.2. Kiểm tra bằng test tình huống

Đối với mỗi dòng `@throws` quan trọng, nên có test ít nhất cho điều kiện gây lỗi và một trường hợp biên hợp lệ. Ví dụ cho `reserve`:

| Input | Kỳ vọng |
| --- | --- |
| `quantity = 0` | `IllegalArgumentException` |
| `quantity = -1` | `IllegalArgumentException` |
| `quantity = 1` | Trả kết quả thành công |
| `quantity = 5` | Trả kết quả thành công |
| `quantity = 6` | `ReservationLimitException` |

Tập test này kiểm tra đúng **ranh giới `0` và `5`** mà Javadoc cam kết; không cần assert stack trace hoặc message của dependency phụ thuộc bên ngoài. Nếu message public được tuyên bố là hợp đồng, lúc đó mới kiểm tra chuỗi hoặc mã lỗi có chủ đích.

Với API nhiều trạng thái, test thêm `open → close → send`; với lỗi I/O, dùng fake hoặc mock để kích hoạt trường hợp được mô tả. Nếu phương thức có nhiều nhánh lỗi, test nên phản ánh các nhánh có thể quan sát thay vì chỉ độ phủ dòng mã.

### 11.3. Checklist review trước khi phát hành

- Kiểu exception ghi trong `@throws` có thực sự được phương thức ném hoặc truyền ra theo hợp đồng dự kiến?
- Những checked exception trong `throws` đã được giải thích đủ để caller hiểu vì sao chúng xảy ra chưa?
- Các unchecked exception do precondition và trạng thái API cố ý quy định đã được mô tả chưa?
- Các điều kiện ranh giới (`null`, rỗng, âm, bằng giới hạn, vượt giới hạn, đã đóng) có chính xác không?
- Có tên class, mã lỗi, message hoặc chi tiết implementation vô tình thành public contract không?
- Nếu có override, Javadoc của interface/base class có nhất quán với implementation không?
- Nếu đổi logic validation hoặc dependency, đã cập nhật tài liệu và test tương ứng chưa?

## 12. Những lỗi thường gặp và cách sửa

**Chỉ viết “if an error occurs”.** Câu này không hướng dẫn caller. Hãy mô tả loại thất bại và trạng thái/đầu vào kích hoạt; với I/O rộng, có thể dùng câu “nếu xảy ra lỗi I/O khi đọc dữ liệu”.

**Ghi `@throws` nhưng không khai báo checked exception trong `throws`.** Comment không ảnh hưởng đến kiểm tra của compiler. Phải bắt hoặc khai báo checked exception theo luật Java.

**Không tài liệu hóa unchecked exception là một phần precondition.** Những điều kiện như `size <= 0` hay “gọi sau close” có thể quan trọng hơn lỗi checked hiếm gặp. Ghi `@throws` cho hành vi được thiết kế có chủ đích.

**Liệt kê mọi exception từ các lời gọi sâu bên trong.** Điều này dễ biến chi tiết triển khai thành hợp đồng. Tài liệu hóa lỗi public có ý nghĩa; translation ở boundary cần rõ ràng nếu implementation thay đổi.

**Mô tả khác với điều kiện thực tế.** Ví dụ comment nói “nhỏ hơn 0” nhưng code nói “nhỏ hơn hoặc bằng 0”. Đọc lại toán tử, điều kiện biên và thứ tự kiểm tra; dùng test cho từng biên.

**Nhầm `@return` với `@throws`.** `@return` mô tả kết quả khi hoàn thành bình thường, còn `@throws` mô tả đường thất bại. Với API trả sentinel (`null`, empty, Optional) thay vì ném lỗi, tài liệu phải nhất quán với lựa chọn đó.

**Hứa điều kiện phụ thuộc lịch trình hoặc implementation.** Ví dụ khẳng định timeout luôn an toàn để retry hoặc exception chỉ xảy ra trước khi ghi dữ liệu. Chỉ hứa khi có cơ chế bảo đảm; cần mô tả side effect và trạng thái sau lỗi nếu caller dựa vào chúng.

**Dùng tên kiểu exception không phân giải được trong Javadoc.** Kiểm tra import/package và chạy `javadoc` để phát hiện lỗi tham chiếu. Nếu code trong ví dụ giả định một kiểu ứng dụng chưa khai báo, ghi rõ nó là đoạn minh họa.

## 13. Bài tập áp dụng

Xét một API giả định `SessionCache.get(String key)` có yêu cầu: `key` phải non-null, cache phải đang mở, nếu không có phần tử thì trả `Optional.empty()`, còn nếu backend không thể truy cập thì ném `CacheUnavailableException`.

Hãy phác thảo Javadoc bằng `@param`, `@return`, `@throws` cho ba lỗi có thể quan sát: null key, cache đã đóng, backend không sẵn sàng. Đồng thời tự trả lời: **cache miss** có nên có một thẻ `@throws` không?

Đáp án tham khảo **chỉ là chữ ký minh họa; `CacheUnavailableException` và implementation chưa được định nghĩa**:

```java
/**
 * Tra cứu phần tử theo khóa.
 *
 * @param key khóa tra cứu, không được null
 * @return Optional chứa giá trị nếu tìm thấy; Optional.empty()
 *         nếu khóa hợp lệ nhưng không có dữ liệu
 * @throws NullPointerException nếu {@code key == null}
 * @throws IllegalStateException nếu cache đã đóng
 * @throws CacheUnavailableException nếu backend không thể phục vụ tra cứu
 */
public Optional<String> get(String key)
        throws CacheUnavailableException;
```

Nếu cache miss được thiết kế là kết quả `Optional.empty()` thì đó **không phải exception** và cần mô tả ở `@return`, không đưa vào `@throws`. Đây là ví dụ về việc quyết định hợp đồng thành công/thất bại trước khi viết tài liệu.

Điểm cần nhớ: **`@throws` mô tả lời hứa có thể kiểm chứng về điều kiện exception truyền đến caller**. Để Javadoc đáng tin, nó phải đồng bộ với chữ ký `throws`, điều kiện `throw` trong implementation, hợp đồng ở interface/base class và các test cho trường hợp biên.