# Bình luận bù cho ý định không được thể hiện trong mã

Một lập trình viên mở phương thức xử lý đơn hàng và thấy dòng:

~~~java
// Chỉ giao trong ngày cho đơn đã thanh toán, đủ hàng,
// nằm trong vùng phục vụ, không bị giữ và nhận trước 15 giờ.
if (a && b && c && !d && t.isBefore(LocalTime.of(15, 0))) {
    return true;
}
~~~

Nếu xóa bình luận, biểu thức chỉ còn những chữ cái `a`, `b`, `c`, `d` và một thời điểm không rõ ý nghĩa. Người bảo trì muốn sửa quy tắc phải đoán mỗi cờ đại diện cho điều gì, rồi tìm lại lời giải thích ở nơi khác. Bình luận đang làm công việc lẽ ra **tên gọi và cấu trúc mã** phải thực hiện.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Ở chương **Mùi mã**, bài học này tập trung vào dấu hiệu **bình luận bù cho ý định không được thể hiện trong mã** (*comments used as deodorant*): nhận diện, lý giải rủi ro và cải tiến cách biểu đạt mà **không coi mọi bình luận đều xấu**.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt bình luận lặp lại **mã đang làm gì** với bình luận ghi **vì sao** có một quyết định không hiển nhiên.
- Nhận diện trường hợp bình luận che giấu tên biến mơ hồ, cờ trạng thái không rõ, giá trị ma thuật, khối điều kiện lồng nhau và tác dụng phụ bất ngờ.
- Đưa ý định vào **tên phương thức, kiểu dữ liệu, hợp đồng API, guard clause và cấu trúc trách nhiệm**.
- Viết kiểm thử bảo vệ hành vi trước và sau khi cải tổ mã, đặc biệt tại giá trị biên và đường từ chối.
- Quyết định bình luận nào cần xóa, bình luận nào cần cập nhật và bình luận nào **phải giữ** vì chứa ngữ cảnh không thể suy ra từ mã.

## 1. Mùi mã không đồng nghĩa với lỗi đã được chứng minh

**Code smell (mùi mã)** là tín hiệu rằng một cấu trúc có thể gây khó khăn khi hiểu, kiểm thử hoặc sửa đổi. Nó **không tự động chứng minh** chương trình chạy sai và cũng không phải lệnh bắt buộc phải refactor ngay lập tức.

Với bình luận, mùi mã xuất hiện khi **mã không diễn đạt được điều đáng lẽ phải rõ với người đọc**, khiến lời giải thích bằng ngôn ngữ tự nhiên trở thành điều kiện để hiểu hành vi.

Ví dụ:

~~~java
int n = total - used; // Số lượt còn lại.
if (n > 0) {          // Nếu còn lượt.
    n--;              // Giảm đi một lượt.
}
~~~

Các bình luận trên gần như chỉ diễn đạt lại toán tử Java. Nếu đây là logic của thẻ sử dụng dịch vụ, tên có ý nghĩa sẽ giúp hơn:

~~~java
int remainingUses = totalUses - usedUses;
if (remainingUses > 0) {
    remainingUses--;
}
~~~

Tuy nhiên, ví dụ thứ hai **chưa phải mô hình đóng gói hoàn chỉnh**: nó chỉ cho thấy thay tên làm ý định dễ nhận ra hơn. Trong một lớp nghiệp vụ thật, số lượt còn lại nên được cập nhật qua thao tác có kiểm soát, không cho các nơi khác tùy ý sửa biến.

**Tín hiệu cần điều tra** là: người đọc có phải liên tục tìm bình luận để biết biến là gì và điều kiện mang ý nghĩa nào không? Câu trả lời phụ thuộc ngữ cảnh, quy ước nhóm và sự phức tạp thực của bài toán.

## 2. Bình luận “mã làm gì” khác bình luận “vì sao”

| Loại bình luận | Ví dụ | Đánh giá |
| --- | --- | --- |
| Lặp lại cú pháp | `// Tăng i lên 1` đặt trước `i++` | Thường thừa; nên xóa |
| Dịch tên kém | `// a là đơn đã thanh toán` cạnh `boolean a` | Nên đổi `a` thành tên nghiệp vụ |
| Che giá trị ma thuật | `// 2 nghĩa là đã giao` cạnh `status == 2` | Cân nhắc `enum` hoặc hằng có tên |
| Che tác dụng phụ | `// Hàm này cũng ghi database` trên `checkOrder()` | Sửa ranh giới hoặc tên/hợp đồng; comment đơn độc không đủ |
| Giải thích lựa chọn phi hiển nhiên | “Dùng giờ kho, không dùng giờ máy khách vì quy trình nhận hàng” | Có thể rất cần thiết |
| Cảnh báo về tương thích | “Không đổi thứ tự trường vì hệ thống cũ đọc theo vị trí” | Giữ nếu còn đúng; liên kết tới hợp đồng/test |
| Ghi lý do bảo mật | “Không log token vì log được xuất sang hệ thống quan sát” | Có giá trị khi giải thích ràng buộc và phạm vi |
| Javadoc hợp đồng công khai | Đầu vào, kết quả, lỗi, tính ổn định và giới hạn | Cần thiết khi người gọi phải biết điều không thấy từ chữ ký |

