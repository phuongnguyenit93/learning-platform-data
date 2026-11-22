# Hiệu quả sử dụng thời gian và tài nguyên

Một chức năng có thể cho kết quả chính xác nhưng mất quá lâu để phản hồi, khiến người dùng phải chờ hoặc hệ thống không phục vụ nổi khi lượng truy cập tăng. Một chức năng khác trả lời rất nhanh nhưng sử dụng quá nhiều bộ nhớ hoặc kết nối cơ sở dữ liệu, làm ảnh hưởng đến các chức năng còn lại. Cả hai đều đặt ra vấn đề về **hiệu quả sử dụng thời gian và tài nguyên** (*performance efficiency*).

Trong nhóm **Các chiều chất lượng** của module CODE_QUALITY_FUNDAMENTALS, hiệu quả sử dụng thời gian và tài nguyên giúp đánh giá liệu mã nguồn có thực hiện đúng công việc **trong giới hạn thời gian, tải và nguồn lực đã xác định** hay không. Đây cũng là một phần của việc xác định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi: cải tiến tốc độ sẽ không có giá trị nếu làm sai kết quả hoặc khiến mã trở nên khó bảo trì.

## 1. Hiểu đúng về hiệu quả

**Hiệu quả sử dụng thời gian và tài nguyên** là khả năng tạo ra kết quả mong đợi với thời gian phản hồi và lượng tài nguyên phù hợp trong những điều kiện vận hành cụ thể.

Khái niệm này cần gắn với **ngữ cảnh đo đạc**: đầu vào, kích thước dữ liệu, số người dùng đồng thời, phần cứng, cơ sở dữ liệu, mạng, phiên bản JVM và cấu hình chạy. Không có ngữ cảnh, câu “hàm này nhanh” hoặc “ứng dụng này tốn RAM” chưa đủ để kết luận chất lượng.

Ví dụ, cùng một API tìm kiếm sản phẩm:

- Với 10 sản phẩm, việc duyệt danh sách trong bộ nhớ có thể hoàn thành gần như ngay lập tức.
- Với 10 triệu sản phẩm, cách duyệt đó có thể tiêu tốn nhiều thời gian và CPU.
- Khi có hàng trăm yêu cầu đồng thời, truy vấn cơ sở dữ liệu có thể phải chờ kết nối dù bản thân mã Java không đổi.

Vì vậy, cần xem **kết quả** cùng với **chi phí để tạo ra kết quả**.

### 1.1. Ba nhóm đặc tính cần quan sát

| Nhóm | Ý nghĩa | Ví dụ chỉ số |
| --- | --- | --- |
| Hành vi theo thời gian | Mất bao lâu để hoàn thành thao tác? | Thời gian phản hồi, thời gian xử lý, độ trễ p95/p99 |
| Sử dụng tài nguyên | Tốn bao nhiêu tài nguyên khi làm việc? | CPU, bộ nhớ heap, số byte cấp phát, đĩa, mạng, số kết nối |
| Khả năng đáp ứng tải | Phục vụ được mức nhu cầu nào trong giới hạn yêu cầu? | Thông lượng, số yêu cầu đồng thời, tỉ lệ lỗi khi tăng tải |

Các nhóm có liên hệ nhưng không đồng nhất. Một dịch vụ có thể có thời gian phản hồi tốt khi tải thấp nhưng suy giảm mạnh khi tải cao. Một tối ưu có thể giảm CPU nhưng tăng sử dụng bộ nhớ. Việc đánh giá cần dựa trên **nhiều chỉ số liên quan đến mục tiêu thực tế**.

## 2. Thời gian: độ trễ, thời gian phản hồi và thông lượng

### 2.1. Độ trễ và thời gian phản hồi

Trong một API, **thời gian phản hồi** (*response time*) thường được đo từ lúc bên gọi gửi yêu cầu đến lúc nhận phản hồi theo ranh giới đo đã chọn. Thời gian này có thể gồm:

1. Chờ trong hàng đợi hoặc chờ một luồng xử lý.
2. Kiểm tra dữ liệu và xử lý nghiệp vụ trong Java.
3. Chờ cơ sở dữ liệu, bộ nhớ đệm hoặc dịch vụ bên ngoài.
4. Truyền dữ liệu qua mạng và mã hóa/giải mã thông điệp.

