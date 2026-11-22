# Đánh đổi tối ưu hóa với độ rõ ràng và tính đúng đắn

Trong chương **Hiệu năng và tài nguyên** của module **CODE_QUALITY_FUNDAMENTALS**, chúng ta xem xét một tình huống xảy ra thường xuyên khi phát triển phần mềm: **một thay đổi làm chương trình chạy nhanh hơn nhưng có thể khiến mã khó hiểu, khó kiểm thử hoặc không còn giữ nguyên hành vi**.

Mục tiêu của **CODE_QUALITY_FUNDAMENTALS** là hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Hiệu năng là một phần của chất lượng: phản hồi chậm hoặc sử dụng tài nguyên quá mức có thể làm hệ thống không đáp ứng yêu cầu. Nhưng hiệu năng không đứng riêng lẻ. Một phép tối ưu khiến số tiền tính sai, mất bản ghi hoặc khiến người bảo trì không thể sửa lỗi một cách an toàn **không phải một cải thiện tổng thể**.

> **Tối ưu hóa có giá trị khi giải quyết được một vấn đề hiệu năng đã được xác định, với bằng chứng đo đạc phù hợp, trong khi vẫn bảo vệ hợp đồng hành vi và giữ chi phí bảo trì ở mức chấp nhận được.**

Bài học này không khuyến khích bỏ qua hiệu năng; nó giúp chọn **thời điểm**, **điểm tác động** và **mức độ phức tạp** hợp lý cho một thay đổi tối ưu hóa, đặc biệt trong ứng dụng Java.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **tính đúng đắn**, **độ rõ ràng**, **thời gian thực thi**, **mức sử dụng tài nguyên** và **khả năng mở rộng**.
2. Giải thích vì sao một thay đổi làm nhanh hơn ở microbenchmark chưa chắc cải thiện trải nghiệm người dùng hoặc toàn hệ thống.
3. Đề xuất một phép tối ưu dựa trên mục tiêu, dữ liệu đo và giả thuyết về nút thắt (*bottleneck*).
4. Nhận diện các đánh đổi: độ phức tạp thuật toán so với bộ nhớ, cache so với dữ liệu lỗi thời, đồng thời so với tính nhất quán, và mã ngắn so với mã dễ hiểu.
5. Bảo toàn kết quả, ngoại lệ, thứ tự, tác dụng phụ và đặc tính giao dịch khi tối ưu mã Java.
6. Thiết kế test hồi quy và phép đo trước–sau để đánh giá hiệu quả thực sự.
7. Quyết định khi nào nên giữ cách viết đơn giản, khi nào nên dùng cấu trúc dữ liệu hoặc cơ chế phức tạp hơn.
8. Giải thích một quyết định tối ưu trong code review bằng **lợi ích đo được, rủi ro và giới hạn kết luận**.

## 2. Tối ưu hóa nhằm cải thiện thuộc tính nào?

Không có một đại lượng “hiệu năng” duy nhất. Những mục tiêu thường gặp:

| Thuộc tính | Câu hỏi cụ thể | Ví dụ |
| --- | --- | --- |
| **Độ trễ (latency)** | Một yêu cầu hoàn tất trong bao lâu? | Thời gian API trả kết quả tìm kiếm. |
| **Thông lượng (throughput)** | Hệ thống xử lý bao nhiêu công việc trong một khoảng thời gian? | Số đơn hàng được xử lý mỗi giây. |
| **CPU** | Cần bao nhiêu năng lực tính toán? | Phép tính lặp lại, mã hóa, tuần tự hóa dữ liệu. |
| **Bộ nhớ** | Ứng dụng dùng bao nhiêu heap và dữ liệu giữ sống? | Tạo nhiều collection trung gian, cache tăng không giới hạn. |
| **I/O và mạng** | Có bao nhiêu lần đọc/ghi, round trip hoặc dữ liệu truyền? | N+1 database queries, nhiều lời gọi API nối tiếp. |
| **Đĩa và lưu trữ** | Có bao nhiêu dữ liệu phải lưu/đọc và tồn tại bao lâu? | File tạm, bộ đệm, bảng index, log. |
| **Khả năng mở rộng** | Hệ thống phản ứng thế nào khi tải tăng? | 100 và 10.000 yêu cầu đồng thời cho kết quả khác nhau. |

Một thay đổi có thể cải thiện đại lượng này nhưng làm xấu đại lượng khác. Ví dụ dùng `HashSet` để tăng tốc kiểm tra thành viên có thể giảm thời gian CPU khi tra cứu nhiều phần tử nhưng cần thêm bộ nhớ và chi phí dựng tập. Giữ cache giảm round trip mạng nhưng thêm chi phí bộ nhớ, invalidation và nguy cơ dữ liệu lỗi thời.

Cần nêu rõ **cái gì cần tối ưu** và **cái gì không được đánh đổi**. Một hệ thống thanh toán thường không được phép giảm tính đúng đắn để tiết kiệm vài mili giây.

### 2.1. Độ trễ trung bình không mô tả toàn bộ trải nghiệm

Giả sử hai cách triển khai có độ trễ trung bình gần bằng nhau, nhưng một cách thường xuyên có vài yêu cầu chậm bất thường. Với ứng dụng tương tác, người dùng có thể chịu ảnh hưởng mạnh bởi những yêu cầu chậm đó.

Vì vậy, tùy mục tiêu, cần theo dõi **phân vị** như p50, p95 hoặc p99 bên cạnh trung bình. p95 là ngưỡng mà khoảng 95% quan sát có thời gian không vượt quá trong một tập đo và điều kiện đã xác định; nó **không bảo đảm** mọi yêu cầu đều dưới ngưỡng ấy.

Nếu có yêu cầu “95% yêu cầu hoàn tất trong một mức thời gian nhất định”, phép đo phải dùng dữ liệu đại diện và cùng cách tính trước–sau. Không nên chỉ nhìn một lần gọi chạy nhanh trên máy cá nhân.

### 2.2. Chi phí tài nguyên không tự đồng nghĩa với lỗi

Một thuật toán sử dụng thêm 20 MB để tiết kiệm một lượng lớn CPU có thể rất hợp lý khi máy chủ có bộ nhớ dư. Cùng thuật toán ấy có thể gây áp lực bộ nhớ trong dịch vụ chạy nhiều instance với giới hạn heap nhỏ.

**Đúng hay sai phụ thuộc ngân sách tài nguyên và bối cảnh vận hành**, không phụ thuộc một quan niệm chung rằng “ít cấp phát nhất luôn tốt nhất”.