Một cách hỏi đơn giản:

> **Nếu xóa bình luận, người đọc còn hiểu đúng ý định của mã không?**

Nếu không, hãy xem **mã có thể được cải thiện để tự diễn đạt hay không**. Nhưng đừng áp dụng câu hỏi này như một luật “xóa mọi bình luận”: lý do nghiệp vụ, điều kiện từ hệ thống ngoài, quyết định tương thích và các đánh đổi kỹ thuật có thể **không thể** thể hiện hết qua tên biến hoặc phương thức.

## 3. Bình luận có thể làm mã khó bảo trì như thế nào?

Một bình luận bù cho tên gọi hoặc cấu trúc yếu gây ra ít nhất bốn dạng rủi ro.

**Rủi ro 1 — Có hai nguồn sự thật dễ lệch nhau.** Người phát triển sửa biểu thức nhưng quên cập nhật dòng giải thích. Bình luận vẫn nói “đúng 15 giờ được giao”, trong khi mã dùng `isBefore` và từ chối trường hợp đúng 15:00.

**Rủi ro 2 — Dễ hiểu nhầm vị trí chịu trách nhiệm.** Bình luận “đã kiểm tra quyền” ở controller có thể khiến người sửa service tưởng không cần kiểm tra quyền theo tài nguyên, dù luồng xử lý mới đi từ một job không qua controller.

**Rủi ro 3 — Review bị đánh lạc hướng.** Khi bình luận viết một ý định hợp lý, người review có thể đọc lướt và không kiểm tra biểu thức phức tạp bên dưới có thực hiện đúng ý định ấy không.

**Rủi ro 4 — Thay đổi phụ thuộc vào trí nhớ.** Người mới phải nhớ `flagA` là gì, `status == 3` là giai đoạn nào và gọi helper nào trước. Mã càng phụ thuộc vào chú thích rời rạc, người bảo trì càng khó sửa an toàn.

Đặc biệt, bình luận **không được thực thi** như quy tắc nghiệp vụ. Trình biên dịch Java và phần lớn công cụ kiểm thử không tự bảo đảm lời giải thích vẫn khớp với hành vi thật.

## 4. Ví dụ xuyên suốt: điều kiện giao hàng trong ngày

Giả sử doanh nghiệp có chính sách **giả định để minh họa**:

- Đơn đã được xác nhận thanh toán.
- Tồn kho đã được giữ đủ cho đơn.
- Địa chỉ nằm trong vùng giao trong ngày.
- Đơn không bị giữ do kiểm tra rủi ro.
- Đơn được tiếp nhận **trước 15:00 theo giờ địa phương của kho**. Đúng 15:00 đã quá hạn chốt.

Phương thức dưới đây chỉ **quyết định điều kiện**, không tự đặt hàng, xuất kho hoặc giao hàng. Quy tắc thời gian và chính sách áp dụng là giả định đã được nêu rõ cho bài học, không tự suy ra từ ứng dụng thực tế.

### 4.1. Phiên bản phụ thuộc bình luận

~~~java
import java.time.LocalTime;

public final class OldSameDayRule {
    public boolean ok(
            boolean a, boolean b, boolean c, boolean d, LocalTime t) {
        // a: đã thanh toán
        // b: đã giữ đủ hàng
        // c: địa chỉ được phục vụ
        // d: đang bị giữ do rủi ro
        // t: giờ tiếp nhận theo kho
        // Chỉ giao trong ngày nếu mọi điều kiện đều đạt trước 15:00.
        return a && b && c && !d && t.isBefore(LocalTime.of(15, 0));
    }
}
~~~

Phần logic rất ngắn nhưng chữ ký không diễn đạt được ý định. Một lời gọi như:

~~~java
boolean eligible = oldRule.ok(true, true, false, false,
    LocalTime.of(14, 30));
~~~

khó được hiểu hoặc review ngay tại chỗ. Đổi hai tham số Boolean vẫn biên dịch, có thể gây sai hành vi. Bình luận nằm trong thân phương thức không xuất hiện ở nơi gọi, nên người đọc **phải mở phần triển khai** để biết ý nghĩa.

Ngoài ra, nếu một ngày có thêm quy tắc “chỉ áp dụng cho đơn giao tiêu chuẩn”, phương thức có thể tích lũy một cờ Boolean nữa; bình luận sẽ phình ra, trong khi chữ ký vẫn khó dùng đúng.

### 4.2. Đưa khái niệm nghiệp vụ vào kiểu dữ liệu

