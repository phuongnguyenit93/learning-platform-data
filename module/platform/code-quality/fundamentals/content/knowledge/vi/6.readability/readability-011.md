# Đọc một đoạn mã dưới góc nhìn người mới tiếp nhận

> **Chương:** Khả năng đọc  
> **Học phần:** Code Quality Fundamentals (`CODE_QUALITY_FUNDAMENTALS`) — hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Đọc một đoạn mã chưa quen theo **mục tiêu hành vi**, thay vì cố ghi nhớ toàn bộ cú pháp hoặc cấu trúc dự án.
2. Xác định **đầu vào, đầu ra, trạng thái, tác dụng phụ, phụ thuộc, điều kiện biên** và các quy tắc nghiệp vụ đang được mã thực hiện.
3. Phân biệt **điều có thể chứng minh từ mã**, **giả định cần kiểm tra** và **câu hỏi chưa có bằng chứng**.
4. Diễn giải một luồng Java bằng ngôn ngữ dễ hiểu, mô phỏng một số trường hợp cụ thể và tìm điểm dễ gây hiểu nhầm.
5. Ghi lại kết quả tiếp nhận mã đủ ngắn gọn để thực hiện thay đổi an toàn, đồng thời đề xuất cải thiện khả năng đọc có căn cứ.

## 1. “Dễ đọc” phải được nhìn từ người chưa biết mã

Người viết thường nhớ vì sao một biến được đặt tên như vậy, một nhánh `if` tồn tại hoặc một lời gọi có tác dụng phụ. Người mới tiếp nhận không có sẵn bối cảnh đó. Họ phải tìm cách trả lời những câu hỏi cơ bản:

- Chức năng này có nhiệm vụ gì, ai gọi nó và kết quả nào được xem là đúng?
- Dữ liệu nào đi vào, được biến đổi thế nào rồi đi ra đâu?
- Quy tắc nào đến từ nghiệp vụ, quy tắc nào là chi tiết kỹ thuật?
- Điều gì xảy ra nếu đầu vào bất thường, lời gọi bên ngoài lỗi hoặc người dùng thao tác hai lần?
- Nếu sửa một điều kiện, phần nào khác có thể bị ảnh hưởng?

**Khả năng đọc (readability)** là mức dễ dàng để người đọc xây dựng một mô hình tinh thần **đúng** về hành vi và ý định của mã. Nó liên quan chặt chẽ đến *understandability*, nhưng không đồng nghĩa với việc câu lệnh phải ngắn hoặc chỉ dùng cú pháp quen thuộc. Mã ngắn mà buộc người đọc đoán nhiều giả định có thể khó đọc hơn một đoạn dài hơn nhưng diễn đạt ranh giới và quy tắc rõ ràng.

Mục đích khi tiếp nhận mã là **hiểu đủ chính xác để làm việc**, không phải ngay lập tức đánh giá tác giả hay đổi toàn bộ phong cách viết.

### Chi phí nhận thức của một đoạn mã

| Điều người đọc phải làm | Dấu hiệu gây tốn công | Dấu hiệu giúp đọc nhanh |
| --- | --- | --- |
| Nhận diện ý định | Hàm `run()`, `doIt()`, biến `x`, `tmp` | Tên nêu mục đích: `calculateAmountDue()`, `expiresAt` |
| Theo luồng điều khiển | Nhiều nhánh lồng nhau, `return` nằm rải rác | Điều kiện có nghĩa rõ và điểm thoát dễ tìm |
| Theo dữ liệu | Một biến bị thay đổi nhiều lần, đơn vị không rõ | Giá trị trung gian có tên và đơn vị rõ |
| Theo tác dụng phụ | Câu lệnh đọc dữ liệu, ghi DB, gọi mạng bị trộn | Ranh giới tính toán và I/O nhìn thấy được |
| Kiểm tra giả định | “Ai cũng biết” đầu vào hợp lệ | Có hợp đồng, validation và ví dụ trường hợp biên |
| Tìm ngữ cảnh | Logic phụ thuộc nhiều hàm ẩn và global state | Các phụ thuộc thể hiện qua tham số/constructor |

Những dấu hiệu này **không phải quy tắc tuyệt đối**. Một thuật toán vốn phức tạp không thể tự biến thành đơn giản chỉ nhờ đổi tên biến; đôi khi việc tách quá nhiều hàm khiến người đọc phải chuyển file liên tục. Hãy đánh giá mức dễ hiểu bằng **công việc đọc thật**.

## 2. Đặt mục tiêu đọc trước khi đi vào từng dòng

Người mới tiếp nhận dễ rơi vào hai cực: đọc từ đầu đến cuối không có mục tiêu, hoặc thấy một chi tiết lạ là lập tức sửa. Trước khi xem kỹ đoạn mã, nên xác định câu hỏi cần trả lời.