## 3. Ba câu hỏi trước khi tối ưu

### 3.1. Có vấn đề thực sự cần giải quyết không?

Một phương thức “trông có vẻ chậm” chưa phải bằng chứng. Cần tìm hiểu:

- Mục tiêu độ trễ hoặc thông lượng là gì?
- Có sự cố, cảnh báo, SLO bị vi phạm hoặc phản hồi người dùng cụ thể không?
- Mất thời gian ở CPU, database, mạng, khóa, GC hay một nơi khác?
- Vấn đề xuất hiện với dữ liệu và tải nào: 10 mục hay 1 triệu mục; một người dùng hay nhiều người đồng thời?
- Có cần cải thiện ngay hay thay đổi đó chỉ dựa trên dự đoán?

Không nhất thiết phải có sự cố production mới tối ưu. Với bài toán biết chắc quy mô dữ liệu lớn hoặc ràng buộc thời gian nghiêm ngặt, phân tích thuật toán sớm có ích. Tuy nhiên, cần **phát biểu giả định và mục tiêu**, tránh tối ưu theo cảm giác.

### 3.2. Nút thắt nằm ở đâu?

Thời gian của một request có thể gồm nhiều thành phần:

~~~text
Nhận yêu cầu
    |
    v
Xác thực ──> Truy vấn database ──> Xử lý Java ──> Gọi API ngoài
                 |                   |                 |
               160 ms               4 ms             120 ms
    |
    v
Trả phản hồi
~~~

Các con số chỉ để minh họa. Nếu phần Java mất 4 ms trong khi database và API ngoài chiếm phần lớn, việc làm mã Java nhanh gấp đôi chỉ tiết kiệm khoảng 2 ms cho đường đi này, giả sử các thành phần khác không đổi. Điều đó có thể ít giá trị hơn sửa truy vấn, giảm round trip hoặc điều chỉnh tích hợp.

**Quy luật Amdahl** nhắc rằng mức tăng tốc tổng thể bị giới hạn bởi tỷ trọng công việc được cải thiện. Nếu chỉ một phần nhỏ thời gian được tối ưu, tăng tốc phần ấy không thể tự động tăng tốc toàn hệ thống theo cùng tỷ lệ.

### 3.3. Rủi ro hành vi là gì?

Một phép tối ưu có thể tác động đến:

- **Kết quả:** thứ tự phần tử, giá trị biên, đơn vị tiền, độ chính xác và cách làm tròn.
- **Ngoại lệ:** lỗi trước đây được ném giờ bị nuốt hoặc đổi kiểu.
- **Trạng thái:** cache cũ, object chia sẻ, mất cập nhật.
- **Tác dụng phụ:** ghi log, gửi event hoặc gọi API bị lặp/bỏ sót.
- **Tính nhất quán:** thao tác vốn nguyên tử bị tách thành nhiều bước độc lập.
- **Khả năng bảo trì:** logic chuyển thành cấu trúc khó giải thích hoặc phụ thuộc vào chi tiết runtime.

Vì vậy, một đề xuất tối ưu nên kèm **giả thuyết hiệu năng** và **danh sách hành vi phải giữ**.

## 4. Mô hình đánh đổi giữa tốc độ, độ rõ ràng và tính đúng đắn

Một phương án tối ưu có thể được đánh giá theo bảng:

| Tiêu chí | Cách triển khai đơn giản | Cách tối ưu phức tạp hơn |
| --- | --- | --- |
| Dễ đọc và sửa | Ít khái niệm, ít trạng thái và phụ thuộc. | Có thể thêm cấu trúc dữ liệu, cache, thread hoặc tham số. |
| Tính đúng đắn | Hợp đồng và đường đi thường dễ thấy hơn. | Cần giữ nguyên hợp đồng và kiểm tra trường hợp mới. |
| Thời gian | Có thể đủ nhanh với tập dữ liệu nhỏ. | Có thể nhanh hơn với quy mô hoặc mẫu tải phù hợp. |
| Bộ nhớ | Ít cấu trúc phụ trợ. | Có thể tăng vì index, bộ đệm hoặc snapshot. |
| Chi phí vận hành | Ít cơ chế cần theo dõi. | Có thể cần giới hạn cache, metrics, invalidation hoặc xử lý tranh chấp. |

Không nên biến bảng thành công thức cộng điểm máy móc. **Tính đúng đắn và các yêu cầu bắt buộc là ràng buộc**, không phải thứ tự do được phép “mua bớt” bằng tốc độ. Trong các phương án đáp ứng ràng buộc, ta mới so sánh lợi ích hiệu năng và chi phí phức tạp.

Một nguyên tắc thực tế:

> **Giữ thiết kế đơn giản nhất đáp ứng yêu cầu đo được; chỉ thêm độ phức tạp khi lợi ích đủ rõ và có cách kiểm chứng lâu dài.**

## 5. Ví dụ Java: thay thuật toán thay vì chỉ làm mã ngắn hơn

Giả sử một hệ thống cần xác định liệu đơn hàng có chứa **bất kỳ mã sản phẩm nào thuộc danh sách chặn** hay không.

Yêu cầu của ví dụ:

- Hai danh sách không được `null`.
- Mã sản phẩm là `String`; phép so sánh có phân biệt chữ hoa–chữ thường.
- Danh sách có thể rỗng hoặc chứa mã trùng nhau.
- Kết quả chỉ là `boolean`; không cần giữ thứ tự kết quả hay trả sản phẩm đầu tiên bị chặn.
- Dữ liệu đầu vào không bị sửa.
- Tất cả mã đều là chuỗi; ví dụ không xử lý chuẩn hóa Unicode hoặc các quy tắc nghiệp vụ khác.

### 5.1. Cách viết trực tiếp, dễ hiểu

~~~java
import java.util.List;
import java.util.Objects;

public final class BlockedProducts {
    private BlockedProducts() {}

    public static boolean hasBlockedProductSimple(
            List<String> productCodes,
            List<String> blockedCodes) {
        Objects.requireNonNull(productCodes, "productCodes");
        Objects.requireNonNull(blockedCodes, "blockedCodes");

        for (String code : productCodes) {
            if (blockedCodes.contains(code)) {
                return true;
            }
        }
        return false;
    }
}
~~~

Ưu điểm: ít mã, dễ theo dõi, không tạo thêm collection; với danh sách rất nhỏ, giải pháp có thể đủ nhanh.

Nếu `productCodes` có \(n\) phần tử và `blockedCodes` có \(m\) phần tử, `List.contains` có thể phải quét tối đa \(m\) phần tử ở mỗi lượt. Trường hợp xấu nhất với danh sách thông thường là **O(n × m)** phép so sánh.