Java 17 có thể biểu diễn các điều kiện đầu vào bằng một `record`:

~~~java
import java.time.LocalTime;
import java.util.Objects;

public record DispatchRequest(
    boolean paymentConfirmed,
    boolean inventoryReserved,
    boolean destinationServed,
    boolean fraudHold,
    LocalTime receivedAtWarehouse
) {
    public DispatchRequest {
        Objects.requireNonNull(
            receivedAtWarehouse,
            "receivedAtWarehouse"
        );
    }
}
~~~

Các trường có tên diễn đạt đúng loại dữ liệu. Người gọi tạo đối tượng qua những giá trị có thể nhận diện:

~~~java
DispatchRequest request = new DispatchRequest(
    true,                    // paymentConfirmed
    true,                    // inventoryReserved
    true,                    // destinationServed
    false,                   // fraudHold
    LocalTime.of(14, 30)
);
~~~

Đây là **bước cải thiện**, nhưng vẫn chưa phải giải pháp chống mọi nhầm lẫn: bốn Boolean liên tiếp còn có thể bị đảo. Với API công khai có tác động lớn, cân nhắc **builder có tên trường**, các đối tượng trạng thái riêng hoặc kiểu nghiệp vụ giàu ý nghĩa hơn. Không nhất thiết tạo một lớp cho mỗi Boolean nếu chi phí đó vượt lợi ích thực tế.

### 4.3. Đặt tên cho quyết định và làm rõ đường từ chối

~~~java
import java.time.LocalTime;
import java.util.Objects;

public final class SameDayDispatchPolicy {
    private static final LocalTime EXCLUSIVE_CUTOFF =
        LocalTime.of(15, 0);

    private SameDayDispatchPolicy() {
    }

    public static boolean isEligible(DispatchRequest request) {
        Objects.requireNonNull(request, "request");

        if (!request.paymentConfirmed()
                || !request.inventoryReserved()) {
            return false;
        }
        if (!request.destinationServed() || request.fraudHold()) {
            return false;
        }
        return request.receivedAtWarehouse()
            .isBefore(EXCLUSIVE_CUTOFF);
    }
}
~~~

Lúc này, **cấu trúc mã thể hiện các điều kiện cần**. Người đọc không còn phải nhớ `a`, `b`, `c`, `d` có nghĩa gì. Tên `EXCLUSIVE_CUTOFF` và `isBefore` cho thấy **đúng 15:00 bị từ chối**, còn `isEligible` nói đây là quyết định, không phải thao tác xuất kho.

Vẫn cần xem **hợp đồng thời gian**: `LocalTime` không chứa ngày hoặc múi giờ. Ở ví dụ này, giả định thời điểm đã được chuyển sang **giờ địa phương của kho** ở một ranh giới đáng tin cậy. Nếu quy tắc phải xử lý nhiều kho/múi giờ, ca qua nửa đêm hoặc ngày chuyển giờ mùa hè, mã thực tế cần mô hình thời điểm phù hợp như `Instant` và `ZoneId`, cùng kiểm thử các tình huống liên quan. Không nên chỉ đổi tên `t` thành `receivedAtWarehouse` rồi coi việc chuyển múi giờ đã được giải quyết.

### 4.4. Bình luận nào còn có ích?

Sau khi tên và cấu trúc đã rõ, một bình luận như sau không còn cần thiết:

~~~java
// Nếu chưa xác nhận thanh toán hoặc chưa giữ hàng, trả false.
if (!request.paymentConfirmed() || !request.inventoryReserved()) {
    return false;
}
~~~

Ngược lại, nếu cutoff được chọn vì quy định vận hành, hãy ghi lý do khi nó thực sự khó suy ra:

~~~java
// Đối tác vận chuyển chốt lệnh lấy hàng lúc 15:00 theo giờ kho.
// Đơn được tiếp nhận đúng 15:00 thuộc đợt tiếp theo.
private static final LocalTime EXCLUSIVE_CUTOFF =
    LocalTime.of(15, 0);
~~~

Nội dung này **chỉ nên được đưa vào production khi đã được nghiệp vụ xác nhận**. Nếu có tài liệu chính sách, ID yêu cầu hoặc bản ghi quyết định ổn định, bình luận có thể liên kết tới nguồn đó. Bình luận giải thích **vì sao chọn ranh giới** có giá trị hơn bình luận chỉ đọc lại biểu thức.

## 5. Dùng kiểu trạng thái thay cho chú thích “mã số”

Một mùi mã thường gặp:

~~~java
// 0 = mới, 1 = đã thanh toán, 2 = đang đóng gói, 3 = đã giao.
if (status == 2) {
    // Chỉ cho phép in nhãn khi đang đóng gói.
    printLabel();
}
~~~

Nếu ai đó thêm trạng thái `CANCELLED` hoặc đổi thứ tự mã số, phần chú thích và các điều kiện số học có thể lệch nhau. Có thể dùng `enum`:

~~~java
enum OrderStatus {
    NEW,
    PAID,
    PACKING,
    SHIPPED,
    CANCELLED
}

if (order.status() == OrderStatus.PACKING) {
    printLabel();
}
~~~

Từ khóa `PACKING` diễn đạt ý định mà không cần ghi `// 2 là đang đóng gói`. Nhưng **chỉ đổi `int` thành `enum` chưa bảo đảm chuyển trạng thái hợp lệ**. Nếu có quy tắc không được chuyển từ `SHIPPED` về `NEW`, cần bảo vệ qua thao tác nghiệp vụ và kiểm thử chuyển trạng thái.

Nếu dữ liệu lưu trữ hoặc giao thức bên ngoài dùng mã số có ý nghĩa cố định, hãy ánh xạ rõ mã đó sang `enum` ở ranh giới. Không được tự thay thứ tự giá trị `enum` rồi giả định thứ tự ordinal có thể dùng làm mã giao thức bền vững.

## 6. Đưa tác dụng phụ vào tên và ranh giới

Một chú thích có thể cố cảnh báo:

~~~java
// Chú ý: hàm này ghi dữ liệu vào database!
void checkCustomer(Customer customer) {
    ...
}
~~~

Tên `checkCustomer` dễ khiến người đọc nghĩ đây là truy vấn, trong khi phương thức thực tế **ghi trạng thái**. Nếu người dùng gọi nó để “kiểm tra thử”, tác dụng phụ có thể ngoài dự kiến.

Có thể tổ chức rõ:

~~~java
CustomerValidationResult validateCustomer(Customer customer);

void saveValidatedCustomer(Customer customer);
~~~

Hai chữ ký minh họa **ý định khác nhau**, chưa phải implementation. `validateCustomer` nên có hợp đồng về việc chỉ kiểm tra; `saveValidatedCustomer` là một mệnh lệnh có thể ghi dữ liệu. Việc tách chỉ hợp lý nếu thao tác nghiệp vụ thật sự cần hai trách nhiệm này và ranh giới transaction được định nghĩa đúng.

**Tên gọi không thể thay cơ chế kiểm soát.** Nếu quyền ghi cần được kiểm tra tại database transaction hoặc hệ thống lưu trữ, đổi tên phương thức không tự bảo đảm tính nguyên tử, phân quyền hay idempotency. Mục tiêu của tên là giúp người gọi **không hiểu sai hành vi**, còn các bảo đảm phải được cài đặt đúng.

## 7. Bình luận về thứ tự thao tác có thể là dấu hiệu phụ thuộc thời gian

Xét mã:

~~~java
// Phải gọi bước này trước send(), nếu không sẽ lỗi.
service.prepare();
service.send();
~~~

Một người mới không biết `prepare()` có thể bị gọi hai lần không, ai chịu trách nhiệm gọi, hay trạng thái nào được đảm bảo sau bước đầu.

Nếu nghiệp vụ cho phép, có thể thiết kế một API diễn đạt **thao tác hoàn chỉnh**:

~~~java
service.prepareAndSend(request);
~~~

Hoặc, khi có nhiều bước có ý nghĩa riêng, mô hình có thể thể hiện trạng thái qua các đối tượng hoặc phương thức chuyển trạng thái có kiểm soát:

~~~java
PreparedMessage prepared = service.prepare(request);
service.send(prepared);
~~~

Ở cách thứ hai, `send` nhận `PreparedMessage` chứ không nhận dữ liệu thô, giúp một số lỗi sai thứ tự **khó biểu diễn hơn về kiểu**. Tuy vậy, hệ thống thật còn phải xử lý trạng thái hết hạn, phát lại, gửi trùng, lỗi mạng và vòng đời tài nguyên; không nên coi kiểu dữ liệu là bảo đảm đầy đủ.

Bình luận “đừng đổi thứ tự” có thể **vẫn cần giữ** nếu ràng buộc đến từ một hệ thống ngoài hoặc một giao thức đặc biệt mà mã không thể biểu đạt hết. Nhưng nên cố gắng biến thứ tự bắt buộc thành **hợp đồng có kiểm tra**, thay vì chỉ trông vào trí nhớ người gọi.

## 8. Khi nào bình luận giải thích lý do là cần thiết?

Không phải mọi lý do đều có thể tự bộc lộ qua Java. Có những trường hợp bình luận là thành phần thiết kế quan trọng:

| Ngữ cảnh | Bình luận có giá trị khi chứa | Việc nên làm kèm theo |
| --- | --- | --- |
| **Quy tắc nghiệp vụ khó suy ra** | Nguồn quyết định, giới hạn, ngày hiệu lực | Test biên và tài liệu chính sách |
| **Tương thích ngược** | Vì sao giữ một hành vi có vẻ bất thường | Contract test với client cũ, kế hoạch loại bỏ |
| **Bảo mật** | Giả định trust boundary, dữ liệu không được log, nguyên nhân cần kiểm tra quyền | Kiểm thử phủ định và code review |
| **Hiệu năng/đồng thời** | Vì sao chọn thuật toán hoặc thứ tự khóa đặc biệt | Benchmark/test đồng thời và mô tả phạm vi |
| **Giao thức ngoài** | Thứ tự trường hoặc cách serialize bắt buộc | Integration/contract tests |
| **Workaround có hạn sử dụng** | Lỗi thư viện/đối tác, phạm vi và điều kiện gỡ bỏ | Ticket hoặc issue có người phụ trách |
| **Lý do không làm một việc hiển nhiên** | Vì sao tránh cache, tránh retry hoặc tránh sửa dữ liệu ở ranh giới nào đó | Kiểm tra tác dụng phụ và tài liệu kiến trúc |

Ví dụ có thể đáng giữ nếu đã được xác minh:

~~~java
// Không retry thao tác chuyển tiền chỉ vì mất phản hồi:
// đối tác có thể đã xử lý thành công. Phải đối soát theo requestId
// trước khi phát sinh một yêu cầu mới.
~~~

Lời giải thích trên không nên thay thế thiết kế retry/idempotency, nhưng nó lưu **lý do vì sao cách làm tưởng tiện là nguy hiểm**. Đây là kiến thức người đọc khó suy ra chỉ từ một dòng `return`.

Một bình luận tốt nên **đúng, ngắn gọn ở đúng nơi, có thể xác minh và ít lệ thuộc vào chi tiết dễ thay đổi**. Nếu không thể biết ai xác nhận hoặc vì sao tồn tại, hãy tìm nguồn trước khi xóa một bình luận lạ trong vùng có rủi ro cao.

## 9. Bình luận lỗi thời có thể nguy hiểm hơn không có bình luận

Giả sử mã ban đầu:

~~~java
// Đúng 15:00 vẫn được giao trong ngày.
return !receivedAt.isAfter(LocalTime.of(15, 0));
~~~

Sau khi chính sách thay đổi, lập trình viên sửa:

~~~java
// Đúng 15:00 vẫn được giao trong ngày.
return receivedAt.isBefore(LocalTime.of(15, 0));
~~~

Mã mới từ chối đúng 15:00 nhưng lời giải thích vẫn nói ngược lại. Người review đọc bình luận có thể tưởng hành vi chưa đổi.

Quy trình đúng:

1. **Xác nhận quy tắc mới và thời điểm hiệu lực** với nguồn có thẩm quyền.
2. **Cập nhật mã** theo hợp đồng mới.
3. **Cập nhật test** cho trước, đúng và sau ranh giới.
4. **Cập nhật hoặc xóa bình luận** không còn đúng; nếu cần, thay bằng lời giải thích nguyên nhân của quyết định mới.
5. **Cập nhật tài liệu/API** khi thay đổi ảnh hưởng người gọi.

Không được “sửa” sự bất đồng chỉ bằng cách đổi bình luận cho giống mã nếu **mã thật ra đang sai so với yêu cầu**. Khi nguồn thông tin mâu thuẫn, cần đối chiếu hợp đồng nghiệp vụ, không mặc định mã hoặc comment luôn đúng.

## 10. Kiểm thử sau refactor: bảo vệ hành vi trước khi xóa bình luận

Refactor nhằm cải thiện cách diễn đạt mà **không làm thay đổi hành vi đã cam kết**. Nếu chỉ nhìn tên và xóa comment, rất dễ vô tình đổi điều kiện, ví dụ đổi `<` thành `<=` hoặc đổi thứ tự xử lý khi các điều kiện có tác dụng phụ.

Với `SameDayDispatchPolicy`, test cần bắt đầu từ **bảng quy tắc nghiệp vụ**, không sao chép biểu thức hiện tại:

| Thanh toán | Giữ hàng | Vùng phục vụ | Giữ rủi ro | Giờ kho | Đủ điều kiện? |
| --- | --- | --- | --- | --- | --- |
| Có | Có | Có | Không | 14:59:59 | Có |
| Có | Có | Có | Không | **15:00:00** | **Không** |
| Có | Có | Có | Không | 15:00:01 | Không |
| Không | Có | Có | Không | 14:00 | Không |
| Có | Không | Có | Không | 14:00 | Không |
| Có | Có | Không | Không | 14:00 | Không |
| Có | Có | Có | Có | 14:00 | Không |