Ví dụ bạn nhận yêu cầu: “Hãy xác minh cách hệ thống tính tiền thanh toán cho khách VIP khi có mã giảm giá.” Mục tiêu đọc lúc này là:

1. Xác định hàm thực sự tính số tiền.
2. Tìm điều kiện áp dụng ưu đãi, thứ tự tính và cách làm tròn.
3. Hiểu số tiền được truyền tới đâu và ghi lại ở đâu.
4. Biết những trường hợp chưa có bằng chứng để hỏi người phụ trách nghiệp vụ.

Chưa cần hiểu toàn bộ framework, hệ thống đăng nhập hay cấu hình triển khai nếu chúng không ảnh hưởng đến câu hỏi đang xử lý. Tuy nhiên, phải mở rộng phạm vi khi phát hiện phụ thuộc có thể thay đổi kết quả.

**Đơn vị cần đọc** nên là một lát cắt hành vi: từ điểm gọi và dữ liệu vào, đi qua quy tắc chính, tới kết quả hoặc tác dụng phụ. Người đọc có thể phác thảo:

~~~text
Yêu cầu sử dụng tính năng
      ↓
Điểm vào / caller
      ↓
Hàm chịu trách nhiệm chính
      ↓
Các phép tính và quyết định
      ↓
Lời gọi ngoài / ghi dữ liệu
      ↓
Kết quả, lỗi và trạng thái quan sát được
~~~

Luồng trên giúp xác định **đọc tiếp ở đâu** thay vì đi ngẫu nhiên theo cây thư mục.

## 3. Ví dụ xuyên suốt: tiếp nhận một đoạn mã Java tính tiền đơn hàng

Giả sử bạn mới tham gia nhóm và được giao tìm hiểu phương thức `checkout`. Bên dưới là ví dụ giả định, viết để học cách đọc và nhận diện thông tin còn thiếu. Các kiểu `Customer`, `Line`, `Payment` và `Order` được khai báo giản lược để nhìn rõ hợp đồng:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.List;

record Customer(long id, boolean vip, String paymentToken) {}
record Line(long unitPriceVnd, int quantity) {}
record Payment(String reference) {}
record Order(long customerId, long amountVnd,
             Instant paidAt, String paymentReference) {}
record Receipt(String paymentReference, long amountVnd) {}

interface PaymentGateway {
    Payment charge(String paymentToken, long amountVnd);
}

interface OrderStore {
    void save(Order order);
}

final class CheckoutService {
    private final PaymentGateway gateway;
    private final OrderStore store;
    private final Clock clock;

    CheckoutService(PaymentGateway gateway, OrderStore store, Clock clock) {
        this.gateway = gateway;
        this.store = store;
        this.clock = clock;
    }

    Receipt checkout(Customer customer, List<Line> lines, String code) {
        long s = 0L;

        for (Line line : lines) {
            s += line.unitPriceVnd() * line.quantity();
        }

        if (customer.vip() && s > 1_000_000L) {
            s = s * 90 / 100;
        }
        if ("SAVE50".equals(code)) {
            s -= 50_000L;
        }

        Payment payment = gateway.charge(customer.paymentToken(), s);
        store.save(new Order(
                customer.id(), s, Instant.now(clock), payment.reference()));

        return new Receipt(payment.reference(), s);
    }
}
~~~

Đoạn mã này ngắn, nhưng người mới vẫn phải dựng lại khá nhiều ý nghĩa. Thay vì bắt đầu bằng việc đổi `s` thành tên khác, hãy đọc theo các lớp thông tin sau.

### 3.1. Đọc “khung” trước: chữ ký và các phụ thuộc

Từ chữ ký:

~~~java
Receipt checkout(Customer customer, List<Line> lines, String code)
~~~

ta biết **dữ liệu nhận vào về mặt kiểu** là một khách hàng, danh sách dòng hàng và mã khuyến mãi; hàm trả một `Receipt`. Nhưng chưa biết `customer` có thể là `null` không, danh sách có rỗng không, số lượng âm có hợp lệ không, hay `code` có phân biệt chữ hoa/chữ thường không.

Từ constructor và các trường:

~~~java
private final PaymentGateway gateway;
private final OrderStore store;
private final Clock clock;
~~~

ta biết hàm có khả năng **gọi hệ thống thanh toán**, **lưu đơn** và **đọc thời gian**. `final` ở đây chỉ nghĩa là tham chiếu tới các phụ thuộc không được gán lại; nó **không bảo đảm bản thân các đối tượng phụ thuộc là bất biến hoặc thread-safe**.

Chưa cần mở sâu từng lớp ngay. Hãy ghi nhận rằng `checkout` có tác dụng phụ và cần tìm hợp đồng của `PaymentGateway.charge` cùng `OrderStore.save` khi đánh giá lỗi hoặc retry.