Khi nói **độ trễ** (*latency*), cần nêu rõ đang đo thao tác hoặc chặng nào. Độ trễ của một truy vấn SQL không tương đương với thời gian người dùng chờ toàn bộ trang.

~~~text
Yêu cầu HTTP
    |
    +-- Chờ tài nguyên / hàng đợi
    +-- Xử lý nghiệp vụ Java
    +-- Truy vấn cơ sở dữ liệu
    +-- Gọi dịch vụ bên ngoài
    +-- Tạo và truyền phản hồi
    |
Phản hồi HTTP
~~~

Chỉ tối ưu vòng lặp Java sẽ không mang lại nhiều lợi ích nếu phần lớn thời gian thực tế nằm ở truy vấn SQL hoặc cuộc gọi mạng.

### 2.2. Trung bình chưa nói lên toàn bộ trải nghiệm

Giả sử một API có thời gian phản hồi trung bình là 120 ms. Giá trị đó không cho biết một số người dùng có phải chờ nhiều giây hay không.

Các **phân vị** (*percentiles*) giúp mô tả phân bố độ trễ:

- **p50:** khoảng 50% số lần đo có thời gian không vượt quá giá trị này.
- **p95:** khoảng 95% số lần đo có thời gian không vượt quá giá trị này.
- **p99:** khoảng 99% số lần đo có thời gian không vượt quá giá trị này.

Ví dụ, nếu p95 là 400 ms thì khoảng 95% yêu cầu trong tập đo có thời gian phản hồi không quá 400 ms, còn khoảng 5% có thể lâu hơn. Phân vị cần được tính trên tập mẫu đủ lớn, với cách đo và tải rõ ràng.

Trung bình, p50, p95 và p99 đều có ích. **Độ trễ phần đuôi** (*tail latency*) cao thường gợi ý cần kiểm tra tình trạng chờ, truy vấn chậm, garbage collection hoặc các điểm nghẽn dưới tải.

### 2.3. Thông lượng và mức tải

**Thông lượng** (*throughput*) là lượng công việc hoàn thành trong một đơn vị thời gian, chẳng hạn:

- Yêu cầu HTTP hoàn thành mỗi giây (*requests/second*).
- Đơn hàng được xử lý mỗi phút.
- Bản ghi được nhập hoặc xuất mỗi giây.

Thông lượng phải đi cùng **tỉ lệ thành công và độ trễ**. Một dịch vụ trả hàng nghìn phản hồi lỗi mỗi giây không thể được coi là hiệu quả chỉ vì số yêu cầu hoàn thành cao.

**Mức tải** (*load*) mô tả nhu cầu mà hệ thống phải phục vụ: tốc độ yêu cầu đến, lượng công việc trong mỗi yêu cầu, số tác nhân đồng thời, kích thước dữ liệu hoặc kết hợp các yếu tố đó.

Khi nhu cầu tăng, tài nguyên hữu hạn như CPU, băng thông, nhóm kết nối (*connection pool*) và luồng xử lý có thể trở thành điểm nghẽn. Trước ngưỡng bão hòa, tăng thêm tải đôi khi vẫn làm thông lượng tăng. Sau đó, thời gian chờ và tỉ lệ lỗi có thể tăng nhanh trong khi thông lượng tăng rất ít hoặc giảm.

Không nên mặc định rằng tăng số thread gấp đôi sẽ giúp thông lượng tăng gấp đôi: tài nguyên chung và việc chuyển ngữ cảnh có thể làm hệ thống chậm hơn.

## 3. Tài nguyên không chỉ là CPU và RAM