Đó là vấn đề thuật toán có thể đáng chú ý khi hai danh sách lớn.

### 5.2. Phiên bản dùng Set để tối ưu nhiều lần tra cứu

~~~java
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public final class BlockedProductsFast {
    private BlockedProductsFast() {}

    public static boolean hasBlockedProduct(
            List<String> productCodes,
            List<String> blockedCodes) {
        Objects.requireNonNull(productCodes, "productCodes");
        Objects.requireNonNull(blockedCodes, "blockedCodes");

        Set<String> blocked = new HashSet<>(blockedCodes);
        for (String code : productCodes) {
            if (blocked.contains(code)) {
                return true;
            }
        }
        return false;
    }
}
~~~

Với các mã `String` bình thường và hàm băm phân bố phù hợp, dựng `HashSet` mất khoảng O(m) thời gian trung bình; tra cứu `contains` trung bình gần O(1) cho mỗi phần tử. Thời gian trung bình trở thành khoảng **O(n + m)**, đổi lại **O(m)** bộ nhớ phụ trợ.

Đây không phải bảo đảm thời gian cố định cho mọi dữ liệu, cũng không có nghĩa phương án Set luôn nhanh hơn. Khi danh sách chặn chỉ có một hoặc hai mục, chi phí tạo `HashSet`, cấp phát và hash có thể lớn hơn lợi ích của việc quét danh sách.

**Giá trị của thay đổi:** thuật toán khác nhau khi quy mô tăng; tên và cấu trúc vẫn dễ giải thích. Đây là một ví dụ tốt về tối ưu có cơ sở hơn việc rút gọn vòng lặp thành một biểu thức ngắn khó đọc.

### 5.3. Test bảo vệ hợp đồng, không bảo vệ cấu trúc nội bộ

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;

class BlockedProductsFastTest {
    @Test
    void detectsBlockedCode() {
        assertTrue(BlockedProductsFast.hasBlockedProduct(
                List.of("SKU-1", "SKU-2"),
                List.of("SKU-9", "SKU-2")));
    }

    @Test
    void reportsFalseWhenNoneBlocked() {
        assertFalse(BlockedProductsFast.hasBlockedProduct(
                List.of("SKU-1", "SKU-2"),
                List.of("SKU-9")));
    }

    @Test
    void handlesEmptyAndDuplicateCodes() {
        assertFalse(BlockedProductsFast.hasBlockedProduct(
                List.of(),
                List.of("SKU-1", "SKU-1")));
        assertTrue(BlockedProductsFast.hasBlockedProduct(
                List.of("SKU-2", "SKU-2"),
                List.of("SKU-2")));
    }

    @Test
    void preservesCaseSensitiveComparison() {
        assertFalse(BlockedProductsFast.hasBlockedProduct(
                List.of("sku-1"),
                List.of("SKU-1")));
    }

    @Test
    void rejectsNullCollections() {
        assertThrows(NullPointerException.class,
                () -> BlockedProductsFast.hasBlockedProduct(
                        null, List.of()));
        assertThrows(NullPointerException.class,
                () -> BlockedProductsFast.hasBlockedProduct(
                        List.of(), null));
    }
}
~~~

Đây là unit test JUnit 5 dùng để bảo vệ những ca có ý nghĩa. Nếu cần bảo đảm hai phương án tương đương trên nhiều dữ liệu, có thể tạo thêm kiểm thử so sánh **cùng đầu vào → cùng kết quả/ngoại lệ** trên các trường hợp đại diện, kể cả đầu vào rỗng, trùng lặp và khác chữ hoa–thường.

Bộ test không tự chứng minh phiên bản dùng Set nhanh hơn. **Đúng đắn được kiểm tra bằng hành vi; hiệu năng cần một phép đo riêng.**

### 5.4. Một giới hạn khi “tái sử dụng Set” để tránh cấp phát

Có thể nghĩ đến việc tạo `HashSet` một lần rồi cache lại để nhiều request dùng chung. Điều này chỉ đúng nếu danh sách chặn có chính sách vòng đời và cập nhật phù hợp.

Nếu danh sách chặn thay đổi sau khi Set được dựng, cache có thể trả kết quả sai do **dữ liệu lỗi thời**. Nếu nhiều thread cùng sửa Set mutable không có cơ chế đồng bộ, còn có rủi ro về nhất quán.

Vì vậy, việc tránh chi phí cấp phát cũng đặt ra câu hỏi về **ai sở hữu trạng thái, khi nào refresh và ai được đọc/ghi**. Không nên tiếp tục tối ưu bằng cách đưa Set vào field `static` mutable mà chưa xác định hợp đồng.

## 6. Tối ưu thuật toán và cấu trúc dữ liệu thường đáng xem trước mẹo vi mô

Một lựa chọn cấu trúc dữ liệu phù hợp có thể tạo khác biệt lớn khi quy mô tăng:

| Bài toán | Cách đơn giản | Phương án đáng cân nhắc khi có lý do |
| --- | --- | --- |
| Kiểm tra một mã có thuộc tập lớn không | `List.contains` trong vòng lặp. | `HashSet` hoặc index phù hợp. |
| Lấy bản ghi theo khóa nhiều lần | Quét toàn danh sách. | `Map` theo khóa khi có hợp đồng về trùng khóa. |
| Tìm các dòng dữ liệu theo tiêu chí tại database | Lấy mọi dòng rồi lọc trong Java. | Truy vấn có điều kiện và index thích hợp. |
| Tìm kiếm lặp lại trên dữ liệu ít thay đổi | Quét và tính lại mọi lần. | Tiền xử lý hoặc cache có giới hạn/vô hiệu hóa rõ. |
| Nối chuỗi trong vòng lặp rất lớn | `result = result + piece` nhiều lần. | `StringBuilder` dùng trong phạm vi phù hợp. |

**Cẩn trọng:** mỗi cấu trúc dữ liệu có ngữ nghĩa riêng. Chuyển `List` sang `Set` làm mất tính trùng lặp và không giữ thứ tự theo hợp đồng của Set tổng quát. Nếu nghiệp vụ cần giữ thứ tự, chọn `LinkedHashSet` hoặc mô hình khác khi phù hợp; nếu cần đếm số lần xuất hiện, `Set` không thể thay thế danh sách như không có gì thay đổi.

Tối ưu có ý nghĩa là **chọn đúng cấu trúc cho phép toán cần thực hiện**, đồng thời giữ những thuộc tính dữ liệu mà yêu cầu phụ thuộc vào.