### 3.2. Đọc luồng điều khiển thành câu

Có thể diễn giải đúng theo thứ tự hiện tại:

1. Tạo biến `s` ban đầu bằng 0.
2. Duyệt các dòng hàng, cộng `đơn giá VND × số lượng` vào `s`.
3. Nếu khách là VIP **và tổng ban đầu lớn hơn 1.000.000 VND**, lấy `s × 90 / 100`.
4. Nếu mã đúng chuỗi `SAVE50`, trừ tiếp 50.000 VND.
5. Gọi `gateway.charge` với token thanh toán và số tiền sau giảm.
6. Sau khi nhận `Payment`, lưu `Order` với thời điểm lấy từ `clock`.
7. Trả `Receipt` chứa tham chiếu thanh toán và số tiền.

Đây là **hành vi quan sát được từ code**, chưa phải chứng nhận rằng nó khớp chính sách kinh doanh. Nếu chính sách thực tế là “từ 1.000.000 trở lên”, điều kiện `>` có thể cần sửa thành `>=`; nhưng người mới chưa được phép tự suy luận đặc tả từ trực giác.

### 3.3. Ghi tên gọi và ý nghĩa của dữ liệu

| Biểu thức trong mã | Ý nghĩa có thể xác nhận | Điều cần hỏi thêm |
| --- | --- | --- |
| `s` trước điều kiện VIP | Tổng của `unitPriceVnd() * quantity()` | Giá đã gồm thuế/phí chưa? Số lượng âm có được phép? |
| `s > 1_000_000L` | Chỉ giảm VIP khi tổng **lớn hơn** ngưỡng | Chính sách có gồm đúng ngưỡng không? |
| `s * 90 / 100` | Giữ lại 90% theo phép toán số nguyên | Làm tròn xuống có đúng quy định không? Có nguy cơ tràn ở `s * 90` không? |
| `"SAVE50".equals(code)` | So sánh đúng nội dung, có phân biệt hoa/thường; `code = null` trả `false` | Có cần chuẩn hóa khoảng trắng hoặc chữ hoa không? |
| `gateway.charge(..., s)` | Có lời gọi thanh toán với giá trị `s` | Khi timeout thì giao dịch đã diễn ra chưa? Có idempotency không? |
| `store.save(...)` | Lưu đơn sau lời gọi thanh toán thành công theo luồng hiện tại | Nếu lưu lỗi thì trạng thái thanh toán được xử lý ra sao? |

Đừng chỉ viết ghi chú kiểu “`s` là tổng tiền”. Vì `s` thay đổi ý nghĩa sau từng phép giảm, chính xác hơn nên phân biệt **subtotal**, **số tiền sau ưu đãi VIP** và **amount due**. Một tên biến duy nhất cho ba giai đoạn làm người đọc phải theo dõi lại lịch sử gán.

## 4. Mô phỏng dữ liệu cụ thể để xác nhận mình hiểu

Một cách đọc hiệu quả là tự lập bảng một vài đầu vào và **tính bằng tay theo đúng thứ tự câu lệnh**. Đừng bắt đầu bằng những trường hợp phức tạp nhất.

Với `Line(1_100_000L, 1)`, khách VIP và mã `SAVE50`:

~~~text
s ban đầu              = 0
s sau khi cộng dòng    = 1.100.000
VIP: 1.100.000 > 1.000.000 → đúng
s sau VIP              = 1.100.000 × 90 / 100 = 990.000
SAVE50                 = 990.000 - 50.000 = 940.000
gateway.charge(..., 940.000)
store.save(..., 940.000)
Receipt(..., 940.000)
~~~

Bảng quan sát từ đoạn mã (giả định các phụ thuộc hoạt động thành công):

| Tổng ban đầu | VIP | Mã | Số tiền được đưa tới `charge` | Điều cần chú ý |
| ---: | :---: | --- | ---: | --- |
| 900.000 | Có | Không có | 900.000 | Không đạt ngưỡng VIP |
| 1.000.000 | Có | Không có | 1.000.000 | Đúng ngưỡng vẫn không giảm vì `>` |
| 1.100.000 | Có | `SAVE50` | 940.000 | Giảm VIP trước, rồi trừ cố định |
| 30.000 | Không | `SAVE50` | -20.000 | Mã hiện tại có thể đưa số âm cho cổng thanh toán |
| 1.100.000 | Không | `SAVE50` | 1.050.000 | Mã giảm cố định áp dụng khi không phải VIP |

Trong bảng trên, **-20.000** là kết quả phép tính nhìn thấy được, không có nghĩa `PaymentGateway` sẽ chấp nhận số âm. Ta chưa biết gateway trả lỗi, từ chối hay điều chỉnh. Đó là một **khoảng trống phải kiểm tra**, đồng thời cho thấy vì sao cần tìm dấu hiệu xác thực đầu vào.