| Tài nguyên | Cần theo dõi điều gì? | Ví dụ vấn đề |
| --- | --- | --- |
| CPU | Mức sử dụng, thời gian CPU, hoạt động bất thường dưới tải | Tính lại cùng dữ liệu, vòng lặp không cần thiết |
| Bộ nhớ | Heap sử dụng, số byte cấp phát, đối tượng tồn tại lâu | Đưa toàn bộ tệp lớn vào RAM, giữ tham chiếu không còn cần thiết |
| Garbage collection (GC) | Tần suất và thời gian dừng, áp lực cấp phát | Tạo quá nhiều đối tượng tạm trong đường xử lý nóng |
| Đĩa và cơ sở dữ liệu | Số lần đọc/ghi, thời gian I/O, truy vấn chậm, kết nối | Thực hiện một truy vấn cho từng phần tử của danh sách |
| Mạng | Dung lượng truyền, số lượt gọi, thời gian chờ | Gọi dịch vụ từ xa nhiều lần thay vì gom hợp lý |
| Luồng, kết nối, khóa | Số lượng đang hoạt động, thời gian chờ, tranh chấp | Giữ khóa lâu, dùng hết connection pool |

**Tài nguyên có chi phí cơ hội.** Khi một yêu cầu chiếm bộ nhớ hoặc kết nối lâu hơn cần thiết, các yêu cầu khác có thể phải chờ. Mức tiêu thụ cao cũng có thể làm tăng chi phí vận hành.

Tuy nhiên, **sử dụng tài nguyên thấp không phải lúc nào cũng là mục tiêu tối ưu**. Một dịch vụ dùng thêm RAM cho bộ đệm có thể giảm số truy vấn cơ sở dữ liệu và giảm độ trễ đáng kể. Điều cần đánh giá là lợi ích, chi phí và rủi ro của lựa chọn đó.

## 4. Hiệu quả thuật toán: ví dụ Java

Giả sử có một mảng mã đơn hàng và cần xác định **có mã nào xuất hiện ít nhất hai lần hay không**. Hai cách triển khai sau có cùng hợp đồng:

- Trả về **true** nếu tồn tại hai phần tử bằng nhau; ngược lại trả về **false**.
- Hai phần tử có giá trị **null** được tính là trùng nhau.
- So sánh chuỗi có phân biệt chữ hoa và chữ thường.
- Nếu chính mảng đầu vào là **null**, ném **NullPointerException** với thông điệp **orderIds**.

### 4.1. Cách A: so sánh từng cặp

~~~java
import java.util.Objects;

public final class DuplicateOrderIdChecker {
    private DuplicateOrderIdChecker() {}

    public static boolean hasDuplicate(String[] orderIds) {
        Objects.requireNonNull(orderIds, "orderIds");

        for (int i = 0; i < orderIds.length; i++) {
            for (int j = i + 1; j < orderIds.length; j++) {
                if (Objects.equals(orderIds[i], orderIds[j])) {
                    return true;
                }
            }
        }
        return false;
    }
}
~~~

Khi không có phần tử trùng nhau, cách này cần xét khoảng \(n(n-1)/2\) cặp cho mảng dài \(n\). Do đó:

- **Độ phức tạp thời gian:** \(O(n^2)\) trong trường hợp xấu.
- **Bộ nhớ bổ sung:** \(O(1)\), không tính đầu vào.

Đây là cách dễ hiểu và có thể phù hợp nếu mảng luôn rất nhỏ hoặc bộ nhớ bổ sung bị giới hạn nghiêm ngặt.

### 4.2. Cách B: lưu các mã đã gặp

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public final class DuplicateOrderIdChecker {
    private DuplicateOrderIdChecker() {}

    public static boolean hasDuplicate(String[] orderIds) {
        Objects.requireNonNull(orderIds, "orderIds");

        Set<String> seen = new HashSet<>();
        for (String orderId : orderIds) {
            if (!seen.add(orderId)) {
                return true;
            }
        }
        return false;
    }
}
~~~

Ở đây, **HashSet.add** trả về **false** nếu tập hợp đã chứa phần tử tương đương. **HashSet** chấp nhận một phần tử **null**, nên quy tắc hai giá trị **null** là trùng vẫn được giữ nguyên.

Trong điều kiện băm thông thường:

- **Thời gian kỳ vọng:** \(O(n)\) cho toàn bộ mảng vì mỗi lần thêm/kiểm tra trong HashSet thường có chi phí trung bình \(O(1)\).
- **Bộ nhớ bổ sung:** \(O(n)\) trong trường hợp phải lưu nhiều mã khác nhau.