## 7. Tối ưu tính toán nhưng không đánh đổi kết quả: đặc biệt với số tiền

Một nguồn lỗi thường gặp là thay kiểu dữ liệu hoặc công thức để giảm CPU/cấp phát mà không xét chính xác số học.

### 7.1. Số thực dấu phẩy động có thể không phù hợp cho tiền

Ví dụ:

~~~java
double price = 0.1;
double fee = 0.2;
System.out.println(price + fee); // Có thể in 0.30000000000000004
~~~

`double` biểu diễn nhị phân không thể biểu diễn chính xác nhiều phân số thập phân. Nếu yêu cầu là tính tiền với quy tắc làm tròn rõ ràng, thường nên dùng **đơn vị tiền nhỏ nhất bằng kiểu nguyên** khi phù hợp hoặc `BigDecimal` với `scale` và `RoundingMode` đã xác định.

Không nên thay `BigDecimal` bằng `double` chỉ vì microbenchmark cho thấy phép cộng nhanh hơn, nếu việc thay đổi làm sai hợp đồng số học.

### 7.2. Kiểu nguyên cũng có giới hạn tràn số

~~~java
long priceCents = Long.MAX_VALUE / 2;
long quantity = 3;

long total = priceCents * quantity; // Tràn long, không tự ném ngoại lệ
~~~

Để nhận biết tràn số ở phép nhân:

~~~java
long total = Math.multiplyExact(priceCents, quantity);
~~~

`Math.multiplyExact` ném `ArithmeticException` khi kết quả không biểu diễn được trong `long`. Sự khác biệt này có ý nghĩa nghiệp vụ: đôi khi nên từ chối giao dịch hoặc dùng kiểu số có miền lớn hơn, thay vì âm thầm tạo số âm.

Việc thêm `multiplyExact` cũng có thể **thay đổi hành vi ngoại lệ** của mã cũ. Nếu nhiệm vụ hiện tại là “refactor không đổi hành vi”, cần xác nhận và tách riêng việc sửa lỗi tràn số thay vì xem nó là tối ưu thuần túy.

### 7.3. Làm tròn và thứ tự phép toán là một phần hợp đồng

Hai cách tính:

~~~java
// Chiết khấu từng dòng, rồi cộng:
long totalDiscountByLine =
        (item1Cents / 10) + (item2Cents / 10);

// Cộng tiền rồi chiết khấu:
long totalDiscountOnSum =
        Math.addExact(item1Cents, item2Cents) / 10;
~~~

có thể cho kết quả khác vì phép chia nguyên làm tròn xuống ở mỗi dòng so với làm tròn sau khi cộng. Ví dụ hai dòng 9 đơn vị: cách thứ nhất cho 0, cách thứ hai cho 1.

Đừng “gộp phép tính cho nhanh” trước khi xác định chính sách làm tròn theo dòng hay toàn đơn. **Tính đúng đắn không phải chi tiết có thể suy ra từ việc hai biểu thức trông tương đương đại số.**

## 8. Cache: giảm tính toán nhưng tăng trạng thái phải quản lý

Caching thường là tối ưu dễ hấp dẫn: kết quả được tính rồi thì giữ lại để khỏi tính nữa. Nhưng cache làm xuất hiện một **bản sao có vòng đời riêng** và câu hỏi **khi nào bản sao không còn đúng**.

### 8.1. Ví dụ rủi ro của cache thiếu khóa

Giả sử phí vận chuyển phụ thuộc vào `postalCode`, `shippingMethod` và `policyVersion`. Nếu cache chỉ dùng `postalCode` làm khóa, hai lần yêu cầu ở cùng mã bưu chính nhưng phương thức vận chuyển khác nhau có thể nhận sai phí.

Dù cache cho tỷ lệ hit cao và giảm độ trễ đáng kể, nó vẫn **vi phạm yêu cầu** nếu khóa không chứa đủ các yếu tố ảnh hưởng kết quả.

### 8.2. Những câu hỏi tối thiểu trước khi thêm cache

1. Dữ liệu **nguồn sự thật** ở đâu?
2. Khóa cache có đại diện đầy đủ cho đầu vào quyết định kết quả không?
3. Ai cập nhật nguồn và cache biết việc đó khi nào?
4. Có chấp nhận dữ liệu lỗi thời trong một khoảng thời gian hay không?
5. Cache có giới hạn dung lượng và thời hạn tồn tại không?
6. Có nguy cơ để lộ dữ liệu giữa người dùng hoặc tenant không?
7. Khi cache hỏng/mất, chức năng có vẫn đúng hoặc thất bại có kiểm soát không?

TTL (*time to live*) giới hạn khoảng thời gian giữ một mục nhưng **không tự bảo đảm dữ liệu luôn mới trong thời gian TTL**. Với tồn kho, quyền truy cập hoặc giao dịch tài chính, một quyết định quan trọng có thể vẫn cần xác minh tại nguồn dữ liệu có khả năng cập nhật nhất quán.

### 8.3. Đánh đổi cụ thể

| Lợi ích cache | Chi phí và rủi ro |
| --- | --- |
| Giảm truy vấn hoặc tính toán lặp lại. | Bộ nhớ tăng và cần eviction. |
| Giảm độ trễ khi truy cập từ cache. | Tăng độ phức tạp khi xử lý miss, stampede hoặc refresh. |
| Giảm tải cho hệ thống phụ thuộc. | Có thể lưu dữ liệu lỗi thời hoặc sai phạm vi người dùng. |
| Cải thiện trải nghiệm trong điều kiện mạng chậm. | Cần giám sát hit ratio, sai lệch dữ liệu, lỗi và mục bị quá hạn. |

Chỉ nên thêm cache khi **đặc tính nhất quán có thể chấp nhận được** và **lợi ích đo được xứng với chi phí quản lý trạng thái**.

## 9. Đồng thời và bất đồng bộ: thông lượng cao hơn có thể đi kèm lỗi mới

Một phép tối ưu phổ biến khác là chạy nhiều phần việc song song. Nhưng song song hóa không miễn phí: có chi phí tạo/lập lịch công việc, contention, đồng bộ và giới hạn của các hệ thống phụ thuộc.

### 9.1. Không phải cứ dùng parallel stream là nhanh

~~~java
long count = items.parallelStream()
        .filter(this::isEligible)
        .count();
~~~

Đoạn này có thể nhanh hơn khi mỗi phép kiểm tra đủ nặng, số phần tử lớn, công việc độc lập và máy có tài nguyên phù hợp. Nhưng nó có thể **chậm hơn** nếu tập dữ liệu nhỏ, chi phí phân tách/phối hợp lớn hoặc bottleneck nằm ở I/O và hệ thống phụ thuộc.