Ngoài giá trị mẫu, thử đi qua các ranh giới quan trọng:

- `lines = null`, danh sách rỗng, phần tử `null`, `quantity = 0` hoặc âm.
- Tổng ngay dưới, đúng bằng và ngay trên mốc VIP.
- Mã `save50`, `" SAVE50 "`, chuỗi rỗng và `null`.
- Số lượng hoặc đơn giá đủ lớn để phép nhân/cộng `long` bị tràn.
- Gateway lỗi, store lỗi, lời gọi timeout, hủy request hoặc gọi lại cùng một yêu cầu.

Không nhất thiết trường hợp nào cũng được hỗ trợ. **Điều quan trọng là biết chương trình hiện xử lý chúng ra sao và hợp đồng mong đợi là gì.**

## 5. Đọc theo ba lớp: dữ kiện, giả định, câu hỏi

Khi chưa quen dự án, hãy tạo bảng ghi chú ngắn để tránh biến suy đoán thành sự thật:

| Loại | Ví dụ | Cách ghi |
| --- | --- | --- |
| **Dữ kiện từ mã** | `store.save` nằm sau `gateway.charge` | “Theo luồng này, lưu đơn xảy ra sau khi `charge` trả về.” |
| **Giả định cần kiểm chứng** | Gateway có thể tự từ chối số tiền âm | “Chưa xem hợp đồng hoặc test của `PaymentGateway`.” |
| **Câu hỏi nghiệp vụ** | Khách VIP đúng 1.000.000 có được giảm không? | “Cần đối chiếu chính sách hoặc người phụ trách.” |
| **Rủi ro đã nhìn thấy** | Số tiền có thể âm trước khi gọi gateway | “Cần xác định đầu vào hợp lệ và chính sách chặn dưới.” |
| **Phạm vi chưa kiểm tra** | Một request được gửi lại sau timeout | “Chưa biết cơ chế tránh thanh toán trùng.” |

Cách ghi này đặc biệt hữu ích khi code review hoặc bàn giao. Người đọc tiếp theo biết **điều gì đã xác minh**, không phải mất thời gian phân biệt câu khẳng định và phỏng đoán.

### Đọc code không đồng nghĩa hiểu toàn bộ hệ thống

Các kiểu và tên phương thức giúp xây dựng giả thuyết, nhưng không cho biết chắc:

- `save()` có commit ngay, được chạy trong transaction hay chỉ lưu vào bộ nhớ đệm;
- `charge()` có idempotent, đồng bộ hay gọi mạng thực;
- `clock` dùng UTC hay múi giờ địa phương khi định dạng cho người dùng;
- `Receipt` có được xuất ra API công khai hay được biến đổi tiếp.

Muốn kết luận, cần xem **hợp đồng và implementation liên quan**, test hiện có hoặc quan sát chương trình trong môi trường an toàn. Trong bài thực hành này, ta giữ những điểm đó là câu hỏi, vì không có repository triển khai thực tế nào được cung cấp cho ví dụ.

## 6. Tìm “đường đi” trong mã mà không đọc lan man

Khi mở một codebase lớn, có thể dùng trình tự sau:

1. **Xác định điểm vào:** tên endpoint, command, scheduled job hoặc sự kiện gọi chức năng.
2. **Tìm nơi thực hiện quyết định nghiệp vụ:** nơi có điều kiện, công thức hoặc quy tắc chuyển trạng thái; tìm theo tên chức năng và điểm gọi cụ thể.
3. **Theo chiều dữ liệu:** đầu vào được tạo ở đâu, có được kiểm tra hay chuyển đổi không; kết quả đi tới những nơi nào.
4. **Theo tác dụng phụ:** lời gọi ghi database, gửi thông báo, gọi API, cập nhật trạng thái, ghi file hoặc phát sự kiện.
5. **Đọc hợp đồng phụ thuộc:** kiểu trả về, lỗi có thể ném, yêu cầu tiền điều kiện, khả năng retry và giao dịch.
6. **Đối chiếu test và hành vi chạy thực tế:** xác nhận trường hợp chính, trường hợp lỗi, cạnh biên; tìm phần chưa có test.
7. **Tóm tắt đường đi và rủi ro:** đủ để chỉ ra vị trí cần thay đổi, điều kiện đúng và điều chưa được chứng minh.

Có thể dùng một sơ đồ nhỏ thay cho ghi nhớ trong đầu:

~~~mermaid
flowchart TD
    A["Caller yêu cầu checkout"] --> B["CheckoutService.checkout"]
    B --> C["Tính tổng dòng hàng"]
    C --> D["Kiểm tra VIP và mã giảm giá"]
    D --> E["PaymentGateway.charge"]
    E --> F["OrderStore.save"]
    F --> G["Trả Receipt"]
    E -. "Lỗi / timeout: chưa rõ hợp đồng" .-> U["Cần kiểm tra"]
    F -. "Lưu thất bại sau thanh toán" .-> U
~~~

Đừng nhảy ngay tới chi tiết hạ tầng nếu mục tiêu là đọc công thức giảm giá. Tuy nhiên, **điểm chuyển qua thanh toán và lưu dữ liệu** phải được ghi nhận vì có thể khiến một thay đổi nhỏ gây hậu quả lớn.

### Khi nào cần đọc sang file khác?

Dùng câu hỏi sau để quyết định:

> “Thông tin trong file kia có thể thay đổi kết luận của mình về đầu vào, kết quả hoặc tác dụng phụ không?”

Nếu có, hãy đọc tiếp đúng hợp đồng hoặc call site liên quan. Nếu không, ghi lại mối liên hệ và quay về phạm vi cần giải quyết. Cách này tránh lạc vào toàn bộ cây phụ thuộc khi chưa cần.

## 7. Đọc luồng điều khiển và trường hợp lỗi

Đối với người mới, nhánh thành công thường dễ nhận ra hơn các đường kết thúc khác. Khi đọc một hàm, nên đặt cạnh nhau:

| Lát cắt | Câu hỏi quan sát |
| --- | --- |
| Trường hợp bình thường | Hàm trả kết quả gì, trạng thái nào được cập nhật? |
| Điều kiện biên | Dấu `>` hay `>=`? Số 0, âm, rỗng và `null` ra sao? |
| Ngoại lệ | Phương thức nào có thể ném lỗi? Lỗi có bị nuốt, chuyển đổi hoặc retry? |
| Tác dụng phụ từng phần | Đã ghi được gì trước khi bước tiếp theo thất bại? |
| Lặp và đồng thời | Hai lời gọi gần nhau có dùng chung trạng thái hay tạo side effect trùng? |
| Tài nguyên | File, kết nối, transaction hoặc lock do ai sở hữu và đóng? |

Trong ví dụ, nếu `gateway.charge` ném exception, theo luồng mã hiển thị sẽ **không gọi `store.save` và không trả `Receipt`**. Nếu `charge` đã thực hiện thanh toán ở phía bên kia rồi mới xảy ra lỗi mạng, trạng thái thật vẫn cần đối soát; chỉ nhìn exception không đủ kết luận giao dịch đã thất bại.

Nếu `store.save` ném exception sau khi `charge` trả về, phương thức cũng không trả `Receipt` nhưng đã có thể có tác dụng phụ thanh toán. Đây là một lý do quan trọng để hiểu **thứ tự thao tác**, ngay cả khi nhiệm vụ ban đầu chỉ yêu cầu đọc code chứ chưa sửa.

Đối với đồng thời, đừng mặc định `final` đồng nghĩa an toàn luồng. Hãy xem những phụ thuộc có trạng thái, vòng đời object và các ràng buộc ghi nhận duy nhất. Trong ví dụ, biến `s` là biến cục bộ nên riêng cho từng lời gọi, nhưng gateway và store có thể được dùng chung.

## 8. Dấu hiệu khiến người mới tiếp nhận khó hiểu

### 8.1. Tên không mô tả vai trò

`s`, `tmp` hoặc `handle()` bắt người đọc suy luận từ các dòng xung quanh. Tên rõ hơn có thể là `subtotalVnd`, `vipDiscountedVnd`, `amountDueVnd`. Đổi tên là cải thiện khả năng đọc khi tên mới **khớp đúng ý nghĩa tại mọi điểm sử dụng**; một tên quá tự tin nhưng sai nghĩa còn nguy hiểm hơn tên ngắn.

### 8.2. Biến bị thay đổi nhiều lần

Khi `s` vừa là tổng trước giảm, vừa là số sau VIP, vừa là số sau mã giảm giá, người đọc phải nhớ “phiên bản” của nó. Các bước có tên riêng thường giúp đọc một phép tính theo chuỗi nguyên nhân:

~~~java
long subtotalVnd = sumLines(lines);
long afterVipVnd = applyVipDiscount(subtotalVnd, customer.vip());
long amountDueVnd = applyCoupon(afterVipVnd, code);
~~~

Ba hàm ở đây chỉ là **cách biểu đạt đề xuất**, chưa có implementation và chưa khẳng định nên trừ tiền như thế nào. Cần giữ hành vi cũ có kiểm soát hoặc thống nhất thay đổi nghiệp vụ trước khi áp dụng thực tế.

### 8.3. Hằng số không có tên hoặc không rõ nguồn

