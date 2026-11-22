# Thứ tự thao tác và trạng thái cập nhật một phần

Một đoạn mã có thể thực hiện đúng từng phép tính riêng lẻ nhưng vẫn cho ra kết quả sai khi các thao tác diễn ra **không đúng thứ tự**, hoặc khi chương trình thất bại **sau khi chỉ một phần trạng thái đã được cập nhật**. Đây là dạng lỗi đặc biệt quan trọng với số dư, tồn kho, đơn hàng, thanh toán và các quy trình có nhiều bước phụ thuộc nhau.

Trong chương **Tính đúng đắn** của module **CODE_QUALITY_FUNDAMENTALS**, chủ đề này giúp hiểu vì sao mã nguồn đáng tin cậy phải giữ được quy tắc nghiệp vụ ngay cả khi xuất hiện ngoại lệ, yêu cầu đồng thời, mất kết nối hoặc thao tác được chạy lại. Chất lượng không chỉ nằm ở giá trị trả về cuối cùng, mà còn ở trạng thái và tác động được tạo ra trên đường thực thi.

## 1. Thứ tự thao tác ảnh hưởng tới tính đúng đắn như thế nào?

Xét quy trình chuyển 100.000 đồng từ tài khoản A sang tài khoản B. Nếu ban đầu A có 300.000 đồng và B có 50.000 đồng thì kết quả hợp lệ là:

| Trạng thái | A | B | Tổng |
| --- | ---: | ---: | ---: |
| Trước chuyển | 300.000 | 50.000 | 350.000 |
| Sau chuyển thành công | 200.000 | 150.000 | 350.000 |

Quy tắc **tổng tiền không đổi** là một *bất biến* (*invariant*) của thao tác chuyển tiền trong ví dụ này. Nếu chương trình trừ tiền A thành công nhưng lỗi trước khi cộng tiền B, trạng thái có thể thành:

| Trạng thái lỗi | A | B | Tổng |
| --- | ---: | ---: | ---: |
| Chỉ trừ A | 200.000 | 50.000 | 250.000 |

Mặc dù phép trừ tự nó đã làm đúng, **toàn bộ thao tác chuyển tiền là sai**.

### 1.1. Quan hệ trước – sau và phụ thuộc

Một số công việc phải xảy ra theo thứ tự:

- **Kiểm tra điều kiện** trước khi thay đổi trạng thái, nếu điều kiện đó quyết định thao tác có được phép hay không.
- **Tạo dữ liệu cần thiết** trước khi tham chiếu đến dữ liệu ấy.
- **Ghi nhận kết quả bền vững** trước khi công bố một sự kiện khẳng định kết quả đã hoàn tất.
- **Xác nhận tính hợp lệ của toàn bộ thay đổi** trước khi đưa trạng thái mới ra cho bên khác quan sát, khi hợp đồng yêu cầu thao tác nguyên tử.

Không phải lúc nào đổi thứ tự hai câu lệnh cũng làm đổi kết quả cuối cùng nếu mọi bước đều thành công. Tuy nhiên, **kết quả sau lỗi, thứ tự bên ngoài quan sát được và tác động khi chạy lại** có thể khác nhau.

Ví dụ, nếu gửi email “Đơn hàng đã thanh toán” trước khi hệ thống ghi nhận thanh toán thành công, một lỗi ghi dữ liệu sau đó sẽ khiến người dùng nhận một thông báo sai. Đổi thứ tự giúp giảm nguy cơ gửi quá sớm, nhưng chỉ đổi vị trí câu lệnh vẫn chưa giải quyết được mọi lỗi: nếu ghi thành công rồi gửi email thất bại, lại xuất hiện một trạng thái khác cần xử lý.

### 1.2. Trạng thái cập nhật một phần là gì?

**Trạng thái cập nhật một phần** (*partial update state*) xuất hiện khi một thao tác logic gồm nhiều thay đổi nhưng chỉ một số thay đổi được thực hiện hoặc được lưu thành công. Các nguyên nhân thường gặp gồm:

1. Một phép kiểm tra hoặc tính toán ném ngoại lệ sau khi dữ liệu đã bị sửa.
2. Truy vấn cơ sở dữ liệu thứ hai thất bại sau khi truy vấn thứ nhất đã được ghi.
3. Mạng mất kết nối sau khi một dịch vụ bên ngoài đã nhận yêu cầu.
4. Tiến trình dừng giữa lúc đang cập nhật nhiều tệp hoặc bản ghi.
5. Hai yêu cầu đồng thời cùng đọc dữ liệu cũ rồi ghi chồng lên nhau.
6. Một công việc chạy theo lô xử lý thành công vài phần tử rồi dừng.

Cần phân biệt **trạng thái trung gian có kiểm soát** với **trạng thái lỗi**. Quy trình dài như giao hàng có thể hợp lệ ở trạng thái “đã xác nhận, đang vận chuyển”. Vấn đề phát sinh khi trạng thái trung gian **vi phạm hợp đồng**, bị công bố như hoàn tất, hoặc không có cách tiếp tục và khôi phục.

## 2. Bất biến: cơ sở để nhận diện kết quả sai

Bất biến là quy tắc phải được duy trì tại những ranh giới quan sát được hoặc những điểm cam kết đã xác định.

Ví dụ:

| Bài toán | Bất biến hoặc điều kiện phải giữ | Hậu quả nếu vi phạm |
| --- | --- | --- |
| Chuyển tiền | Tổng tiền của hai tài khoản không đổi, trừ khi có phí được quy định | Mất tiền hoặc tạo tiền ngoài dự kiến |
| Đặt hàng | Số lượng giữ chỗ không vượt quá số lượng có thể bán | Bán vượt tồn kho |
| Thanh toán | Một mã yêu cầu thanh toán không được tính tiền hai lần nếu hợp đồng quy định đúng một lần | Thu tiền trùng |
| Đăng ký tài khoản | Tài khoản chỉ chuyển sang trạng thái hoạt động khi đủ điều kiện | Quyền truy cập được cấp quá sớm |
| Nhập dữ liệu | Mỗi mục nhập đã xác nhận có kết quả xác định, không bị ghi đúp khi chạy lại | Dữ liệu trùng hoặc thiếu |

Khi xem xét thứ tự thao tác, hãy hỏi:

- Trạng thái nào được phép tồn tại?
- Quy tắc nào không được vi phạm tại thời điểm cam kết?
- Ai có thể đọc trạng thái giữa các bước?
- Nếu lỗi xảy ra sau mỗi bước, kết quả còn hợp lệ không?
- Có thể khôi phục, bù trừ hoặc chạy lại an toàn không?

Một sơ đồ trạng thái đơn giản giúp làm rõ rủi ro:

~~~text
S0: Chưa bắt đầu
  |
  v
S1: Đã hoàn tất thay đổi A
  |
  |  <-- Có thể thất bại tại đây
  v
S2: Đã hoàn tất thay đổi A và B
  |
  v
S3: Đã xác nhận hoàn tất
~~~

Nếu nghiệp vụ quy định chỉ S0 và S3 là trạng thái ổn định thì S1, S2 cần nằm trong một ranh giới giao dịch hoặc có cơ chế xử lý lỗi phù hợp. Nếu nghiệp vụ cho phép trạng thái trung gian, chúng cần được mô hình hóa rõ ràng và không bị hiểu nhầm là hoàn tất.

## 3. Ví dụ Java: ngoại lệ sau khi đã sửa trạng thái

Xét một đối tượng Java giữ hai số dư trong bộ nhớ. Đây là ví dụ rút gọn để tập trung vào thứ tự thao tác; chưa có cơ sở dữ liệu hoặc hệ thống bên ngoài.

### 3.1. Cách sai: sửa trước, kiểm tra sau

~~~java
public final class UnsafeTransfer {
    private long sourceCents = 300_00;
    private long targetCents = 50_00;

    public void transfer(long amountCents) {
        sourceCents -= amountCents; // Đã sửa trạng thái.

        if (amountCents <= 0 || sourceCents < 0) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        targetCents = Math.addExact(targetCents, amountCents);
    }

    public long sourceCents() {
        return sourceCents;
    }

    public long targetCents() {
        return targetCents;
    }
}
~~~