Nếu `isEligible` có tác dụng phụ, phụ thuộc thứ tự hoặc sửa trạng thái chia sẻ, chạy song song còn có thể làm hành vi khác đi. Một lựa chọn tốt là tách phép kiểm tra thuần túy, đo đạc trên dữ liệu đại diện và cân nhắc giới hạn tài nguyên.

### 9.2. Lỗi check-then-act khi tối ưu cập nhật đồng thời

~~~java
if (inventory.available(sku) >= quantity) {
    inventory.reserve(sku, quantity);
}
~~~

Đoạn mã có thể hoạt động khi một request chạy đơn lẻ. Nếu hai request cùng đọc số lượng còn lại rồi đều ghi nhận giữ chỗ, chúng có thể bán vượt tồn kho.

Việc chuyển sang xử lý nhiều luồng để tăng throughput khiến lỗi rõ hơn, nhưng nguyên nhân là **kiểm tra và cập nhật không nguyên tử tại nơi dữ liệu được sở hữu**.

Một giải pháp đúng có thể cần giao dịch database, cập nhật có điều kiện hoặc cơ chế khóa được thiết kế theo kho dữ liệu và yêu cầu nhất quán. `synchronized` chỉ trên một instance Java không bảo đảm tính nguyên tử giữa nhiều instance ứng dụng.

### 9.3. Bất đồng bộ không làm công việc tự biến mất

Gọi công việc với `CompletableFuture` có thể giảm thời gian chờ của thread xử lý request, nhưng công việc thực vẫn cần CPU, I/O và bộ nhớ. Nếu nhận vô hạn công việc mà không có giới hạn hàng đợi hoặc khả năng từ chối, hệ thống có thể tăng độ trễ, cạn tài nguyên hoặc mất công việc khi tiến trình dừng.

Tối ưu cần xét:

- Bounded queue, số worker và giới hạn concurrency.
- Timeout, retry, idempotency và cách xử lý lỗi.
- Thứ tự công việc có còn quan trọng không?
- Kết quả có được lưu bền trước khi trả “thành công” không?
- Có cách quan sát và bảo vệ tác vụ khi tải tăng không?

Trong thực tế, **một phương thức ngắn trả future** chưa chắc đơn giản hơn một phương thức đồng bộ rõ ràng nếu toàn bộ hợp đồng lỗi và tài nguyên trở nên khó theo dõi.

## 10. I/O và database: nhiều khi đáng tối ưu hơn vòng lặp Java

Một ví dụ phổ biến là vấn đề N+1 truy vấn:

~~~text
1 truy vấn lấy 100 đơn hàng
       |
       +--> 100 truy vấn riêng để lấy khách hàng của từng đơn
       |
       v
Tổng cộng 101 truy vấn
~~~

Ngay cả khi mỗi vòng lặp Java chỉ tốn rất ít thời gian, số lượt đi–về database có thể chiếm phần lớn độ trễ.

Có thể xem xét:

- Lấy dữ liệu cần thiết bằng truy vấn phù hợp, batch fetching hoặc join khi đúng yêu cầu.
- Chỉ chọn những cột cần dùng thay vì lấy cả object graph không cần thiết.
- Dùng index phù hợp với điều kiện lọc và kiểu truy vấn quan trọng.
- Giảm số lượt gọi mạng bằng batching khi hợp đồng của API cho phép.
- Phân trang hoặc xử lý theo luồng với tập kết quả lớn thay vì giữ toàn bộ trong heap.

**Đánh đổi:** lấy quá nhiều dữ liệu bằng một join có thể gây trùng lặp hàng và tăng bộ nhớ; batching có thể tăng độ trễ cho từng phần tử; phân trang có thể làm phức tạp thứ tự và tính nhất quán khi dữ liệu đang thay đổi.

Không nên quy mọi vấn đề chậm sang thuật toán trong Java khi phép đo cho thấy phần lớn thời gian nằm ngoài JVM.

## 11. Đo đạc trước–sau: phân biệt hiệu quả thật với nhiễu

Một phép đo có ích phải trả lời cùng một câu hỏi trước và sau thay đổi, dưới điều kiện đủ tương đồng.

### 11.1. Xác định mục tiêu và tập dữ liệu

Trước khi đo:

1. Chọn thao tác cụ thể: ví dụ tìm mã chặn trong hai danh sách.
2. Chọn kích thước và phân bố dữ liệu đại diện: `n`, `m`, tỷ lệ trúng, chuỗi ngắn/dài, số mã trùng.
3. Chọn thước đo: thời gian mỗi thao tác, thông lượng, phân bố độ trễ, bộ nhớ cấp phát.
4. Ghi môi trường: JDK, CPU, mức tải, cấu hình JVM, heap và các phụ thuộc bên ngoài.
5. Xác định tiêu chí thành công và ràng buộc: cải thiện đủ lớn, không tăng heap vượt ngân sách, test không thất bại.

Với ví dụ `List.contains` và `HashSet`, cần đo cả trường hợp **danh sách rất nhỏ** và **danh sách lớn**. Nếu chỉ đo dữ liệu có một triệu phần tử, có thể chọn cách tối ưu không phù hợp với tải thật thường là vài phần tử.

### 11.2. Tại sao tự bấm giờ một lần dễ sai trong Java?

Một ví dụ đo đơn giản bằng `System.nanoTime()` có thể chịu ảnh hưởng mạnh bởi:

- JIT compilation và warm-up của JVM.
- Hoạt động garbage collector.
- CPU scaling, tiến trình khác và scheduling.
- Khác biệt dữ liệu cache, cấp phát và trạng thái bộ nhớ.
- Dead-code elimination hoặc constant folding nếu phép đo được thiết kế sai.
- Nhiễu do I/O, log hoặc khởi tạo đối tượng nằm trong phạm vi đo.

`System.nanoTime()` hữu ích để đo thời gian đã trôi qua trong những trường hợp phù hợp, nhưng không có nghĩa chỉ cần một lần gọi là đủ kết luận về tối ưu vi mô.

### 11.3. Microbenchmark và hệ thống thật trả lời các câu hỏi khác nhau

**Microbenchmark** cô lập một thao tác để so sánh một khía cạnh chi phí. Với Java, **JMH** là một công cụ phổ biến hỗ trợ warm-up, đo nhiều lượt, xử lý kết quả và hạn chế một số sai lệch đo đạc thường gặp.

Nhưng microbenchmark không thay thế:

- Profiling để xác định phần nào đang chiếm tài nguyên thật.
- Load test để xem độ trễ khi nhiều yêu cầu đồng thời.
- Integration test để xác minh truy vấn, kết nối và giao dịch.
- Giám sát production để đánh giá tải và lỗi thực tế.

Một phiên bản nhanh hơn 20% trong microbenchmark có thể không thay đổi đáng kể p95 của API nếu phần lớn thời gian nằm ở mạng hoặc database.

### 11.4. Khung ghi nhận một phép tối ưu

| Trường | Ví dụ thông tin cần ghi |
| --- | --- |
| Mục tiêu | Giảm độ trễ kiểm tra sản phẩm bị chặn khi danh sách lớn. |
| Bottleneck quan sát | Phần lớn CPU tập trung ở thao tác `List.contains` lặp lại. |
| Giả thuyết | Tạo Set một lần giảm tổng số phép so sánh khi số phần tử lớn. |
| Đầu vào đo | Kích thước hai danh sách, tỷ lệ trúng, loại mã và phân bố dữ liệu. |
| Thước đo | Thời gian mỗi lượt, cấp phát bộ nhớ, kết quả p95 nếu áp dụng ở service. |
| Ràng buộc | Không thay đổi kết quả, ngoại lệ, phân biệt chữ hoa–thường. |
| Đánh đổi | Thêm O(m) bộ nhớ và chi phí xây Set. |
| Kết luận | Giữ/không giữ tối ưu trong các ngưỡng dữ liệu thực tế đã kiểm tra. |

**Lưu ý:** bảng minh họa cách báo cáo, không khẳng định đã thực hiện một phép đo cụ thể hoặc có kết quả tăng tốc nào.

## 12. Một tối ưu hóa tốt phải đi qua hai nhóm kiểm chứng riêng

Tính đúng đắn và hiệu năng cần **hai loại bằng chứng** vì chúng trả lời hai câu hỏi khác nhau.

### 12.1. Bằng chứng giữ đúng hành vi

Trước và sau thay đổi, cần xem:

- Kết quả trả về có như nhau cho những trường hợp hợp lệ không?
- Trường hợp lỗi, ngoại lệ và điều kiện biên có giữ hợp đồng không?
- Thứ tự kết quả có quan trọng không? Có thay đổi thứ tự duyệt hoặc xử lý không?
- Có đổi quy tắc làm tròn, đơn vị dữ liệu hoặc phạm vi số không?
- Tác dụng phụ (lưu DB, gửi event, log kiểm toán) có phát sinh đúng số lần và đúng thứ tự không?
- Trong hệ thống đồng thời, có bảo vệ bất biến và trạng thái sau thao tác không?
- Test có độc lập với cách cài đặt riêng tư hay đang phụ thuộc cấu trúc mới?

Không nhất thiết mỗi tối ưu phải có test mới nếu đã có bộ test đủ mạnh. Nhưng mọi thay đổi có rủi ro nên có bằng chứng tương xứng.

### 12.2. Bằng chứng đạt mục tiêu hiệu năng

Sau khi hành vi được bảo vệ, cần đánh giá:

- Kịch bản đo có trùng với vấn đề ban đầu không?
- Lợi ích có lớn hơn sai số/nhiễu và ổn định qua nhiều lượt đo không?
- Chi phí bộ nhớ/GC/I/O có tăng ngoài ngân sách không?
- Khi tải tăng, sự cải thiện có còn đúng không?
- Có xuất hiện latency spike hoặc contention mới không?
- Việc tăng tốc có bù được chi phí tạo và duy trì cơ chế mới không?

Không nên viết test kiểu “hàm phải luôn chạy dưới 5 ms trên mọi máy CI” cho một thao tác nhỏ mà chưa kiểm soát môi trường. Các kiểm thử hiệu năng cần ngưỡng và quy trình đo được thiết kế phù hợp; tránh biến nhiễu máy chạy thành lỗi kiểm thử ngẫu nhiên.

## 13. Những tối ưu hóa thường gây hại khi áp dụng quá sớm

### 13.1. Giảm vài dòng nhưng tăng chi phí nhận thức

~~~java
// Ví dụ nén điều kiện, không phải cải thiện chắc chắn:
return a ? b ? x : y : c ? z : w;
~~~

Cách viết ngắn có thể khó theo dõi hơn một cấu trúc `if/else` rõ ràng. Ít dòng không chứng minh ít CPU, ít nhánh hay ít lỗi.

### 13.2. Tạo quá nhiều object mutable dùng lại

Giữ một object mutable trong singleton để tránh cấp phát có thể làm request này ảnh hưởng request khác. Đôi khi chi phí tránh cấp phát nhỏ hơn chi phí đồng bộ hoặc sửa lỗi race condition.

Cần đo trước khi đổi một thiết kế không trạng thái, dễ kiểm thử thành một thiết kế chia sẻ trạng thái chỉ để giảm vài allocation.

### 13.3. Loại bỏ validation hoặc xử lý lỗi

Bỏ kiểm tra đầu vào, bỏ `Math.addExact` hoặc nuốt ngoại lệ có thể làm một microbenchmark nhanh hơn, nhưng cũng đổi hợp đồng hoặc giấu lỗi dữ liệu.

Nếu validation có chi phí đáng kể, hãy đo **đúng điểm kiểm tra**, xem có trùng lặp bất hợp lý không và có thể kiểm tra ở ranh giới phù hợp hơn không. Không nên loại bỏ một kiểm tra bảo vệ tính đúng đắn chỉ vì nó làm tăng thời gian thực thi.

### 13.4. Cache mọi thứ

Cache không giới hạn có thể dẫn đến bộ nhớ tăng dần, dữ liệu cũ và chi phí invalidation. Không phải tính toán nào cũng đáng cache; nếu phép tính rất rẻ hoặc dữ liệu đổi liên tục, cache có thể làm hệ thống phức tạp hơn lợi ích.

### 13.5. Dùng concurrency cho công việc vốn không nghẽn CPU

Tăng số thread có thể tăng contention, context switching và tải vào database. Khi bottleneck nằm ở một kho lưu trữ có giới hạn, thêm nhiều request đồng thời có thể làm p95/p99 tệ hơn.

### 13.6. Tự viết thuật toán khó kiểm chứng thay thư viện ổn định

Một tối ưu tự chế cho sorting, parsing hay thao tác collection có thể thêm nhiều trường hợp biên, code khó đọc và rủi ro bảo mật. Trước khi thay một API thư viện đã hiểu rõ, cần có bằng chứng nó là bottleneck và phương án thay thế giữ đúng hợp đồng.