### Ví dụ JUnit 5

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.LocalTime;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class SameDayDispatchPolicyTest {
    @ParameterizedTest
    @CsvSource({
        "true,  true,  true,  false, 14:59:59, true",
        "true,  true,  true,  false, 15:00:00, false",
        "true,  true,  true,  false, 15:00:01, false",
        "false, true,  true,  false, 14:00:00, false",
        "true,  false, true,  false, 14:00:00, false",
        "true,  true,  false, false, 14:00:00, false",
        "true,  true,  true,  true,  14:00:00, false"
    })
    void respectsSameDayDispatchRules(
            boolean paymentConfirmed,
            boolean inventoryReserved,
            boolean destinationServed,
            boolean fraudHold,
            String warehouseTime,
            boolean expected) {
        DispatchRequest request = new DispatchRequest(
            paymentConfirmed,
            inventoryReserved,
            destinationServed,
            fraudHold,
            LocalTime.parse(warehouseTime)
        );

        assertEquals(
            expected,
            SameDayDispatchPolicy.isEligible(request)
        );
    }

    @Test
    void rejectsMissingRequestAndTime() {
        assertThrows(
            NullPointerException.class,
            () -> SameDayDispatchPolicy.isEligible(null)
        );
        assertThrows(
            NullPointerException.class,
            () -> new DispatchRequest(true, true, true, false, null)
        );
    }
}
~~~

Khi cài đặt mới khác cấu trúc cũ, bộ test này có thể **bảo vệ hành vi có ý nghĩa**. Đặc biệt, ca đúng 15:00 giúp phát hiện lỗi ở ranh giới mà những kiểm thử chỉ có 14:00 và 16:00 có thể bỏ sót.

Tuy nhiên, test trên **không chứng minh toàn bộ tính đúng đắn**. Nó giả định `LocalTime` đã biểu diễn đúng giờ kho và chưa kiểm tra chuyển đổi từ timestamp của HTTP, nhiều múi giờ, ngày lễ hoặc trường hợp đồng thời. Nếu sản phẩm thật yêu cầu chúng, cần thêm kiểm thử ở ranh giới thích hợp.

### Bình luận và test có vai trò khác nhau

Một bình luận `// Đúng 15:00 không được nhận` có thể thông báo ý định, nhưng **không tự thất bại** khi mã đổi sang `<=`. Test đúng giá trị biên có assertion sẽ báo sai khác. Ngược lại, test không tự cho biết **vì sao** doanh nghiệp chọn 15:00. Muốn bảo trì tốt, cần **mã diễn đạt hành vi, test kiểm chứng các ca quan trọng và tài liệu/bình luận giải thích lý do**.

## 11. Phân biệt refactor với thay đổi nghiệp vụ

Một số thay đổi nhìn giống làm sạch code nhưng thật ra có thể đổi hợp đồng:

| Thay đổi | Có thể chỉ là refactor nếu... | Rủi ro cần xem |
| --- | --- | --- |
| `a` → `paymentConfirmed` | Tên mới phản ánh đúng nguồn và ngữ nghĩa dữ liệu | Có phải `a` thực chất là “đã ủy quyền thanh toán” chứ chưa thu tiền? |
| `status == 2` → `OrderStatus.PACKING` | Mã số 2 đúng là PACKING ở mọi nơi liên quan | Mapping DB/API hoặc quy tắc lịch sử khác |
| Thay điều kiện lồng nhau bằng guard clause | Giữ nguyên thứ tự đánh giá và kết quả | Tác dụng phụ hoặc lỗi được ném ở những điều kiện cũ |
| Trích xuất một khối thành helper có tên | Dữ liệu đầu vào và tác dụng phụ không thay đổi | Scope, transaction, exception, đồng thời |
| Xóa comment “không gọi hai lần” | Đã có ràng buộc idempotency hoặc kiểm soát khác | Gọi lại có thể tạo tác dụng phụ trùng |
| Sửa `<` thành `<=` | **Không phải** refactor khi thay hành vi biên | Cần xác nhận thay đổi chính sách và test mới |

Đặc biệt, nếu điều kiện là **hàm có tác dụng phụ** hoặc có thể ném ngoại lệ, đổi thứ tự trong biểu thức `&&` có thể đổi hành vi vì Java dùng **short-circuit evaluation**. Ví dụ `isAuthorized() && charge()` khác `charge() && isAuthorized()`: phiên bản thứ hai có thể thực hiện thu tiền trước khi xác minh quyền. Không được coi hai cách viết là tương đương chỉ vì phép logic Boolean có tính giao hoán khi xét trên các giá trị thuần.

Một refactor an toàn cần biết **hành vi nào là hợp lệ**, có kiểm thử đủ ở đường quan trọng và review ảnh hưởng tới I/O, ngoại lệ, trạng thái và concurrency khi các yếu tố đó hiện diện.

## 12. Không phải “thêm tên” lúc nào cũng làm mã rõ hơn

Một cách phản ứng thái quá là biến mỗi toán tử thành một helper:

~~~java
private static boolean isBeforeFifteen(LocalTime time) {
    return time.isBefore(LocalTime.of(15, 0));
}

private static boolean isPaid(DispatchRequest request) {
    return request.paymentConfirmed();
}
~~~