`1_000_000L`, `90`, `100`, `50_000L` cho biết cơ chế tính, nhưng không cho biết **lý do**, đơn vị và cách thay đổi chính sách. Đặt tên ví dụ `VIP_THRESHOLD_VND` làm rõ ý nghĩa, còn mức ngưỡng và phần trăm phải được kiểm chứng với quy tắc nghiệp vụ. Không nhất thiết phải chuyển mọi số vào file cấu hình; hãy chọn vị trí thể hiện một nguồn sự thật hợp lý.

### 8.4. Trách nhiệm bị trộn lẫn

Phương thức `checkout` vừa tính tiền vừa gọi thanh toán và lưu dữ liệu. Người đọc không thể dễ dàng kiểm tra công thức mà không cân nhắc các phụ thuộc bên ngoài. Có thể tách **logic tính toán thuần** khỏi **điều phối side effect**, nếu việc này làm ranh giới trách nhiệm rõ và dễ kiểm thử hơn.

Nhưng việc tách thành hàng chục lớp trung gian chỉ để tránh một hàm dài có thể làm **khả năng đọc toàn luồng** tệ hơn. Đơn vị nên được tách theo trách nhiệm có ý nghĩa, không chỉ theo số dòng.

### 8.5. Lý do không thể suy ra từ câu lệnh

Ví dụ, vì sao phải áp dụng VIP trước mã giảm giá? Đó là quyết định nghiệp vụ hoặc có thể là lỗi. Bình luận tốt giải thích **lý do và quy tắc đã được xác nhận**; bình luận như `// giảm 10%` ngay bên trên `s = s * 90 / 100` chỉ lặp lại điều đã nhìn thấy.

Chú thích và tài liệu có nguy cơ lỗi thời. Khi mã và comment mâu thuẫn, cần điều tra thay vì mặc định comment đúng.

## 9. Từ đọc hiểu tới cải thiện: thay đổi từng bước có chứng cứ

Mục tiêu của người mới khi thực hiện thay đổi nhỏ thường nên là **giảm rủi ro khi sửa**, không phải thiết kế lại cả module. Quy trình có thể là:

1. **Mô tả hành vi hiện tại:** ghi rõ các đầu vào và số tiền thực sự được tính theo mã.
2. **Xác minh đặc tả:** hỏi về ranh giới VIP, thứ tự ưu đãi, làm tròn, số tiền tối thiểu và cách xử lý lỗi thanh toán.
3. **Viết kiểm thử đặc tả/hồi quy phù hợp:** phân biệt test “ghi nhận hành vi cũ” với test “hành vi mong đợi mới”.
4. **Thực hiện cải thiện dễ đọc:** đặt tên có đơn vị, tách phép tính có trách nhiệm rõ, giới hạn phạm vi tác dụng phụ nếu hợp lý.
5. **Xử lý lỗi nghiệp vụ theo yêu cầu xác nhận:** ví dụ chặn số tiền âm hoặc thay đổi dấu `>`; coi đây là thay đổi hành vi, không gộp lặng lẽ vào refactor.
6. **Kiểm tra lại hành vi và ranh giới tích hợp:** nhất là kết quả charge/save, lỗi, retry và những đường ảnh hưởng tới hệ thống ngoài.
7. **Viết ghi chú bàn giao:** nêu điều đã kiểm chứng, điều được thay đổi và giới hạn còn lại.

Phân biệt hai loại công việc:

| Loại thay đổi | Ví dụ | Tiêu chí thành công |
| --- | --- | --- |
| **Refactor bảo toàn hành vi** | Đổi `s` thành `amountDueVnd` đúng tại vị trí sử dụng, tách công thức không đổi kết quả | Trường hợp đầu vào hợp lệ vẫn có cùng kết quả và side effect |
| **Sửa tính đúng đắn** | Chặn tổng âm, xử lý tràn, thay `>` thành `>=` theo chính sách | Có đặc tả mới và kiểm thử chứng minh điều kiện mong đợi |
| **Thay đổi thiết kế tích hợp** | Quản lý thanh toán/lưu đơn bằng trạng thái bền vững và idempotency | Giải quyết được tình huống lỗi/nhân đôi đã xác định, được kiểm thử ở mức tích hợp |

Điều này tránh lỗi thường gặp khi tiếp nhận mã: thấy một đoạn “khó coi” rồi sửa nhiều thứ cùng lúc, khiến reviewer không phân biệt được cải thiện khả năng đọc với thay đổi hành vi.

## 10. Đọc code cùng kiểm thử để giảm suy đoán

Nếu có test, hãy xem chúng như **bằng chứng bổ sung**, không phải đặc tả tuyệt đối. Một test có thể phản ánh hành vi cũ không còn mong đợi, hoặc bỏ qua trường hợp quan trọng. Quan sát test và mã cùng nhau sẽ giúp đặt câu hỏi đúng.