## 14. Khi nào nên ưu tiên tính rõ ràng?

Ưu tiên giải pháp đơn giản khi:

- Độ trễ và tài nguyên đã đáp ứng yêu cầu với khoảng dự phòng phù hợp.
- Không có bằng chứng thao tác đang xét là bottleneck.
- Tập dữ liệu nhỏ hoặc hiếm xử lý, chi phí tạo cấu trúc tối ưu không đáng.
- Phép tối ưu đòi trạng thái dùng chung, cache phức tạp hoặc thêm nhiều nhánh khó kiểm chứng.
- Mã thuộc nghiệp vụ rủi ro cao và lợi ích đo được quá nhỏ so với độ phức tạp tăng.
- Nhóm phải thường xuyên thay đổi quy tắc và cấu trúc tối ưu sẽ làm mọi thay đổi khó hơn.

**Ưu tiên rõ ràng không có nghĩa cố tình chậm.** Một thuật toán đơn giản, có ranh giới đúng và dữ liệu rõ nghĩa thường là nền tảng giúp tối ưu có căn cứ sau này.

### 14.1. Khi nào chấp nhận thêm phức tạp?

Một cơ chế phức tạp hơn đáng cân nhắc khi:

- Yêu cầu hiệu năng hoặc ngân sách tài nguyên quan trọng đang không đạt.
- Profiling/đo đạc chỉ ra đúng nút thắt mà cơ chế mới giải quyết.
- Có test đủ mạnh cho kết quả và đường đi lỗi.
- Cơ chế mới có tên, hợp đồng, phạm vi sở hữu và chiến lược dọn dẹp rõ.
- Lợi ích đo được đáng kể trong bối cảnh tải thực và vẫn bền qua các lần thay đổi.
- Nhóm có thể giám sát, rollback hoặc vô hiệu hóa tối ưu khi kết quả vận hành không như kỳ vọng.

Một tối ưu tốt không nhất thiết là ngắn nhất, nhưng **cần giải thích được vì sao sự phức tạp bổ sung là cần thiết**.

## 15. Tình huống thực tế: tăng tốc tra cứu giá nhưng trả sai chính sách

Một service báo giá có API được gọi nhiều lần mỗi giây. Đội phát triển nhận thấy truy vấn chính sách giá tốn thời gian nên bổ sung cache trong bộ nhớ. Sau khi triển khai, thời gian trung bình giảm, nhưng một số đơn nhận giá sai trong lúc chương trình khuyến mại đổi chính sách.

### 15.1. Phân tích nguyên nhân

Giả sử giá phụ thuộc vào:

- Mã sản phẩm.
- Hạng khách hàng.
- Khu vực giao hàng.
- Phiên bản chính sách đang có hiệu lực.

Cache chỉ dùng mã sản phẩm làm khóa. Hai yêu cầu của các nhóm khách hàng khác nhau có thể nhận cùng giá đã cache dù đáng lẽ phải khác.

Đây là một ví dụ **tốc độ tăng nhưng tính đúng đắn giảm**. Không nên kết luận phép tối ưu thành công chỉ vì latency trung bình đẹp hơn.

### 15.2. Hướng giải quyết

1. **Xác nhận đặc tả giá:** đầu vào nào ảnh hưởng kết quả, thời điểm chính sách có hiệu lực khi nào?
2. **Chọn khóa cache đúng:** bao gồm các yếu tố cần thiết để phân biệt quyết định giá, hoặc thay cấu trúc lưu cache.
3. **Xác định chính sách invalidation:** phiên bản, sự kiện thay đổi, TTL và ngữ nghĩa nhất quán phù hợp.
4. **Bảo vệ quyền truy cập:** không chia sẻ dữ liệu giá cá nhân/tenant không đúng phạm vi.
5. **Viết test hồi quy:** cùng sản phẩm nhưng khác hạng, khác vùng, khác phiên bản chính sách phải cho kết quả phù hợp.
6. **Đo cả hai mặt:** thời gian truy vấn, bộ nhớ cache, tỷ lệ hit, tỷ lệ lỗi giá và hành vi khi policy đổi.
7. **Chuẩn bị rollback:** có thể tắt cache hoặc trở về truy vấn nguồn khi phát hiện sai lệch không?

Sau khi bảo vệ tính đúng đắn, nhóm mới có cơ sở đánh giá lợi ích hiệu năng ròng của cache.

## 16. Quy trình đề xuất tối ưu hóa trong code review

Một chuỗi sáu bước có thể áp dụng:

**Bước 1 — Nêu vấn đề đo được.** “Truy vấn chính sách chiếm phần đáng kể độ trễ của request dưới mẫu tải X”, thay vì “đoạn này trông chậm”.

**Bước 2 — Xác định hợp đồng hành vi.** Đầu vào, kết quả, thứ tự, ngoại lệ, tác dụng phụ, tính nguyên tử và những tình huống biên phải giữ nguyên.

**Bước 3 — Chọn phương án ít phức tạp nhất giải quyết nút thắt.** Ví dụ đổi `List.contains` lặp lại thành Set, cải thiện truy vấn hoặc giảm số round trip trước khi cân nhắc cache phức tạp hay song song hóa.

**Bước 4 — Viết và chạy test hồi quy.** So sánh các trường hợp thông thường, giá trị biên, lỗi hạ tầng và trạng thái khi cần.

**Bước 5 — Đo trên dữ liệu và tải đại diện.** Ghi lại môi trường, phiên bản, thời gian, CPU, heap hoặc độ trễ phù hợp. Kiểm tra nhiễu và tính ổn định.

**Bước 6 — Ghi nhận đánh đổi và quyết định.** Giữ tối ưu nếu lợi ích đủ rõ, hợp đồng đúng và chi phí bảo trì chấp nhận được. Nếu không, có thể quay lại cách đơn giản hơn.

### 16.1. Mẫu lập luận trong pull request

> “Profiling cho thấy việc kiểm tra danh sách mã chặn bằng `List.contains` lặp lại chiếm phần đáng kể CPU khi có hàng chục nghìn mã. Tôi đổi sang tạo `HashSet` một lần trong phạm vi lời gọi để giảm số lần quét. Hai phương án có cùng kết quả cho trường hợp trùng mã, danh sách rỗng và mã khác chữ hoa–thường theo unit test. Phương án mới dùng thêm O(m) bộ nhớ; tôi chưa cache Set giữa các request vì danh sách chặn có thể thay đổi. Chúng ta sẽ so sánh thời gian và mức cấp phát trên tập dữ liệu đại diện trước khi quyết định giữ thay đổi.”