Những helper này có thể giúp nếu đại diện cho **khái niệm nghiệp vụ được tái sử dụng** và được đặt tên đúng. Nhưng nếu mục đích chỉ để che một phép so sánh đơn giản, người đọc có thể phải chuyển qua nhiều phương thức để hiểu một điều vốn đã rõ.

**Độ trừu tượng tốt giảm lượng thông tin phải giữ trong đầu.** Một helper như `isEligibleForSameDayDispatch` có ý nghĩa nếu nó đóng gói một quy tắc hoàn chỉnh; một loạt helper chỉ lặp lại getter không nhất thiết cải thiện thiết kế.

Hãy đánh giá:

- Người đọc hiểu **ý định nghiệp vụ** nhanh hơn không?
- Khi quy tắc thay đổi, có một vị trí chịu trách nhiệm rõ ràng không?
- Test có thể kiểm tra một hợp đồng có ý nghĩa mà không phụ thuộc tên helper nội bộ không?
- Có thêm điều kiện, lớp hoặc định tuyến khiến mã khó theo dõi hơn không?
- Tên mới có thật sự đúng với hành vi, kể cả ca lỗi và ngoại lệ không?

Mục tiêu không phải xóa sạch comment, cũng không phải tăng số phương thức, mà là giúp **mã thực hiện ý định rõ ràng và có thể xác minh**.

## 13. Quy trình xử lý mùi mã trong code review

Khi thấy một bình luận dài giải thích khối code bên dưới, có thể tiến hành:

1. **Đọc bình luận như một giả thuyết về ý định.** Đừng lập tức tin rằng mã đang làm đúng điều đó.
2. **Xác định hợp đồng thực tế.** Tên miền nghiệp vụ, đầu vào, kết quả, tác dụng phụ, giá trị biên và nguồn quy tắc.
3. **So sánh lời giải thích với hành vi.** Có điều kiện nào bị đảo, bỏ sót hoặc không còn đúng?
4. **Nhận diện nguyên nhân khó hiểu.** Tên mơ hồ, cờ Boolean liên tiếp, magic number, hàm làm quá nhiều việc, phụ thuộc ngầm hay logic lồng nhau?
5. **Tạo bằng chứng trước khi sửa.** Viết/kiểm tra test cho hành vi được cam kết; với mã cũ, phân biệt test ghi nhận hành vi hiện tại và test xác nhận yêu cầu đúng.
6. **Refactor phạm vi nhỏ.** Đổi tên, trích xuất khái niệm nghiệp vụ, giới hạn tác dụng phụ, đưa điều kiện về đúng trách nhiệm; tránh thay đồng thời quá nhiều thứ.
7. **Giữ bình luận thật sự cần thiết.** Bảo toàn lời giải thích **vì sao**, nguồn quyết định và cảnh báo về hệ thống ngoài; bỏ bình luận chỉ lặp cú pháp hoặc đã lỗi thời.
8. **Đọc lại và chạy kiểm chứng phù hợp.** Review diff, test unit/integration liên quan, bảo đảm không đổi API hoặc trạng thái khi chưa được chấp thuận.

### Một gợi ý nhận xét review

Thay vì:

> “Bình luận này dài quá, xóa đi.”

Có thể nhận xét:

> “Hiện người gọi chỉ thấy `ok(a, b, c, d, t)`, còn ý nghĩa tham số phải đọc từ comment trong thân hàm. Có thể dùng tên theo nghiệp vụ và một đối tượng request để tránh đảo các cờ không? Trước khi đổi, nên có test cho các điều kiện từ chối và ranh giới đúng 15:00. Phần bình luận nêu lý do cutoff có thể giữ nếu đã được xác nhận.”

Một nhận xét tốt đưa ra **vấn đề, tác động, hướng thay đổi và cách giữ hành vi**, không chỉ yêu cầu chỉnh lại thẩm mỹ.

## 14. Các tình huống thường bị đánh giá sai

| Tình huống | Kết luận vội vàng | Cách nhìn phù hợp |
| --- | --- | --- |
| Mã có nhiều bình luận | “Mã có smell vì comment nhiều” | Xem mỗi bình luận có truyền đạt lý do hay đang che tên kém |
| Một hàm không có comment | “Mã tự giải thích nên tốt” | Hàm có thể vẫn sai, có tác dụng phụ ẩn hoặc thiếu hợp đồng |
| Comment dùng từ nghiệp vụ nhưng code dùng biến mơ hồ | “Người mới cứ đọc comment là đủ” | Đưa từ nghiệp vụ vào tên/kiểu để thấy ngay ở nơi gọi |
| Một workaround được giải thích rất dài | “Xóa cho mã sạch” | Xác minh rủi ro tương thích, điều kiện gỡ bỏ và test trước |
| Formatter/linter không báo cảnh báo | “Bình luận đã đúng” | Công cụ cú pháp không tự kiểm chứng toàn bộ ý nghĩa nghiệp vụ |
| Trích mọi điều kiện thành helper | “Điểm complexity giảm nên dễ đọc hơn” | Đánh giá tổng mức khó theo dõi và sự phân tán quy tắc |
| Xóa comment sau khi rename | “Đã refactor xong” | Cần kiểm chứng hành vi, đường lỗi và thay đổi tài liệu nếu cần |