Đây là một **đánh đổi thời gian lấy bộ nhớ**: cách B có thể hiệu quả hơn đáng kể khi số mã lớn, nhưng cần cấp phát tập hợp và các cấu trúc nội bộ. Với đầu vào rất nhỏ, chi phí tạo HashSet có thể khiến nó không nhanh hơn cách A. Ký hiệu Big-O mô tả xu hướng tăng trưởng, **không phải phép đo thời gian chạy thực tế**.

### 4.3. Kiểm chứng hành vi khi đổi thuật toán

Hai cách được thiết kế để giữ cùng hợp đồng. Trước khi thay đổi mã, cần kiểm thử các trường hợp:

| Đầu vào | Kết quả mong đợi | Lý do |
| --- | --- | --- |
| Mảng rỗng | false | Không có mã |
| Chỉ chứa A | false | Chỉ có một phần tử |
| A, B, A | true | Mã lặp ở vị trí không kề nhau |
| A, B, C | false | Không có mã lặp |
| null, A, null | true | Hai giá trị null trùng nhau |
| A, a | false | So sánh phân biệt chữ hoa và chữ thường |
| Mảng đầu vào null | Ném NullPointerException với thông điệp orderIds | Đầu vào không hợp lệ |

Ví dụ kiểm thử JUnit 5 cho một phần hợp đồng:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class DuplicateOrderIdCheckerTest {
    @Test
    void detectsDuplicateIncludingNullElements() {
        assertTrue(DuplicateOrderIdChecker.hasDuplicate(
                new String[] {"A", "B", "A"}));
        assertTrue(DuplicateOrderIdChecker.hasDuplicate(
                new String[] {null, "A", null}));
    }

    @Test
    void reportsNoDuplicate() {
        assertFalse(DuplicateOrderIdChecker.hasDuplicate(new String[0]));
        assertFalse(DuplicateOrderIdChecker.hasDuplicate(
                new String[] {"A", "a"}));
    }

    @Test
    void rejectsNullArray() {
        NullPointerException error = assertThrows(
                NullPointerException.class,
                () -> DuplicateOrderIdChecker.hasDuplicate(null));
        assertEquals("orderIds", error.getMessage());
    }
}
~~~

Những ca kiểm thử trên giúp bảo vệ hành vi khi thay cấu trúc dữ liệu. Chúng chưa chứng minh hiệu năng được cải thiện. Muốn kết luận cách B nhanh hơn trong hệ thống thực, phải **đo trên dữ liệu và điều kiện vận hành đại diện**.

## 5. Nút thắt thực tế thường nằm ngoài vòng lặp

Độ phức tạp thuật toán rất quan trọng, nhưng hiệu quả tổng thể còn phụ thuộc vào cách phần mềm giao tiếp với các tài nguyên khác.

### 5.1. Truy vấn cơ sở dữ liệu lặp lại

Giả sử cần hiển thị danh sách 100 đơn hàng cùng thông tin khách hàng. Một cách triển khai gọi truy vấn tìm khách hàng cho từng đơn hàng có thể phát sinh hàng trăm lượt truy vấn. Đây là một biểu hiện của vấn đề **N+1 queries**.

Hướng cải thiện có thể là dùng truy vấn **JOIN**, nạp theo lô (*batch fetching*) hoặc thay đổi cách truy xuất dữ liệu để giảm lượt đi tới cơ sở dữ liệu. Nhưng lựa chọn này cần kiểm tra tính đúng đắn, số bản ghi trả về, nguy cơ trùng hàng từ JOIN, bộ nhớ sử dụng và hiệu năng thực tế của truy vấn.

### 5.2. Xử lý dữ liệu lớn

Đọc cả tệp hàng gigabyte vào một String hoặc một danh sách trong bộ nhớ có thể gây cấp phát lớn, GC kéo dài, thậm chí hết bộ nhớ (*OutOfMemoryError*).

Nếu bài toán cho phép, xử lý theo luồng (*streaming*) hoặc theo lô giúp giới hạn lượng dữ liệu giữ cùng lúc. Ngược lại, xử lý theo lô quá nhỏ có thể tăng chi phí I/O và số lượt truy cập. Cần chọn kích thước lô phù hợp qua đo đạc.

### 5.3. Cache, đồng thời và tranh chấp