Mô tả này nêu rõ **bằng chứng, dự kiến lợi ích, hợp đồng được giữ và chi phí mới**, thay vì chỉ tuyên bố “code nhanh hơn”.

## 17. Bài tập tự đánh giá

### Tình huống A: Stream hay vòng lặp?

Một lập trình viên thay vòng lặp thường bằng chuỗi `stream().filter().map().toList()` và nói rằng Java Stream luôn nhanh hơn.

**Câu hỏi:** có thể kết luận như vậy không? Nên đo điều gì?

**Gợi ý:** không có quy tắc “Stream luôn nhanh hơn”. Kết quả phụ thuộc dữ liệu, JVM, pipeline, cấp phát và khả năng tối ưu của runtime. Nên kiểm tra trước–sau về kết quả, thứ tự và ngoại lệ, rồi đo trên dữ liệu đại diện nếu đây thật sự là bottleneck. Ưu tiên cách người bảo trì hiểu rõ khi hiệu năng tương đương.

### Tình huống B: Cache tồn kho

Một nhóm cache số lượng hàng còn lại trong 60 giây để giảm truy vấn database. Dữ liệu tồn kho thay đổi liên tục và đơn đặt hàng phải không được bán vượt số lượng.

**Câu hỏi:** có thể dựa vào cache để xác nhận bán hàng không?

**Gợi ý:** cache có thể hỗ trợ hiển thị hoặc gợi ý theo mức chấp nhận sai lệch, nhưng quyết định giữ chỗ quan trọng cần được bảo đảm bằng cập nhật nhất quán tại nguồn dữ liệu có thẩm quyền. TTL 60 giây không tự bảo đảm tính đúng trong khoảng ấy.

### Tình huống C: Tối ưu phép nhân tiền

Một đoạn mã dùng `Math.multiplyExact(unitPrice, quantity)`. Để tăng tốc, người sửa thay bằng `unitPrice * quantity` và tất cả test thông thường đều đỗ.

**Câu hỏi:** hợp đồng đã thay đổi ở đâu?

**Gợi ý:** phép nhân thông thường có thể tràn số âm thầm; `multiplyExact` phát ngoại lệ khi tràn. Cần test giá trị biên, xác định miền dữ liệu hợp lệ và chỉ đổi hành vi nếu được chủ đích chấp nhận.

### Tình huống D: Microbenchmark cải thiện nhưng API không đổi

Một microbenchmark cho thấy hàm xử lý Java nhanh hơn nhiều lần. Load test tổng thể của API gần như không thay đổi, còn p99 vẫn cao.

**Câu hỏi:** những khả năng nào cần điều tra?

**Gợi ý:** hàm có thể chiếm tỷ lệ thời gian nhỏ; bottleneck ở database, mạng, khóa hoặc GC. Kiểm tra profiling của request, phân bố độ trễ, contention và tải; không mặc định microbenchmark sai hoặc lập tức thêm tối ưu khác vào cùng hàm.

### Tình huống E: Tối ưu bằng song song hóa

Một nhóm chuyển xử lý danh sách đơn sang `parallelStream`. Test đơn luồng đỗ, nhưng một số đơn được tạo hai lần khi chạy tải.

**Câu hỏi:** nên xử lý từ đâu?

**Gợi ý:** kiểm tra tác dụng phụ và trạng thái chia sẻ; xác định thao tác ghi nhận đơn có cơ chế idempotency và bảo vệ nguyên tử ở nơi lưu dữ liệu hay không. Tăng thông lượng mà tạo trùng đơn là vi phạm tính đúng đắn.

## 18. Checklist trước khi chấp nhận một phép tối ưu

- [ ] Tôi nêu rõ độ trễ, thông lượng, CPU, bộ nhớ hoặc tài nguyên nào cần cải thiện.
- [ ] Có dữ liệu hoặc phân tích chứng minh điểm đang sửa liên quan tới bottleneck.
- [ ] Tập dữ liệu, tải, môi trường đo và thước đo phù hợp với tình huống thực tế.
- [ ] Tôi hiểu phép tối ưu làm thay đổi độ phức tạp thuật toán và bộ nhớ như thế nào.
- [ ] Kết quả, ngoại lệ, thứ tự và những trường hợp biên vẫn đúng theo hợp đồng.
- [ ] Các phép tính tiền, thời gian, số học và làm tròn đã được xem xét cẩn thận.
- [ ] Không đưa trạng thái dùng chung hoặc cache vào hệ thống mà thiếu ownership/invalidation.
- [ ] Không làm mất tính nguyên tử hay tạo race condition khi song song hóa.
- [ ] Test xác minh hành vi; phép đo hiệu năng xác minh lợi ích — hai loại bằng chứng được phân biệt.
- [ ] Chỉ số không được diễn giải ngoài phạm vi đã đo, nhất là benchmark nhỏ và dữ liệu không đại diện.
- [ ] Tác động tới GC, I/O, database và các tài nguyên khác đã được xem xét.
- [ ] Độ phức tạp tăng thêm có lợi ích đủ lớn và có thể được người khác bảo trì.
- [ ] Có cách giám sát hoặc quay lại giải pháp cũ nếu tối ưu gây tác động không mong muốn.
- [ ] Tôi có thể giải thích lựa chọn trong code review bằng bằng chứng thay vì sở thích cú pháp.

## 19. Kết luận

**Tối ưu hóa hiệu năng** giúp phần mềm đáp ứng yêu cầu về thời gian, thông lượng và tài nguyên. Tuy nhiên, thay đổi chỉ có giá trị khi nó **giữ được tính đúng đắn** và không tạo chi phí hiểu, kiểm thử, vận hành quá lớn so với lợi ích.

Trong **CODE_QUALITY_FUNDAMENTALS**, mã nguồn chất lượng không phải mã chạy nhanh nhất trong một phép đo cô lập, cũng không phải mã ngắn nhất hay nhiều abstraction nhất. Mã nguồn tốt là mã **đáp ứng hợp đồng, dễ hiểu để được sửa an toàn, và sử dụng tài nguyên phù hợp với mục tiêu thực tế**.

Hãy **đo trước, tìm đúng nút thắt, chọn tối ưu nhỏ nhất có giá trị, kiểm tra hành vi và đo lại**. Khi có bằng chứng rõ, một cấu trúc phức tạp hơn có thể hoàn toàn xứng đáng. Khi lợi ích chưa được xác nhận, giải pháp đơn giản và đúng thường là nền tảng đáng tin cậy nhất.