Mùi mã là **lời mời điều tra một thiết kế**, không phải một danh sách quy tắc áp dụng bất chấp bối cảnh.

## 15. Bài tập tự kiểm tra

Một dịch vụ có phương thức sau:

~~~java
boolean canClose(int s, boolean a, boolean b) {
    // s = 1 nghĩa là đơn đang xử lý.
    // a = đã thanh toán.
    // b = còn tranh chấp chưa giải quyết.
    // Chỉ đóng đơn đang xử lý nếu đã thanh toán và không còn tranh chấp.
    return s == 1 && a && !b;
}
~~~

**Câu hỏi A.** Bình luận nào đang bù cho ý định không thể đọc từ tên và kiểu dữ liệu? Dấu hiệu nào có thể khiến lời giải thích lỗi thời?

**Câu hỏi B.** Đề xuất tên và kiểu Java để điều kiện được nhận diện ngay từ chữ ký và cách gọi.

**Câu hỏi C.** Nếu hệ thống thật bắt buộc kiểm tra quyền người thực hiện và cập nhật database trong một transaction, có đủ để chỉ đổi tên `canClose` thành `closeOrder` không? Vì sao?

**Câu hỏi D.** Những test nào cần có trước khi refactor điều kiện trên?

### Gợi ý đáp án

**A.** Cả ba bình luận mô tả `s`, `a`, `b` đang diễn giải hộ kiểu dữ liệu và tên kém. Bình luận quy tắc có thể hữu ích để hiểu yêu cầu ban đầu, nhưng khi code rõ hơn thì không cần lặp điều kiện. Nếu mã trạng thái `1` đổi nghĩa hoặc bổ sung trạng thái mới, comment có thể không được cập nhật theo.

**B.** Có thể dùng:

~~~java
enum OrderStatus {
    NEW,
    PROCESSING,
    CLOSED,
    CANCELLED
}

record CloseEligibility(
    OrderStatus status,
    boolean paymentConfirmed,
    boolean unresolvedDispute
) {
    CloseEligibility {
        java.util.Objects.requireNonNull(status, "status");
    }
}

boolean canClose(CloseEligibility order) {
    return order.status() == OrderStatus.PROCESSING
        && order.paymentConfirmed()
        && !order.unresolvedDispute();
}
~~~

Trong ví dụ trên, `canClose` là phương thức minh họa logic và sẽ cần đặt trong một lớp phù hợp của dự án. Nếu các cờ có những trạng thái không hợp lệ hoặc đi cùng quy tắc phức tạp, cần mô hình hóa thêm thay vì chỉ đổi tên.

**C.** Không đủ. Tên `closeOrder` gợi ý thao tác **thay đổi trạng thái**, nhưng phương thức đang trả về một Boolean và không kiểm tra quyền hay ghi dữ liệu. Để thực hiện đóng đơn thật, cần API mệnh lệnh riêng, kiểm tra quyền, bất biến và transaction nhất quán. Đổi tên không thay thế cài đặt.

**D.** Ít nhất phải có test đơn `PROCESSING`, đã thanh toán, không tranh chấp → `true`; và mỗi lý do từ chối riêng: trạng thái khác `PROCESSING`, chưa thanh toán, còn tranh chấp → `false`. Nếu quy tắc có giá trị thiếu hoặc nguồn dữ liệu ngoài, thêm test theo hợp đồng đó. Sau khi cải tổ, đối chiếu kết quả trên những ca đã được xác nhận và xem có thay đổi hành vi ngoài ý muốn không.

## Ghi nhớ

**Bình luận bù cho ý định không thể hiện trong mã** là một mùi mã: người đọc phải dựa vào lời giải thích để hiểu biến, điều kiện hoặc tác dụng phụ mà tên và cấu trúc lẽ ra phải nói rõ. Hướng cải thiện thường là **đổi tên theo nghiệp vụ, chọn kiểu dữ liệu phù hợp, làm rõ trách nhiệm và kiểm thử hành vi**, thay vì chỉ thêm nhiều dòng giải thích.

Nhưng bình luận vẫn rất có giá trị khi ghi **lý do, giả định, đánh đổi, quyết định tương thích và ràng buộc của hệ thống ngoài**. Mã tốt không phải mã không có comment; đó là mã **thể hiện rõ điều đang làm**, có kiểm thử cho các cam kết quan trọng và lưu đủ ngữ cảnh để người khác hiểu **vì sao** nó được thiết kế như vậy.