- **Cache** có thể giảm tính toán và truy vấn lặp, nhưng tốn RAM và đòi hỏi chiến lược cập nhật dữ liệu.
- **Xử lý song song** có thể khai thác nhiều lõi CPU, nhưng thêm chi phí điều phối và nguy cơ tranh chấp, đặc biệt khi công việc nhỏ.
- **Khóa đồng bộ** giúp bảo vệ trạng thái chung, nhưng nếu phạm vi khóa lớn hoặc giữ khóa trong lúc thực hiện I/O, các yêu cầu khác có thể phải chờ.
- **Giới hạn số công việc đang xử lý** đôi khi giúp hệ thống ổn định hơn bằng cách tránh sử dụng hết tài nguyên và giảm thời gian xếp hàng khó kiểm soát.

Không có kỹ thuật nào luôn nhanh hơn trong mọi ngữ cảnh; cần xác định đúng điểm nghẽn và các tác động phụ.

## 6. Đo lường để tối ưu có căn cứ

### 6.1. Bắt đầu bằng yêu cầu có thể kiểm chứng

Ví dụ, một yêu cầu phi chức năng có thể được diễn đạt như sau:

> Trong môi trường kiểm thử đã định nghĩa, với dữ liệu đại diện và mức tải ổn định 150 yêu cầu/giây, ít nhất 95% yêu cầu tìm kiếm sản phẩm thành công phải phản hồi trong 300 ms; tỉ lệ lỗi phải nằm trong ngưỡng đã thỏa thuận.

Các con số trên chỉ là **ví dụ minh họa**, không phải ngưỡng bắt buộc cho mọi dịch vụ. Yêu cầu tốt cần nêu rõ ranh giới đo, loại yêu cầu, dữ liệu, mức tải, thời gian kiểm thử, môi trường và ngưỡng chấp nhận.

### 6.2. Phân biệt các công cụ và cấp độ đo

| Cách tiếp cận | Phù hợp để trả lời | Điều cần lưu ý |
| --- | --- | --- |
| **Microbenchmark** với JMH | Cấu trúc dữ liệu hoặc hàm nhỏ nào có chi phí thấp hơn? | Cần khởi động JVM, kiểm soát JIT, GC và tránh phép đo bị tối ưu hóa sai lệch |
| **Profiler** như Java Flight Recorder | CPU, cấp phát và thời gian chờ tập trung ở đâu? | Chọn tải đại diện và hiểu chi phí đo; không chỉ nhìn một stack trace |
| **Kiểm thử tải** (*load test*) | API hoạt động thế nào khi tăng tốc độ và số lượng yêu cầu? | Cần xem đồng thời độ trễ, thông lượng, lỗi và tài nguyên |
| **Theo dõi vận hành** | Thực tế hệ thống gặp vấn đề ở tải hoặc thời điểm nào? | Cần kết hợp metric, log, trace và ngữ cảnh triển khai |

Đo một phương thức đơn lẻ với **System.nanoTime()** một lần thường **không đáng tin cậy** để so sánh các tối ưu rất nhỏ trong Java. JIT, làm nóng mã (*warm-up*), garbage collection, tải hệ điều hành và dữ liệu đầu vào có thể tạo ra sai lệch lớn. Dùng JMH cho benchmark cấp phương thức và kiểm thử tải khi mục tiêu là trải nghiệm API toàn hệ thống.

### 6.3. Ví dụ so sánh kết quả trước và sau

Bảng dưới đây là **số liệu giả định để minh họa cách đọc**, không phải kết quả benchmark thật:

| Chỉ số với cùng mức tải và dữ liệu | Trước cải tiến | Sau cải tiến | Diễn giải |
| --- | ---: | ---: | --- |
| Thời gian phản hồi p50 | 110 ms | 95 ms | Người dùng điển hình chờ ít hơn |
| Thời gian phản hồi p95 | 620 ms | 240 ms | Phần đuôi cải thiện rõ |
| Thời gian phản hồi p99 | 1.400 ms | 710 ms | Vẫn có yêu cầu chậm cần tìm hiểu |
| CPU trung bình của dịch vụ | 75% | 64% | Giảm áp lực CPU ở mức tải đã đo |
| Bộ nhớ cấp phát mỗi yêu cầu | 1,2 MB | 1,8 MB | Đánh đổi: cấp phát tăng, cần kiểm tra ảnh hưởng tới GC |
| Tỉ lệ lỗi | 0,1% | 0,1% | Chưa thấy cải thiện hay suy giảm ở chỉ số này |