Đối với ví dụ `checkout`, một bảng test nên xuất phát từ những điều đang cần xác minh:

| Đầu vào/tình huống | Quan sát cần thiết | Loại bằng chứng |
| --- | --- | --- |
| VIP có tổng đúng 1.000.000 VND | Mã hiện tại không áp dụng ưu đãi VIP | Có thể xác nhận bằng phép tính và test đặc tả hiện tại |
| VIP trên ngưỡng + `SAVE50` | Áp dụng VIP trước, rồi trừ 50.000 | Có thể xác nhận bằng fake gateway và số tiền truyền vào |
| Tổng 30.000 + `SAVE50` | Có thể truyền -20.000 đến gateway | Cần xem giới hạn và hợp đồng cổng thanh toán |
| `gateway.charge` thất bại | Có gọi `store.save` nữa không? | Test với fake gateway ném exception |
| `store.save` thất bại | Hậu quả sau một charge thành công? | Cần phân tích tích hợp và chiến lược đối soát |
| Hai yêu cầu giống nhau tới gần nhau | Có thể thu tiền hai lần không? | Cần kiểm tra idempotency ở tầng lưu trữ/thanh toán |

Ví dụ JUnit 5 dưới đây minh họa **kiểm thử một hành vi quan sát được** bằng fake đơn giản, không gọi thanh toán thật. Các `record` và interface sử dụng đúng như khai báo trong ví dụ Java ở trên:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.time.Clock;
import java.util.List;
import java.util.concurrent.atomic.AtomicLong;

class CheckoutReadingTest {
    @Test
    void recordsAmountSentToGateway() {
        AtomicLong charged = new AtomicLong(Long.MIN_VALUE);

        PaymentGateway gateway = (token, amountVnd) -> {
            charged.set(amountVnd);
            return new Payment("test-reference");
        };

        OrderStore store = order -> {
            assertEquals(940_000L, order.amountVnd());
        };

        CheckoutService checkout = new CheckoutService(
                gateway, store, Clock.systemUTC());

        Receipt receipt = checkout.checkout(
                new Customer(1L, true, "dummy-token"),
                List.of(new Line(1_100_000L, 1)),
                "SAVE50");

        assertEquals(940_000L, charged.get());
        assertEquals(940_000L, receipt.amountVnd());
    }
}
~~~

Một test như vậy giúp người mới xác nhận **số tiền thực sự truyền qua ranh giới** `PaymentGateway`. Nó **không chứng minh** cổng thanh toán thật đã xử lý thành công, dữ liệu được commit bền vững, hoặc chính sách giảm giá là đúng. Những kết luận đó đòi hỏi test tích hợp và xác nhận hợp đồng nghiệp vụ.

Không cần viết test cho mọi dòng code. Chọn các kịch bản làm rõ ranh giới, giả định và rủi ro khi thay đổi.

## 11. Mẫu ghi chú tiếp nhận mã ngắn gọn

Sau khi đọc, hãy thử viết một ghi chú mà đồng nghiệp chưa biết đoạn mã vẫn hiểu được:

> **Mục đích:** `CheckoutService.checkout` tính tổng tiền từ các dòng hàng, áp dụng giảm VIP và mã `SAVE50`, gửi số tiền cho gateway, lưu đơn rồi trả receipt.  
> **Đầu vào:** `Customer`, `List<Line>`, `code`; chưa thấy validation trong phương thức này.  
> **Quy tắc quan sát:** VIP áp dụng khi tổng lớn hơn 1.000.000 VND; nhân 90/chia 100 bằng số nguyên; `SAVE50` trừ sau VIP.  
> **Tác dụng phụ:** `gateway.charge` trước `store.save`; ghi thời điểm từ `Clock`.  
> **Rủi ro/câu hỏi:** tổng âm hoặc tràn; quy tắc đúng ngưỡng; timeout sau thanh toán; lưu đơn lỗi; retry trùng.  
> **Bằng chứng cần bổ sung:** chính sách giá, test boundary, hợp đồng gateway/store và cơ chế idempotency.

Mẫu này ngắn nhưng phân biệt được **điều mã đang làm** với **điều chưa được biết**. Nếu một ghi chú chỉ gồm “Code hơi rối, cần clean up”, người mới kế tiếp vẫn phải phân tích lại từ đầu.

### Checklist cho người nhận bàn giao