Nếu gọi **transfer(400_00)** trong khi nguồn chỉ có 300_00 xu, phương thức ném ngoại lệ **sau khi** số dư nguồn đã giảm xuống âm. Nếu phép cộng bằng **Math.addExact** bị tràn số, nguồn cũng đã bị trừ nhưng đích chưa được cộng. Trong cả hai trường hợp, không có cơ chế tự hoàn tác biến đã sửa.

Việc có câu lệnh **throw** không có nghĩa Java sẽ tự khôi phục mọi thay đổi trước đó. Ngoại lệ chỉ thay đổi luồng điều khiển; nó không mặc nhiên tạo ra giao dịch.

### 3.2. Cách tốt hơn: xác thực và tính trước, rồi mới cập nhật

~~~java
public final class TwoAccountLedger {
    private long sourceCents;
    private long targetCents;

    public TwoAccountLedger(long sourceCents, long targetCents) {
        if (sourceCents < 0 || targetCents < 0) {
            throw new IllegalArgumentException("Negative initial balance");
        }
        this.sourceCents = sourceCents;
        this.targetCents = targetCents;
    }

    public synchronized void transfer(long amountCents) {
        if (amountCents <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        if (sourceCents < amountCents) {
            throw new IllegalStateException("Insufficient funds");
        }

        long nextSource = Math.subtractExact(sourceCents, amountCents);
        long nextTarget = Math.addExact(targetCents, amountCents);

        sourceCents = nextSource;
        targetCents = nextTarget;
    }

    public synchronized long sourceCents() {
        return sourceCents;
    }

    public synchronized long targetCents() {
        return targetCents;
    }
}
~~~

Những khác biệt quan trọng:

1. **Kiểm tra trước:** số tiền phải dương và tài khoản nguồn phải đủ tiền.
2. **Tính toán trước:** cả hai số dư mới được tính thành biến cục bộ; **Math.addExact** sẽ ném ngoại lệ khi cộng tràn số trước khi bất kỳ trường trạng thái nào bị gán lại.
3. **Cập nhật sau:** khi đã tính thành công, hai trường mới được nhận giá trị.
4. **Đồng bộ truy cập:** trong ví dụ đơn đối tượng này, **synchronized** ngăn các lời gọi dùng cùng khóa quan sát trạng thái xen giữa các lần gán.

Ví dụ chỉ bảo vệ trạng thái **trong bộ nhớ của một đối tượng và một tiến trình**, với điều kiện mọi thao tác đọc/ghi liên quan đều đi qua cơ chế đồng bộ đó. Nó không bảo đảm lưu trữ bền vững, không bao phủ nhiều tiến trình hay giao dịch giữa các cơ sở dữ liệu, và không thay thế khóa/giao dịch ở tầng lưu trữ.

### 3.3. Kiểm thử các điểm thất bại

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class TwoAccountLedgerTest {
    @Test
    void transfersWithoutChangingTotal() {
        TwoAccountLedger ledger = new TwoAccountLedger(300_00, 50_00);

        ledger.transfer(100_00);

        assertEquals(200_00, ledger.sourceCents());
        assertEquals(150_00, ledger.targetCents());
    }

    @Test
    void keepsBalancesWhenSourceHasInsufficientFunds() {
        TwoAccountLedger ledger = new TwoAccountLedger(300_00, 50_00);

        assertThrows(IllegalStateException.class,
                () -> ledger.transfer(400_00));

        assertEquals(300_00, ledger.sourceCents());
        assertEquals(50_00, ledger.targetCents());
    }

    @Test
    void keepsBalancesWhenTargetWouldOverflow() {
        TwoAccountLedger ledger =
                new TwoAccountLedger(300_00, Long.MAX_VALUE);

        assertThrows(ArithmeticException.class,
                () -> ledger.transfer(100_00));

        assertEquals(300_00, ledger.sourceCents());
        assertEquals(Long.MAX_VALUE, ledger.targetCents());
    }
}
~~~

Những kiểm thử này quan trọng vì chúng kiểm tra **trạng thái sau ngoại lệ**, thay vì chỉ xác nhận rằng có ngoại lệ xảy ra. Mã ném đúng loại lỗi nhưng để dữ liệu ở trạng thái sai vẫn không đạt yêu cầu.

## 4. Giao dịch cơ sở dữ liệu và tính nguyên tử

Với dữ liệu cần lưu bền vững, kiểm tra trước khi cập nhật vẫn chưa đủ: quá trình có thể dừng **giữa các lần ghi**. Giao dịch cơ sở dữ liệu (*database transaction*) là cơ chế thường dùng để xử lý một nhóm thay đổi cần cam kết cùng nhau.

**Tính nguyên tử** (*atomicity*) trong một giao dịch có nghĩa là các thay đổi thuộc giao dịch đó được cam kết như một đơn vị: hoặc tất cả được cam kết, hoặc các thay đổi chưa cam kết được hoàn tác theo bảo đảm của hệ quản trị cơ sở dữ liệu.

Ví dụ luồng chuyển tiền trong một cơ sở dữ liệu giao dịch:

~~~text
BEGIN TRANSACTION
  Đọc và khóa dữ liệu tài khoản liên quan
  Kiểm tra số dư và ràng buộc
  Trừ tiền nguồn
  Cộng tiền đích
  Ghi thông tin giao dịch
COMMIT

Nếu lỗi trước COMMIT -> ROLLBACK
~~~

Nhờ đó, không xuất hiện kết quả “trừ nguồn đã commit nhưng cộng đích chưa commit” nếu cả hai thay đổi thực sự nằm trong **cùng một giao dịch** được hệ quản trị hỗ trợ.

### 4.1. Giao dịch không tự sinh ra khi có nhiều câu lệnh Java

Giả sử một dịch vụ thực hiện:

~~~java
debitRepository.save(debitAccount);
creditRepository.save(creditAccount);
~~~

Nếu mỗi lời gọi được cam kết độc lập thì việc thứ hai thất bại có thể để lại lần ghi thứ nhất. Vì vậy phải xác định **ranh giới giao dịch** cụ thể, không chỉ dựa vào việc các lời gọi nằm trong cùng một phương thức.

Với Spring và một nguồn dữ liệu giao dịch phù hợp, có thể tổ chức một phương thức dịch vụ dùng **@Transactional**. Minh họa cấu trúc:

~~~java
@Transactional
public void transfer(long sourceId, long targetId, long amountCents) {
    if (sourceId == targetId || amountCents <= 0) {
        throw new IllegalArgumentException("Invalid transfer");
    }

    // lockById được giả định là truy vấn có khóa ghi thích hợp.
    long firstId = Math.min(sourceId, targetId);
    long secondId = Math.max(sourceId, targetId);
    Account first = accounts.lockById(firstId);
    Account second = accounts.lockById(secondId);

    Account source = sourceId == firstId ? first : second;
    Account target = targetId == secondId ? second : first;
    if (source.getBalanceCents() < amountCents) {
        throw new IllegalStateException("Insufficient funds");
    }

    long newSource =
            Math.subtractExact(source.getBalanceCents(), amountCents);
    long newTarget =
            Math.addExact(target.getBalanceCents(), amountCents);

    source.setBalanceCents(newSource);
    target.setBalanceCents(newTarget);
}
~~~

Đây là **đoạn mã minh họa**, trong đó **Account**, **accounts** và **lockById** thuộc tầng truy cập dữ liệu của ứng dụng. Ví dụ giả định các đối tượng được quản lý trong cùng giao dịch JPA, việc thay đổi trường được đồng bộ vào cơ sở dữ liệu khi giao dịch commit, khóa hoạt động đúng theo thiết kế và lời gọi đi qua cơ chế giao dịch của Spring. Sắp xếp ID trước khi lấy khóa giúp các yêu cầu chuyển tiền chọn thứ tự khóa nhất quán, giảm nguy cơ deadlock; không loại bỏ mọi khả năng deadlock.

Trong cấu hình Spring thông thường, **@Transactional** mặc định đánh dấu rollback cho **RuntimeException** và **Error**, nhưng không mặc định rollback cho mọi checked exception. Cũng cần để ý những trường hợp như tự gọi phương thức trong cùng đối tượng làm lời gọi không đi qua proxy giao dịch. Cách dùng cụ thể phải phù hợp với transaction manager và cấu hình ứng dụng.

### 4.2. Tính nguyên tử khác tính cô lập

Một giao dịch có thể cam kết tất cả thao tác mà vẫn bị lỗi logic khi chạy đồng thời nếu mức cô lập (*isolation*) và cách khóa không phù hợp.

Ví dụ hai yêu cầu cùng đọc tồn kho là 1, cùng kiểm tra “còn hàng”, rồi cùng ghi nhận bán một sản phẩm. Một giao dịch riêng lẻ không đủ để ngăn việc **bán vượt tồn kho** nếu hai giao dịch đồng thời không được phối hợp phù hợp.

Các cách xử lý tùy bài toán:

- **Khóa bi quan:** khóa dòng dữ liệu khi đọc để ngăn cập nhật cạnh tranh trong phạm vi giao dịch.
- **Khóa lạc quan:** dùng trường phiên bản; chỉ ghi khi phiên bản vẫn như khi đọc và xử lý xung đột khi có thay đổi.
- **Cập nhật có điều kiện:** ví dụ chỉ giảm tồn kho nếu số lượng hiện tại đủ; kiểm tra số dòng bị cập nhật.
- **Ràng buộc cơ sở dữ liệu:** dùng constraint để ngăn những trạng thái không hợp lệ mà DB có thể kiểm soát.

Mỗi lựa chọn có đánh đổi về thông lượng, độ trễ chờ, tỉ lệ xung đột và độ phức tạp. Không có một mức cô lập mặc định bảo đảm mọi bất biến nghiệp vụ trong mọi hệ quản trị.

## 5. Những thao tác nằm ngoài giao dịch dữ liệu

Một giao dịch cơ sở dữ liệu thông thường **không tự cuốn vào cùng một lần commit** các tác động như gửi email, gọi cổng thanh toán, ghi tệp ngoài DB hoặc phát thông điệp tới hệ thống khác.

Xét hai cách sắp xếp:

| Thứ tự | Điểm lỗi | Hậu quả có thể xảy ra |
| --- | --- | --- |
| Gửi thông điệp trước, rồi commit DB | Commit DB thất bại | Bên nhận thấy sự kiện về một thay đổi chưa tồn tại |
| Commit DB trước, rồi gửi thông điệp | Ứng dụng dừng sau commit | Thay đổi đã lưu nhưng thông điệp chưa được gửi |

Chỉ đổi thứ tự không loại bỏ đồng thời cả hai khoảng lỗi. Khi cần bảo đảm sự kiện phát ra gắn với dữ liệu đã lưu, một lựa chọn phổ biến là **transactional outbox**.

### 5.1. Ý tưởng transactional outbox

~~~text
Trong MỘT giao dịch DB:
  1. Cập nhật đơn hàng
  2. Ghi bản ghi sự kiện vào bảng outbox
  3. Commit cả hai

Sau commit:
  4. Worker đọc outbox và gửi thông điệp
  5. Ghi nhận kết quả gửi / thử lại khi cần
~~~

Nhờ bước 1 và 2 cùng giao dịch, dữ liệu đơn hàng và ý định phát sự kiện không bị tách rời bởi lỗi trước commit. Tuy nhiên, worker có thể gửi thành công rồi dừng trước khi đánh dấu đã gửi, dẫn tới gửi lại. Vì vậy mô hình outbox thông thường đi cùng **xử lý lặp an toàn** (*idempotent consumer*) và mã định danh sự kiện ổn định.

Outbox không có nghĩa toàn bộ mạng, hệ thống nhận và cơ sở dữ liệu cùng tham gia một giao dịch nguyên tử. Nó cung cấp cơ chế phục hồi và bảo đảm phù hợp trong điều kiện được triển khai đúng.

### 5.2. Bù trừ khi không thể hoàn tác một cách nguyên tử

Với quy trình kéo dài qua nhiều dịch vụ, một số bước đã cam kết độc lập. Khi bước sau thất bại, hệ thống có thể thực hiện **thao tác bù trừ** (*compensation*), chẳng hạn giải phóng phần tồn kho đã giữ hoặc yêu cầu hoàn tiền theo chính sách.

Điểm cần hiểu: thao tác bù trừ **không phải quay ngược thời gian**. Người dùng có thể đã thấy trạng thái trung gian hoặc nhận thông báo. Bù trừ cũng có thể thất bại và cần được thử lại hoặc xử lý thủ công. Quy trình phải xác định trạng thái trung gian, điều kiện chuyển trạng thái và cách theo dõi các bước chưa hoàn tất.

## 6. Thử lại thao tác và tính lặp an toàn

Một trường hợp dễ gây lỗi là **bên gọi không biết yêu cầu đã thành công hay chưa**. Ví dụ, API thanh toán xử lý thành công nhưng mất mạng trước khi gửi phản hồi. Ứng dụng khách thử lại; nếu mỗi lần thử đều tạo một thanh toán mới, người dùng có thể bị thu tiền hai lần.

**Tính lặp an toàn** (*idempotency*) nghĩa là thực hiện cùng một thao tác nhiều lần, theo hợp đồng đã định nghĩa, không tạo thêm thay đổi nghiệp vụ ngoài kết quả của lần thực hiện hợp lệ đầu tiên.

Một cách thiết kế:

1. Bên gọi cung cấp **idempotency key** cho một ý định nghiệp vụ, ví dụ mã yêu cầu thanh toán.
2. Máy chủ kiểm tra và lưu key cùng kết quả hoặc trạng thái đang xử lý.
3. Nếu yêu cầu với cùng key được gửi lại, máy chủ trả kết quả nhất quán hoặc cho biết yêu cầu đang xử lý; không tự tạo thao tác nghiệp vụ thứ hai.
4. Nếu cùng key nhưng nội dung yêu cầu khác, hệ thống cần có quy tắc từ chối hoặc xử lý rõ ràng.

Việc kiểm tra key và ghi nhận giao dịch phải được bảo vệ trước **các yêu cầu đồng thời**; chỉ “kiểm tra tồn tại rồi mới insert” trong hai bước độc lập vẫn có thể gây trùng. Unique constraint, giao dịch, cập nhật có điều kiện hoặc một cơ chế phối hợp đáng tin cậy giúp thực thi quy tắc này.

Một thao tác có hiệu ứng lặp an toàn chưa chắc tạo ra phản hồi byte-for-byte giống nhau ở mọi lần gọi; điều quan trọng là hợp đồng về **trạng thái và tác động nghiệp vụ**.

## 7. Cập nhật từng phần đôi khi là yêu cầu chủ đích

Không phải mọi công việc nhiều bước đều cần đảo ngược toàn bộ khi một bước thất bại. Ví dụ nhập một triệu bản ghi có thể được thiết kế để:

- Ghi thành công từng lô đã xác nhận.
- Ghi rõ lô nào thất bại và nguyên nhân.
- Cho phép tiếp tục từ checkpoint mà không tạo bản ghi trùng.
- Công bố trạng thái **đang xử lý**, **hoàn tất** hoặc **hoàn tất một phần** đúng với thực tế.

Ở đây, cập nhật từng phần là **hợp lệ khi được quy định trong hợp đồng**, có dấu vết và có cách tiếp tục. Ngược lại, âm thầm báo “thành công” dù mới nhập 70% dữ liệu là sai.

Một mô hình trạng thái cho công việc theo lô có thể là:

~~~text
PENDING -> RUNNING -> COMPLETED
                 |
                 +----> PARTIALLY_COMPLETED
                 |                 |
                 |                 +----> RUNNING (tiếp tục)
                 |
                 +----> FAILED
~~~

Cần đặc biệt làm rõ trạng thái sau khi tiến trình bị dừng đột ngột. Một công việc mãi ở **RUNNING** không tự nói lên nó còn hoạt động; có thể cần thời hạn lease, heartbeat hoặc cơ chế phát hiện công việc bị bỏ dở. Checkpoint phải phản ánh đúng những phần đã commit, và cơ chế chạy lại phải đủ an toàn với thao tác có tác dụng phụ.

## 8. Thiết kế kiểm thử cho lỗi giữa các bước

Kiểm thử luồng thành công chưa đủ cho mã có nhiều thao tác. Cần xem xét các **điểm thất bại** và đối chiếu với trạng thái hợp lệ.

| Điểm lỗi mô phỏng | Cần xác minh |
| --- | --- |
| Đầu vào không hợp lệ trước thao tác | Trạng thái không thay đổi |
| Lỗi sau bước cập nhật đầu tiên | Có rollback, bù trừ hoặc trạng thái trung gian hợp lệ |
| Lỗi trong khi commit | Không báo thành công khi chưa xác định kết quả; có cơ chế đối soát nếu cần |
| Lỗi ngay sau commit, trước phản hồi | Bên gọi thử lại không tạo thêm kết quả ngoài ý muốn |
| Hai yêu cầu cạnh tranh cùng dữ liệu | Bất biến vẫn được giữ; xung đột được xử lý đúng |
| Worker gửi sự kiện rồi dừng trước khi xác nhận | Lần gửi lại không gây tác dụng phụ trùng |
| Tiến trình dừng giữa một lô dữ liệu | Có thể tiếp tục hoặc xác định phần đã hoàn tất |

Các kỹ thuật hữu ích gồm:

**Kiểm thử trạng thái sau ngoại lệ.** Sau khi mô phỏng lỗi, đọc lại mọi phần dữ liệu liên quan để kiểm tra bất biến. Chỉ kiểm tra rằng phương thức đã ném ngoại lệ là chưa đủ.

**Tiêm lỗi có kiểm soát** (*fault injection*). Dùng đối tượng giả trong kiểm thử đơn vị để ném lỗi tại một điểm dự kiến; dùng môi trường tích hợp để kiểm tra lỗi DB, ngắt kết nối và thao tác lặp lại. Tránh coi mô phỏng đơn vị là bằng chứng đầy đủ cho việc rollback hoặc lưu trữ bền vững.

**Kiểm thử đồng thời.** Tạo hai hoặc nhiều lời gọi tranh chấp và xác minh kết quả cuối. Kiểm thử kiểu này cần điều phối thời điểm để tái hiện race condition, đồng thời kết hợp với việc xem xét cơ chế khóa/cô lập; một lần chạy xanh không chứng minh không còn lỗi đồng thời.

**Kiểm thử hợp đồng giao diện.** Xác nhận trạng thái trả về phù hợp với trạng thái đã commit và các tác động quan sát được, đặc biệt sau timeout và khi thử lại.

**Đối soát dữ liệu.** Với tiền, tồn kho hoặc các quy trình có nhiều dịch vụ, kiểm tra các bất biến tổng hợp và phát hiện tác vụ đang mắc kẹt là tuyến phòng vệ bổ sung cần thiết.

## 9. Những hiểu nhầm thường gặp

**“Có kiểm tra điều kiện là đủ.”** Nếu kiểm tra diễn ra sau khi sửa trạng thái, lỗi có thể vẫn để lại dữ liệu sai. Ngay cả khi kiểm tra trước, hai yêu cầu đồng thời vẫn có thể làm kết quả sai nếu không được phối hợp.

**“Ném ngoại lệ sẽ hoàn tác các lệnh Java trước đó.”** Java không tự đảo ngược việc gán biến, ghi tệp hay gọi dịch vụ bên ngoài. Rollback phải được hỗ trợ bởi cơ chế giao dịch và ranh giới phù hợp.

**“Có @Transactional nghĩa là toàn bộ hệ thống nguyên tử.”** Annotation này chỉ điều khiển tài nguyên nằm trong phạm vi giao dịch được cấu hình. Email, HTTP hoặc message broker thường nằm ngoài phạm vi đó.

**“Chỉ cần gửi thông điệp sau commit là không thể mất sự kiện.”** Tiến trình có thể dừng ngay giữa commit và gửi. Outbox hoặc cơ chế phát tin đáng tin cậy giải quyết khoảng lỗi này theo giả định cụ thể.

**“Retry luôn giúp phục hồi.”** Nếu lần trước đã thực hiện tác động nhưng bên gọi không nhận phản hồi, retry không có idempotency có thể lặp lại tác động và làm tình hình tệ hơn.

**“Trạng thái trung gian luôn là lỗi.”** Nhiều quy trình nhiều giai đoạn chủ động cho phép trạng thái trung gian. Vấn đề là chúng phải được mô hình hóa, theo dõi và diễn giải đúng.

## 10. Quy trình rà soát một thao tác nhiều bước

Khi review mã xử lý nhiều thay đổi, có thể đi theo thứ tự:

1. **Xác định một đơn vị nghiệp vụ:** Ví dụ một lần chuyển tiền, một lần đặt hàng hoặc một lô nhập dữ liệu.
2. **Viết bất biến:** Những quy tắc phải đúng trước và sau khi thao tác được xác nhận là hoàn tất.
3. **Liệt kê các bước có tác động:** Thay đổi biến, ghi DB, gọi API, gửi thông điệp, cập nhật cache.
4. **Đặt điểm lỗi sau từng bước:** Nếu dừng ngay tại đây, trạng thái nào còn lại và bên ngoài quan sát được điều gì?
5. **Đặt ranh giới cam kết:** Dùng giao dịch cho những thay đổi có thể cam kết cùng nhau; thiết kế trạng thái rõ ràng cho công việc kéo dài.
6. **Kiểm soát cạnh tranh:** Xác định tài nguyên dùng chung, chọn khóa, version, ràng buộc hoặc cập nhật có điều kiện thích hợp.
7. **Thiết kế phục hồi:** Quy định retry, idempotency, outbox, bù trừ hoặc đối soát khi cần.
8. **Kiểm thử các đường lỗi:** Xác nhận cả trạng thái cuối, tác động phụ, thông báo lỗi và khả năng tiếp tục.

Mục đích của quy trình là biến câu hỏi mơ hồ “mã có đúng không?” thành những điều kiện có thể kiểm chứng: **đúng khi thành công, đúng khi thất bại và đúng khi bị chạy đồng thời hoặc chạy lại**.

## 11. Tình huống thực hành

Một API đặt vé thực hiện theo thứ tự:

~~~text
1. Giảm số ghế trống
2. Gọi cổng thanh toán
3. Lưu đơn đặt vé
4. Trả HTTP 200
~~~

Giả sử cổng thanh toán đã thu tiền, nhưng việc lưu đơn đặt vé bị lỗi. Người dùng thấy HTTP 500 và nhấn “Thanh toán lại”.

Hãy tự trả lời:

1. Hệ thống có thể đang ở những trạng thái cập nhật một phần nào?
2. Vì sao chỉ đổi thứ tự lưu đơn và thanh toán chưa giải quyết hết vấn đề?
3. Bất biến và hợp đồng nào cần được xác định rõ?
4. Cần những cơ chế nào để tránh giữ ghế hoặc thu tiền trùng khi người dùng thử lại?
5. Những kiểm thử nào phát hiện được lỗi này?

**Gợi ý đối chiếu:** Có thể đã giảm ghế và thu tiền nhưng chưa có đơn đặt vé. Đổi thứ tự vẫn để lại khoảng lỗi giữa DB và cổng thanh toán. Cần quy định cách giữ ghế có thời hạn, trạng thái đơn hàng, giới hạn bán vượt số ghế, quy tắc thanh toán một lần cho một ý định đặt vé và xử lý thanh toán chưa rõ kết quả. Một thiết kế khả thi có thể ghi đơn ở trạng thái chờ trong giao dịch, dùng idempotency key khi thanh toán, cập nhật trạng thái khi có kết quả, bù trừ hoặc đối soát khi cần. Kiểm thử phải mô phỏng timeout, lỗi ghi DB, retry và hai yêu cầu đặt cùng ghế đồng thời.

## 12. Ghi nhớ

- **Thứ tự thao tác** ảnh hưởng tới tính đúng đắn vì lỗi có thể xảy ra sau bất kỳ bước nào, kể cả khi từng bước riêng lẻ tính toán đúng.
- **Trạng thái cập nhật một phần** cần được ngăn ngừa bằng tính nguyên tử hoặc được mô hình hóa như trạng thái hợp lệ có cơ chế phục hồi.
- **Kiểm tra trước và tính toán trước** giảm rủi ro trong một đối tượng; **giao dịch** xử lý nhóm thay đổi bền vững trong ranh giới tài nguyên hỗ trợ.
- **Tính cô lập, idempotency, outbox và bù trừ** giải quyết các rủi ro khác nhau của cạnh tranh, retry và giao tiếp giữa các hệ thống.
- Để đánh giá mã nguồn đáng tin cậy, phải xác minh **bất biến, trạng thái sau lỗi, tác động phụ và khả năng khôi phục**, không chỉ kiểm tra luồng thành công.