Không thể kết luận “tối ưu thành công hoàn toàn” chỉ từ p95 giảm. Cần kiểm tra xem mức tăng cấp phát có làm GC xấu đi ở tải cao hơn, có hồi quy hành vi nào hay không và các lần đo có ổn định không.

### 6.4. Quy trình cải thiện hiệu quả từng bước

1. **Xác định kỳ vọng:** Hành vi cần giữ, độ trễ hoặc tài nguyên cần cải thiện, điều kiện tải và ngưỡng mục tiêu.
2. **Đo mức hiện tại:** Thu thập thời gian phản hồi, thông lượng, lỗi và tài nguyên trên khối lượng công việc đại diện. Ghi lại cấu hình để có thể đo lại.
3. **Tìm điểm nghẽn:** Dùng profiler, trace, thống kê truy vấn và metric; phân biệt thời gian tính toán với thời gian chờ.
4. **Đưa ra giả thuyết:** Ví dụ “giảm số lần truy vấn từ N xuống một nhóm nhỏ sẽ hạ p95 khi danh sách dài”.
5. **Thay đổi có kiểm soát:** Điều chỉnh thuật toán, cấu trúc dữ liệu, truy vấn hoặc cách quản lý tài nguyên; tránh sửa quá nhiều chỗ cùng lúc nếu khó quy nguyên nhân.
6. **Kiểm chứng hành vi:** Chạy kiểm thử nghiệp vụ, trường hợp biên và kiểm thử tích hợp phù hợp.
7. **Đo lại và so sánh:** Dùng cùng tải, dữ liệu, môi trường và phương pháp; đo nhiều lần khi có dao động. Xem toàn bộ chỉ số, gồm những chỉ số có thể xấu đi.
8. **Duy trì khả năng theo dõi:** Giữ các kiểm thử hồi quy và metric trọng yếu để nhận ra sự suy giảm trong các thay đổi tiếp theo.

Quy trình này nối kết **hiệu quả vận hành** với **khả năng thay đổi an toàn** của mã nguồn: một cải tiến cần có bằng chứng rằng nó giải quyết vấn đề mong muốn và không phá vỡ hợp đồng hiện tại.

## 7. Các đánh đổi thường gặp

| Lựa chọn | Lợi ích tiềm năng | Chi phí hoặc rủi ro |
| --- | --- | --- |
| Dùng HashSet để tra cứu | Tra cứu trung bình nhanh khi dữ liệu lớn | Tốn bộ nhớ; phụ thuộc đặc điểm dữ liệu và chi phí băm |
| Thêm bộ nhớ đệm | Ít tính toán, truy vấn hoặc gọi mạng lặp lại | Dữ liệu cũ, làm mới cache, bộ nhớ, phức tạp vận hành |
| Tăng tính song song | Tận dụng CPU khi công việc có thể tách | Điều phối, tranh chấp, lỗi đồng thời |
| Xử lý theo luồng | Giảm mức bộ nhớ đỉnh | Cách xử lý phức tạp hơn, không phải tác vụ nào cũng hỗ trợ |
| Gom yêu cầu hoặc truy vấn | Ít lượt I/O và round-trip | Có thể tăng độ trễ gom lô, trả dữ liệu thừa, thay đổi thứ tự |
| Tiền tính toán kết quả | Giảm chi phí ở thời điểm đọc | Tăng chi phí ghi và đồng bộ dữ liệu |

**Đánh đổi cũng liên quan tới chất lượng nội tại.** Một giải pháp tiết kiệm vài micro giây nhưng gây khó hiểu, khó kiểm thử hoặc làm tăng lỗi đồng thời có thể không xứng đáng nếu hệ thống chưa hề gặp giới hạn hiệu năng đó.

## 8. Những nhận định sai dễ gặp