- [ ] Tôi nói được chức năng của hàm bằng một hoặc hai câu không dựa vào tên hàm.
- [ ] Tôi biết đầu vào, đầu ra, những trạng thái được thay đổi và các lời gọi có tác dụng phụ.
- [ ] Tôi lần theo được ít nhất một trường hợp thành công và một trường hợp lỗi.
- [ ] Tôi đã kiểm tra các ranh giới quan trọng, đặc biệt là `null`, rỗng, 0, ngưỡng và giá trị lớn.
- [ ] Tôi biết điều gì là bằng chứng từ mã, điều gì chỉ là phỏng đoán.
- [ ] Tôi biết file/hợp đồng/test nào cần đọc tiếp để xác nhận các giả định có ảnh hưởng tới việc sửa.
- [ ] Tôi có thể chỉ ra một cải thiện có lý do và cách xác minh hành vi không bị thay đổi ngoài dự kiến.

## 12. Những ngộ nhận khi mới tiếp nhận mã

**“Đọc hết project trước mới được sửa một hàm.”** Đọc theo lát cắt hành vi thường hiệu quả hơn. Mở rộng theo phụ thuộc có liên quan trực tiếp đến kết quả hoặc side effect.

**“Tên hàm cho biết mọi thứ nó làm.”** `checkout` có thể tính tiền, thanh toán và lưu dữ liệu; phải xác định hành vi từ implementation và hợp đồng.

**“Code ít dòng thì dễ bảo trì.”** Một biến dùng cho nhiều ý nghĩa và các quyết định ngầm có thể làm vài dòng ngắn trở nên khó hiểu.

**“Comment và test luôn là nguồn sự thật tuyệt đối.”** Chúng là bằng chứng cần đối chiếu với đặc tả và hành vi đang chạy; có thể bị lỗi thời hoặc thiếu tình huống.

**“Thấy điều kiện lạ là chắc chắn bug.”** Điều kiện khác trực giác có thể xuất phát từ yêu cầu nghiệp vụ. Ghi nhận, mô phỏng trường hợp biên và kiểm chứng trước khi đổi.

**“Đổi tên và tách hàm là đủ để code đúng.”** Những việc này giúp khả năng đọc nếu làm hợp lý, nhưng không tự sửa chính sách sai, tràn số, tác dụng phụ thiếu nhất quán hoặc phân quyền.

**“Chạy thành công một trường hợp là đã hiểu.”** Cần đọc trường hợp lỗi, biên và cách dữ liệu đi qua các phụ thuộc để có mô hình tinh thần đủ tin cậy.

**“Người mới hỏi nhiều là vì họ chưa đủ giỏi.”** Nếu một đoạn mã thường xuyên buộc người tiếp nhận phải đoán đơn vị, phạm vi trách nhiệm và giả định ẩn, đó là tín hiệu hữu ích để cải thiện khả năng đọc của hệ thống.

## 13. Tự kiểm tra

1. Khi được giao sửa một hàm lạ, ba câu hỏi đầu tiên bạn nên xác định là gì? Vì sao không nên mở tất cả file phụ thuộc ngay lập tức?
2. Trong ví dụ `checkout`, giá trị `s` biểu thị những ý nghĩa nào ở các giai đoạn khác nhau? Hãy đề xuất tên giúp người đọc theo dõi.
3. Khách VIP có tổng đúng 1.000.000 VND có được giảm theo mã hiện tại không? Vì sao điều này chưa đủ để kết luận chương trình sai?
4. Nếu tổng 30.000 VND và dùng `SAVE50`, số tiền truyền cho gateway là bao nhiêu? Những điều gì còn phải kiểm tra?
5. Khi `gateway.charge` đã xử lý nhưng `store.save` thất bại, người đọc cần tìm hợp đồng hoặc test nào trước khi sửa?
6. So sánh một **dữ kiện**, một **giả định** và một **câu hỏi nghiệp vụ** dựa trên đoạn mã ở phần 3.
7. Một bình luận ghi “Mã giảm giá áp dụng trước VIP” nhưng code lại tính VIP trước. Bạn sẽ xử lý mâu thuẫn này ra sao?
8. Vì sao việc đổi `>` thành `>=` không nên được coi là refactor thuần túy?
9. Hãy thiết kế hai trường hợp kiểm thử giúp người mới hiểu ranh giới thanh toán/lưu dữ liệu mà không gọi cổng thanh toán thật.
10. Hãy viết một đoạn bàn giao năm câu mô tả mục đích, dòng dữ liệu, quy tắc đã thấy, tác dụng phụ và phần còn chưa rõ.

## Ghi nhớ

**Đọc mã tốt là tái dựng được hành vi và ranh giới trách nhiệm một cách có bằng chứng.** Hãy bắt đầu từ mục tiêu, đi theo đầu vào → quyết định → tác dụng phụ → kết quả, mô phỏng dữ liệu cụ thể, đọc cả trường hợp lỗi và ghi tách bạch điều đã biết với điều cần xác minh. Khi người mới có thể hiểu và kiểm tra một thay đổi mà không phải đoán quá nhiều, khả năng đọc đã trở thành một thuộc tính chất lượng có giá trị thực tế.