**“Mã ít dòng thì nhanh hơn.”** Số dòng chủ yếu phản ánh cách diễn đạt. Tốc độ phụ thuộc vào thuật toán, cấu trúc dữ liệu, đường đi thực thi và môi trường.

**“Độ phức tạp thấp hơn chắc chắn chạy nhanh hơn.”** Big-O nói về xu hướng khi kích thước dữ liệu tăng. Hệ số hằng, cấp phát, khả năng tận dụng cache CPU và kích thước đầu vào có thể khiến giải pháp có Big-O tốt hơn chạy chậm hơn ở quy mô nhỏ.

**“CPU không cao thì không thể chậm.”** Chương trình có thể đang chờ I/O, khóa hoặc kết nối. CPU thấp có thể đi cùng độ trễ rất cao.

**“Tăng bộ nhớ luôn làm hệ thống mạnh hơn.”** Bộ nhớ lớn hơn chỉ hữu ích khi giảm được điểm nghẽn cụ thể. Giữ quá nhiều đối tượng hoặc tạo đối tượng liên tục vẫn có thể làm GC hoạt động nhiều.

**“Một kết quả benchmark là đủ.”** Kết quả cần có cách đo đúng, dữ liệu phù hợp, mức biến thiên hợp lý và khả năng tái lập; nếu không rất dễ tối ưu theo nhiễu.

**“Nhanh hơn thì chất lượng tốt hơn.”** Nếu tối ưu làm sai kết quả, mất dữ liệu hoặc giảm khả năng bảo trì quá mức, hệ thống chưa được cải thiện toàn diện.

## 9. Tình huống thực hành

Một API trả danh sách giao dịch có p95 là 1,2 giây khi có nhiều người dùng. Người phát triển thấy CPU máy chủ Java chỉ dùng 25% và đề xuất tạo thêm nhiều thread. Trong khi đó, trace của một yêu cầu cho thấy mỗi giao dịch lại gọi một truy vấn riêng để lấy tên khách hàng; khi danh sách dài, thời gian chờ cơ sở dữ liệu chiếm phần lớn thời gian phản hồi.

Hãy suy nghĩ:

1. Chỉ số nào cho thấy người dùng đang chịu ảnh hưởng? Chỉ số nào chưa đủ để kết luận nguyên nhân?
2. Giả thuyết điểm nghẽn hợp lý nhất là gì?
3. Có thể thử thay đổi nào trước khi tăng thread?
4. Sau thay đổi, cần theo dõi những gì ngoài p95?
5. Làm sao bảo đảm danh sách giao dịch vẫn có nội dung, thứ tự và quy tắc phân quyền đúng?

**Gợi ý đối chiếu:** p95 phản ánh độ trễ và cho thấy một nhóm người dùng đang phải chờ lâu; CPU 25% không loại trừ nghẽn I/O. Vết truy vấn gợi ý vấn đề N+1; có thể cân nhắc nạp dữ liệu theo lô hoặc truy vấn phù hợp, rồi so sánh trên cùng mức tải. Cần kiểm tra số truy vấn, thời gian SQL, thông lượng, lỗi, số kết nối, bộ nhớ và hợp đồng trả về. Kiểm thử tích hợp cần xác nhận đúng giao dịch, đúng người dùng và không phát sinh dữ liệu trùng hoặc thiếu.

## 10. Ghi nhớ

- Hiệu quả sử dụng thời gian và tài nguyên xem xét **thời gian hoàn thành công việc** và **tài nguyên tiêu thụ** dưới **mức tải, dữ liệu và môi trường xác định**.
- Cần phân biệt **độ trễ**, **thông lượng** và **mức sử dụng tài nguyên**; không một chỉ số riêng lẻ nào mô tả đầy đủ chất lượng.
- Phân tích thuật toán giúp dự đoán xu hướng theo kích thước đầu vào, nhưng hiệu năng thật còn phụ thuộc vào I/O, đồng thời, JVM và đặc điểm dữ liệu.
- Tối ưu phải bắt đầu từ **đo lường và giả thuyết về điểm nghẽn**, sau đó kiểm chứng bằng dữ liệu đại diện.
- Mọi tối ưu cần **bảo toàn hành vi đúng** và cân nhắc chi phí bộ nhớ, độ phức tạp, khả năng kiểm thử và bảo trì.
