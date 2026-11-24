# Exchange rate freshness: bảo vệ độ mới của tỷ giá

## 1. Tỷ giá đúng định dạng vẫn có thể sai về nghiệp vụ

Trong chương **Currency Handling**, *exchange rate freshness* là khả năng xác định một tỷ giá còn đủ mới để dùng cho một hành động cụ thể hay không. Câu hỏi cần trả lời không chỉ là “tỷ giá bằng bao nhiêu”, mà còn là:

> Tỷ giá này phản ánh dữ liệu vào thời điểm nào, lấy từ nguồn nào, và hệ thống còn được phép chấp nhận một giao dịch mới dựa trên nó đến lúc nào?

Một tỷ giá có thể dương, có đủ chữ số thập phân và đến từ nhà cung cấp hợp lệ nhưng đã quá cũ. Nếu backend tiếp tục chấp nhận, người dùng có thể chọn thời điểm có lợi để mua bằng giá cũ, giữ một báo giá quá lâu rồi thực hiện, hoặc gửi lại yêu cầu đã hết hạn. Đây là rủi ro logic nghiệp vụ: các request riêng lẻ đều hợp lệ về cú pháp nhưng làm sai điều kiện mà sản phẩm đã cam kết.

Ví dụ minh họa, không phải dữ liệu thị trường:

- Dữ liệu tham chiếu nói `1 USD = 25.000 VND` tại `09:00:00Z`.
- Chính sách sản phẩm cho phép dùng dữ liệu đó để tạo và chấp nhận báo giá mới trong tối đa 120 giây.
- Lúc `09:05:00Z`, cache vẫn trả về cùng giá trị.
- Nếu backend chỉ kiểm tra cache hit và tỷ giá lớn hơn không, người gọi vẫn có thể giao dịch theo dữ liệu đã vượt giới hạn.

Độ mới của tỷ giá gắn với business invariants, state machine, quyền theo đối tượng, transaction, idempotency và kiểm thử lạm dụng. Nó không phải một thuộc tính giao diện có thể bảo vệ bằng đồng hồ đếm ngược trên trình duyệt.

Bài này xét hai tình huống cần phân biệt: báo giá chỉ được chấp nhận khi dữ liệu còn đủ mới, và báo giá đã được bảo đảm bằng một cam kết riêng. Không mặc định rằng mọi hệ thống có cùng quy tắc hết hạn.

## 2. Phân biệt các mốc thời gian và loại giá

### 2.1. Một trường timestamp không đủ

| Mốc thời gian | Ý nghĩa | Điều không chứng minh được |
|---|---|---|
| `observedAt` | Thời điểm tỷ giá phản ánh một quan sát hoặc lần xác định giá theo định nghĩa của nguồn | Không nhất thiết là thời điểm backend vừa nhận dữ liệu |
| `publishedAt` | Thời điểm nguồn công bố bản dữ liệu, nếu có | Công bố lại không chắc là một quan sát mới |
| `receivedAt` | Thời điểm connector hoặc backend nhận bản dữ liệu | Không làm dữ liệu nguồn mới hơn |
| `cachedAt` | Thời điểm ghi vào cache | Không được dùng để thay thế tuổi của dữ liệu thị trường |
| `quoteCreatedAt` | Thời điểm server tạo báo giá cho một nghiệp vụ | Không chứng minh tỷ giá đầu vào còn mới |
| `expiresAt` | Hạn cuối được chấp nhận của báo giá theo chính sách | Không mặc nhiên có giá trị nếu client tự gửi |
| `acceptedAt` | Thời điểm hệ thống quyết định chấp nhận lệnh theo giao thức đã định nghĩa | Không nhất thiết trùng thời điểm commit hoặc quyết toán bên ngoài |

Hợp đồng dữ liệu phải nói rõ `observedAt` là thời điểm giao dịch gần nhất, lần chụp giá, bản fixing theo ngày hay thời điểm giá bắt đầu có hiệu lực. Không thể đổi tên mọi timestamp của nhà cung cấp thành `observedAt` rồi suy ra cùng một ý nghĩa.

Nếu nguồn chỉ cung cấp thời gian nhận mà không có thông tin đáng tin cậy về thời gian của dữ liệu, hệ thống không thể khẳng định tuổi thật của tỷ giá chỉ từ timestamp cục bộ. Cần chính sách riêng dựa trên cam kết về độ trễ đầu nguồn, loại dữ liệu và mức rủi ro; không tự gán thời gian hiện tại để làm dữ liệu có vẻ mới.

### 2.2. Giá tham chiếu khác giá thực hiện

- **Reference rate:** giá tham chiếu để định giá, hiển thị hoặc làm đầu vào.
- **Executable rate:** tỷ giá thực hiện theo chiều mua hoặc bán, có thể đã phản ánh spread và điều kiện sản phẩm.
- **Quote:** báo giá cho một giao dịch cụ thể, gắn với số tiền, cặp tiền, chiều đổi, phí, cách làm tròn và thời hạn.
- **Guaranteed quote:** báo giá được bảo đảm theo một cam kết có hiệu lực riêng, chẳng hạn cơ chế giữ giá hoặc khóa giá.

Một giá tham chiếu mới không tự động là mức giá mà hệ thống được phép giao dịch không giới hạn. Báo giá phải gắn với số tiền hoặc hạn mức phù hợp. Một quote còn hạn cũng không chứng minh rằng dữ liệu nguồn vẫn đáp ứng quy tắc độ mới, trừ khi cách tính hạn đã bảo đảm điều đó hoặc một cam kết riêng cho phép.

### 2.3. Cache TTL khác hạn chấp nhận nghiệp vụ

Cache TTL quản lý thời gian lưu hoặc thời gian có thể tái sử dụng một bản ghi trong cache. Hạn nghiệp vụ quyết định có được tạo ra nghĩa vụ tiền tệ hay không.

Ví dụ, TTL cache là 5 phút để phục vụ hiển thị, nhưng tuổi dữ liệu tối đa cho một giao dịch chỉ là 30 giây. Backend không được chấp nhận giao dịch trong toàn bộ 5 phút chỉ vì cache chưa hết hạn.

Chiều ngược lại cũng cần chú ý: cache có TTL 10 giây nhưng dữ liệu nhận từ nguồn đã cũ 20 phút. Làm mới cache liên tục không biến dữ liệu đó thành mới.

## 3. Định nghĩa invariant và chính sách độ mới

### 3.1. Mô hình nghiêm ngặt dùng trong ví dụ

Bài này dùng mô hình **báo giá không có cam kết giữ giá riêng**, với các điều kiện:

~~~text
source được phép dùng cho loại nghiệp vụ
cặp tiền và chiều tỷ giá khớp với lệnh
rate > 0
observedAt <= receivedAt <= decisionTime
decisionTime < observedAt + maxRateAge
decisionTime < quote.expiresAt
quote thuộc đúng actor hoặc chủ thể được phép sử dụng
quote chưa được dùng cho một lệnh nghiệp vụ khác
nội dung lệnh khớp nội dung quote bất biến
~~~

`decisionTime` là thời gian server dùng để quyết định chấp nhận. Trong mô hình này, timestamp tương lai bị từ chối thay vì tự kéo dài tuổi thọ dữ liệu. Hệ thống thực tế có thể cho phép một sai lệch đồng hồ nhỏ, nhưng phải định nghĩa rõ dung sai và cách tính hạn bảo thủ; không mặc nhiên cộng dung sai vào thời hạn giao dịch.

Thời gian và khoảng thời gian phải dùng đơn vị, múi giờ và độ chính xác nhất quán. Có thể biểu diễn bằng instant UTC để trao đổi, rồi định dạng theo múi giờ người dùng khi hiển thị. Không so sánh chuỗi giờ địa phương thiếu ngày hoặc thiếu offset.

### 3.2. Tuổi dữ liệu và hạn quote

Với quy tắc không có giữ giá riêng:

~~~text
rateDeadline = observedAt + maxRateAge

quote.expiresAt =
    min(quoteCreatedAt + quoteTtl, rateDeadline)
~~~

Nếu cần chừa thời gian cho độ lệch đồng hồ hoặc xử lý, có thể trừ một khoảng dự phòng đã định nghĩa khỏi hạn phù hợp. Khoảng dự phòng phải nhỏ hơn cửa sổ được phép và được quản lý như chính sách, không phải một hằng số tùy tiện ở mỗi service.

Ví dụ:

| Thuộc tính | Giá trị minh họa |
|---|---|
| `observedAt` | `09:00:00Z` |
| `receivedAt` | `09:00:02Z` |
| `maxRateAge` | 120 giây |
| `quoteCreatedAt` | `09:01:45Z` |
| `quoteTtl` | 60 giây |
| Hạn theo tuổi dữ liệu | `09:02:00Z` |
| Hạn theo TTL quote | `09:02:45Z` |
| `quote.expiresAt` thực tế | `09:02:00Z` |

Quote này chỉ còn 15 giây để được chấp nhận. Nếu sản phẩm yêu cầu mỗi quote phải có ít nhất 20 giây sử dụng, server cần lấy dữ liệu mới hoặc từ chối tạo quote; không được kéo `expiresAt` vượt `rateDeadline`.

Dùng khoảng nửa mở: hợp lệ khi `decisionTime < expiresAt`, hết hạn khi `decisionTime >= expiresAt`. Các thành phần phải thống nhất cùng quy ước, kể cả tại đúng mili giây hết hạn.

### 3.3. Chọn thời điểm mà hệ thống cam kết

Trong ví dụ của bài, hiệu lực được đánh giá tại `acceptedAt`, được xác lập trong vùng xử lý có khóa hoặc cập nhật có điều kiện rồi lưu cùng giao dịch.

Nếu lệnh được chấp nhận tại `09:01:59Z` và commit tại `09:02:01Z`, nó có thể vẫn hợp lệ theo chính sách “chấp nhận trước hạn”. Không được mô tả thiết kế này là bảo đảm “commit trước hạn”.

Ngược lại, chỉ nhận HTTP request vào hàng đợi lúc `09:01:59Z` chưa có nghĩa là đã chấp nhận báo giá. Nếu worker chỉ quyết định lúc `09:02:10Z`, worker phải kiểm tra hạn tại thời điểm đó.

Nếu sản phẩm yêu cầu một mốc khác, như được nhà cung cấp xác nhận trước hạn, cần giao thức tương ứng với nhà cung cấp. Một lần so sánh đồng hồ ở API không đủ bảo đảm điều kiện đó.

### 3.4. Freshness không đồng nghĩa với giá hợp lý

Dữ liệu có thể mới nhưng sai chiều cặp tiền, sai nguồn, sai đơn vị hoặc có giá trị bất thường. Dữ liệu cũng có thể nằm trong giới hạn tuổi nhưng thị trường đã biến động mạnh trong khoảng đó.

Vì vậy, cần kiểm tra cả nguồn, chiều tỷ giá, phạm vi giá trị, loại nghiệp vụ và các ngưỡng biến động mà sản phẩm định nghĩa. Giới hạn tuổi không thay thế các kiểm soát đó. Một ngưỡng phát hiện bất thường cũng không cho phép dùng dữ liệu vô thời hạn.

## 4. Mô hình dữ liệu: rate snapshot và quote bất biến

Có thể tách bản dữ liệu nguồn khỏi báo giá nghiệp vụ:

~~~text
RateSnapshot
  rateId
  providerId
  providerSequenceOrRevision
  baseCurrency
  quoteCurrency
  rate
  observedAt
  publishedAt (nếu nguồn có)
  receivedAt
  sourceKind
  qualityStatus

FxQuote
  quoteId
  tenantId
  actorId hoặc subjectId có quyền sử dụng
  sourceAccountId
  destinationAccountId hoặc beneficiaryReference
  sourceCurrency
  targetCurrency
  sourceAmount
  sourceFee
  totalDebitAmount
  targetAmount
  executableRate
  rateSnapshotId
  pricingPolicyVersion
  createdAt
  expiresAt
  status
  version
~~~

Một dòng quote có thể chỉ lưu số tiền đã làm tròn cuối cùng và các tham chiếu đủ để tái dựng cách tính. Thiết kế cụ thể tùy sản phẩm, nhưng phải giữ được bằng chứng về giá và điều kiện đã được chấp thuận.

Ví dụ minh họa:

~~~text
Chiều tỷ giá: 1 USD đổi được 25.000 VND ở giá tham chiếu.
Chính sách giá ví dụ: executableRate = referenceRate × 0,996.
Executable rate: 24.900 VND/USD.

Source amount được đem đổi: 100 USD.
Phí thu thêm ở tài khoản nguồn: 1 USD.
Tổng ghi nợ: 101 USD.
Số tiền nhận: 2.490.000 VND.
~~~

Các con số và công thức spread chỉ phục vụ minh họa. Nếu phí được trừ vào số tiền đem đổi hoặc thu bằng loại tiền khác, quote phải biểu diễn đúng cách tính đó. Cần làm tròn theo quy tắc được lưu cùng chính sách, không để từng client tự quyết.

Sau khi tạo quote, không cập nhật tỷ giá hoặc số tiền của quote đó tại chỗ. Khi điều kiện giá thay đổi, tạo quote mới có ID mới. Người dùng cần được xác nhận lại nếu giá, phí hoặc số tiền nhận thay đổi ngoài điều kiện đã chấp thuận.

Quote phải gắn với tài khoản nguồn và điều kiện sử dụng để người có một quote tốt không thể áp dụng nó cho tài khoản, người nhận hoặc số tiền khác. Quyền đọc quote cũng cần được bảo vệ, vì quote có thể chứa thông tin giao dịch hoặc tài khoản.


## 5. Từ dữ liệu nguồn đến quyết định chấp nhận

### 5.1. Kiểm tra khi nhận dữ liệu

Connector cần xác nhận nguồn được phép sử dụng và kiểm tra:

- Cặp tiền và chiều tỷ giá được ánh xạ rõ ràng.
- Giá trị số hợp lệ, dương, trong phạm vi xử lý được.
- Timestamp có ý nghĩa theo hợp đồng nguồn, không nằm tương lai ngoài chính sách.
- Sequence hoặc revision phù hợp, nếu nguồn có cung cấp.
- Bản cập nhật đến muộn không vô tình ghi đè snapshot mới bằng snapshot cũ.
- Trạng thái chất lượng cho phép dùng vào giao dịch, thay vì chỉ cho hiển thị hoặc phân tích.

Nếu provider hỗ trợ chỉnh sửa dữ liệu đã công bố, một revision mới có thể sửa giá của cùng thời điểm quan sát. Cần lưu được sự kiện sửa và cập nhật theo quy tắc của nguồn; chỉ so sánh timestamp rồi bỏ mọi bản có timestamp bằng nhau có thể làm mất bản sửa hợp lệ.

Lưu cả thời điểm nguồn và thời điểm nhận. Độ trễ từ nguồn đến hệ thống là tín hiệu vận hành, nhưng không được dùng để viết lại lịch sử quan sát.

### 5.2. Kiểm tra khi tạo quote

Khi người dùng yêu cầu đổi tiền:

1. Xác thực danh tính, tenant và quyền trên tài khoản nguồn.
2. Chuẩn hóa cặp tiền, chiều đổi, số tiền và chính sách phí.
3. Chọn snapshot đúng nguồn, loại dữ liệu và điều kiện chất lượng.
4. Kiểm tra tuổi dữ liệu ngay lúc tạo quote.
5. Tính số tiền cuối cùng với độ chính xác và làm tròn xác định.
6. Tính `expiresAt` từ cả tuổi dữ liệu và thời hạn quote.
7. Lưu quote bất biến và trả về ID cùng các điều kiện để người dùng xác nhận.

Nếu chỉ kiểm tra ở connector, snapshot có thể đã cũ trước lúc người dùng yêu cầu quote. Nếu chỉ kiểm tra lúc tạo quote, người dùng có thể chờ quá lâu trước khi xác nhận.

### 5.3. Kiểm tra lại khi chấp nhận

Một lệnh xác nhận có thể chỉ cần:

~~~http
POST /fx-conversions
Authorization: Bearer <token>
Idempotency-Key: fx-operation-001
Content-Type: application/json

{
  "quoteId": "quote-001"
}
~~~

Backend không cần nhận lại tỷ giá như một giá trị có quyền quyết định. Nếu request có thêm các trường dùng để người dùng xác nhận số tiền, chúng phải khớp với quote đã lưu; không được ghi đè quote.

Trong transaction chấp nhận, backend cần:

- Kiểm tra quyền đọc và sử dụng quote trong đúng phạm vi.
- Kiểm tra trạng thái và hạn tại thời điểm quyết định sau khi đã chờ các khóa cần thiết.
- Kiểm tra lại quyền ghi nợ, trạng thái tài khoản, tiền khả dụng, phê duyệt và hạn mức.
- Ràng buộc quote với đúng lệnh, ngăn tiêu thụ hai lần.
- Ghi nợ, ghi có hoặc ghi nhận nghĩa vụ đổi tiền theo mô hình sản phẩm.
- Lưu ledger, kết quả idempotency và sự kiện cần gửi theo cùng ranh giới nguyên tử cục bộ.

Freshness không tạo quyền ghi nợ. Một quote còn hạn vẫn phải bị từ chối nếu quyền chi tiêu đã bị thu hồi theo giao thức đồng thời của hệ thống.

### 5.4. State machine của quote

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE: Tạo quote hợp lệ
    ACTIVE --> CONSUMED: Chấp nhận đúng quyền và trước hạn
    ACTIVE --> EXPIRED: Đã tới hạn sử dụng
    ACTIVE --> CANCELLED: Hủy theo chính sách
    ACTIVE --> REPLACED: Tạo quote thay thế và vô hiệu quote cũ
    CONSUMED --> [*]
    EXPIRED --> [*]
    CANCELLED --> [*]
    REPLACED --> [*]
~~~

Không phải hệ thống nào cũng cần lưu mọi trạng thái như trên. `EXPIRED` có thể được suy ra khi đọc dựa trên `expiresAt`. Dù có job đánh dấu hết hạn hay không, đường chấp nhận vẫn phải kiểm tra timestamp; job chạy chậm không được kéo dài hiệu lực.

Tạo một quote mới không tự động làm quote cũ hết hiệu lực. Nếu sản phẩm chỉ cho phép một quote hoạt động cho một ý định giao dịch, cần lưu quan hệ thay thế và thực thi điều kiện đó nguyên tử. Nếu cho phép nhiều quote còn hạn, phải chủ động chấp nhận rủi ro người dùng chọn quote thuận lợi trong cửa sổ đã cam kết.

## 6. Java minh họa cách đánh giá độ mới

Đoạn mã sau là thành phần minh họa cho mô hình nghiêm ngặt ở trên. Nó không bao gồm repository, kiểm tra quyền, transaction, đầy đủ xử lý lỗi đầu vào hoặc tích hợp provider.

~~~java
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;

record RateSnapshot(
        String rateId,
        String providerId,
        String baseCurrency,
        String quoteCurrency,
        BigDecimal rate,
        Instant observedAt,
        Instant receivedAt) {}

record FreshnessPolicy(
        Duration maxRateAge,
        Duration quoteTtl) {}

final class RateFreshness {
    static Instant expiryForNewQuote(
            RateSnapshot rate,
            FreshnessPolicy policy,
            Instant createdAt) {

        if (policy.maxRateAge().isZero()
                || policy.maxRateAge().isNegative()
                || policy.quoteTtl().isZero()
                || policy.quoteTtl().isNegative()) {
            throw new IllegalArgumentException("Invalid freshness policy");
        }

        if (rate.rate().signum() <= 0) {
            throw new IllegalArgumentException("Invalid exchange rate");
        }

        // Mô hình nghiêm ngặt: không chấp nhận timestamp tương lai.
        if (rate.observedAt().isAfter(rate.receivedAt())
                || rate.receivedAt().isAfter(createdAt)) {
            throw new IllegalArgumentException("Invalid rate timestamps");
        }

        Instant rateDeadline =
                rate.observedAt().plus(policy.maxRateAge());

        if (!createdAt.isBefore(rateDeadline)) {
            throw new StaleRateException();
        }

        Instant quoteDeadline = createdAt.plus(policy.quoteTtl());

        return quoteDeadline.isBefore(rateDeadline)
                ? quoteDeadline
                : rateDeadline;
    }

    static void requireAcceptableAt(
            RateSnapshot rate,
            Instant storedQuoteExpiresAt,
            FreshnessPolicy effectivePolicy,
            Instant acceptedAt) {

        // Áp dụng cả giới hạn hiện hành nếu chính sách sản phẩm yêu cầu.
        Instant currentRateDeadline =
                rate.observedAt().plus(effectivePolicy.maxRateAge());

        if (rate.observedAt().isAfter(rate.receivedAt())
                || rate.receivedAt().isAfter(acceptedAt)
                || !acceptedAt.isBefore(storedQuoteExpiresAt)
                || !acceptedAt.isBefore(currentRateDeadline)) {
            throw new ExpiredQuoteException();
        }
    }
}
~~~

Các điều kiện không thể suy ra chỉ từ đoạn mã:

- Snapshot phải lấy từ kho dữ liệu tin cậy, đúng nguồn và cặp tiền; client không được tự tạo một `RateSnapshot` có timestamp mới.
- Cấu hình phải được kiểm tra đầy đủ, kể cả giá trị rỗng, khoảng thời gian vượt phạm vi, giới hạn tối đa và lỗi phân tích timestamp. Lỗi thời gian phải từ chối giao dịch, không chuyển thành “bỏ qua freshness”.
- `effectivePolicy` phải là chính sách có hiệu lực do server xác định. Không nhận `maxRateAge` hoặc `quoteTtl` từ request.
- Trong ví dụ, chính sách hiện hành có thể rút ngắn cửa sổ khi chấp nhận, nhưng không tự kéo dài `storedQuoteExpiresAt`. Nếu sản phẩm bảo đảm chính sách tại lúc phát hành quote, cần cơ chế phiên bản và cam kết tương ứng, thay vì áp dụng tùy tiện quy tắc mới.
- `acceptedAt` phải lấy sau khi chờ khóa và ngay tại điểm quyết định. Không truyền vào thời điểm lấy từ client, lúc bắt đầu request hoặc một giá trị cũ trước khi chờ hàng đợi.

Nên truyền `Clock` hoặc một nguồn thời gian có thể kiểm soát vào tầng nghiệp vụ để kiểm thử. Khi dùng thời gian của cơ sở dữ liệu, cần biết hàm thời gian đang lấy thời điểm thực thi câu lệnh hay thời điểm bắt đầu transaction. Một giá trị bị cố định từ đầu transaction có thể đã cũ sau khi chờ khóa.

Một nguyên tắc triển khai là dùng cùng nguồn thời gian chuẩn cho cả việc kiểm tra và lưu `acceptedAt`. Hệ thống nhiều node vẫn cần theo dõi độ lệch đồng hồ; định dạng UTC không tự đồng bộ hóa các đồng hồ vật lý.

## 7. Chấp nhận nguyên tử và xử lý retry

### 7.1. Không tách kiểm tra hạn khỏi việc tiêu thụ quote

Luồng nguy hiểm:

~~~text
Đọc quote → thấy còn hạn.
Chờ khóa tài khoản hoặc gọi dịch vụ ngoài.
Một khoảng thời gian trôi qua.
Đánh dấu quote đã dùng và chuyển tiền mà không kiểm tra lại.
~~~

Có thể khắc phục bằng một giao thức như:

~~~text
BEGIN
  Nhận quyền xử lý idempotency trong đúng phạm vi.
  Khóa quote, tài khoản và dữ liệu quyền theo thứ tự thống nhất.
  Lấy decisionTime mới.
  Kiểm tra quyền, nội dung quote, trạng thái, hạn và tuổi dữ liệu.
  Tiêu thụ quote bằng thay đổi trạng thái có điều kiện.
  Ghi nhận chuyển đổi, ledger, hạn mức, kết quả lệnh và outbox.
COMMIT
~~~

Khóa quote ngăn hai transaction tiêu thụ cùng quote, nhưng không làm thời gian ngừng trôi. Kiểm tra hạn phải nằm ở điểm quyết định đã chọn sau thời gian chờ cần thiết. Các đường ghi khác cũng phải tuân theo cùng cơ chế bảo vệ trạng thái.

SQL minh họa cho phần chuyển trạng thái sau khi đã giải quyết các điều kiện còn lại:

~~~sql
UPDATE fx_quote
SET status = 'CONSUMED',
    accepted_at = :decision_time,
    conversion_id = :conversion_id,
    version = version + 1
WHERE quote_id = :quote_id
  AND tenant_id = :tenant_id
  AND actor_id = :actor_id
  AND status = 'ACTIVE'
  AND expires_at > :decision_time
  AND version = :expected_version;
~~~

Ví dụ dùng quote gắn với một actor cá nhân. Với tài khoản tổ chức hoặc quyền đại diện, cần thay điều kiện `actor_id` bằng chính sách đối tượng tương ứng. Không bỏ kiểm tra quyền chỉ để hỗ trợ nhiều người dùng.

Số dòng cập nhật phải bằng một. Câu lệnh không kiểm tra toàn bộ tuổi dữ liệu, quyền chi tiêu hoặc tiền khả dụng; các điều kiện đó vẫn phải được bảo vệ trong cùng giao thức. Nếu ghi tiền thất bại, thay đổi trạng thái quote cũng phải rollback.

### 7.2. Retry sau hết hạn không luôn là lệnh mới

Giả sử conversion đã commit trước hạn nhưng client không nhận được response. Client retry sau `expiresAt`:

- Nếu đó là cùng lệnh đã commit, trả lại kết quả cũ sau kiểm tra quyền truy cập; không định giá lại, không chuyển tiền thêm.
- Nếu lệnh chưa từng được chấp nhận thành công, quote hết hạn phải bị từ chối.
- Nếu cùng khóa idempotency nhưng đổi `quoteId` hoặc nội dung ảnh hưởng đến lệnh, trả xung đột.

Một khóa idempotency nên có phạm vi phù hợp, chẳng hạn:

~~~text
unique(tenantId, actorId, operationType, idempotencyKey)
fingerprint = biểu diễn chuẩn hóa của quoteId và nội dung lệnh liên quan
~~~

Ràng buộc một quote chỉ được tiêu thụ cho một conversion vẫn cần tồn tại độc lập. Nếu chỉ dựa vào idempotency key của request, người gọi có thể gửi khóa mới để cố tiêu thụ quote lần nữa.

Không tự tạo một quote mới dưới cùng khóa rồi thực hiện với số tiền nhận khác. Việc chấp nhận một giá mới phải tuân theo sự đồng ý hoặc giới hạn biến động giá mà người dùng đã cấp.

### 7.3. Phê duyệt không làm quote sống mãi

Trong luồng tổ chức, yêu cầu có thể chờ người phê duyệt lâu hơn tuổi thọ quote. Cần chọn một trong các chính sách rõ ràng:

- Chỉ phê duyệt khi quote còn hạn và vẫn kiểm tra lại tại lúc chấp nhận.
- Phê duyệt ý định hoặc hạn mức, sau đó tạo quote mới và xác nhận lại điều kiện giá theo quy tắc được định nghĩa.
- Dùng một cơ chế giữ giá thực sự có đủ thời hạn và căn cứ bảo đảm.

Không đổi timestamp của quote sau khi được phê duyệt. Không để một phê duyệt cho 100 USD và một người nhận cụ thể áp dụng tự động cho số tiền hoặc bên nhận khác.


## 8. Khi nào một quote được phép sống lâu hơn dữ liệu nguồn?

Không phải mọi báo giá đều phải hết hạn tại `observedAt + maxRateAge`. Một báo giá có thể được bảo đảm bằng một thỏa thuận riêng có hiệu lực lâu hơn. Khi đó, dữ liệu cũ không được “làm mới”; hệ thống đang dựa vào **một căn cứ cam kết khác**.

Cần lưu được các điều kiện như:

~~~text
guaranteeReference
guaranteeingParty
guaranteedRate hoặc số tiền nhận được bảo đảm
guaranteedSourceAmount hoặc hạn mức
validUntil
quyền sử dụng và điều kiện hủy
providerQuoteId (nếu có)
trạng thái đã giữ, đã dùng, đã hủy hoặc chưa rõ kết quả
~~~

Invariant trở thành: giao dịch phải dùng đúng cam kết còn hiệu lực, đúng đối tượng, đúng số tiền và đúng điều kiện thực thi. Không chỉ thêm `guaranteed=true` do client gửi rồi bỏ kiểm tra tuổi dữ liệu.

Nếu chính hệ thống chịu rủi ro giữ giá, cần mô hình hóa ngân sách, hạn mức và nghĩa vụ tương ứng. Nếu nhà cung cấp bảo đảm, cần biết khi nào nhà cung cấp xem lệnh là đã được chấp nhận. Được API nội bộ chấp nhận trước hạn không tự chứng minh nhà cung cấp cũng sẽ thực hiện sau đó.

Ví dụ, một worker đọc outbox chậm 30 giây có thể gửi lệnh sau thời hạn của provider. Outbox bảo đảm lưu được ý định gửi cùng transaction cục bộ; nó không kéo dài hiệu lực cam kết bên ngoài.

Khi kết quả bên ngoài chưa rõ vì timeout, không tự kết luận rằng quote chưa dùng rồi cho phép một lệnh đổi tiền thứ hai. Cần truy vấn, đối soát hoặc tiếp tục cùng định danh lệnh theo cơ chế của nhà cung cấp. Thay giá, hoàn tác hay giải phóng tiền đều phải có căn cứ trạng thái, tránh vừa thực hiện ngoài hệ thống vừa hoàn tiền trong hệ thống.

## 9. Cache, nguồn dự phòng và lịch thị trường

### 9.1. Nguyên tắc dùng dữ liệu cũ

| Tình huống | Cách xử lý phù hợp |
|---|---|
| Cache hit nhưng dữ liệu quá tuổi cho giao dịch | Không chấp nhận lệnh mới dựa trên snapshot đó |
| Nguồn lỗi nhưng snapshot còn trong giới hạn đã định nghĩa | Có thể dùng nếu chính sách nguồn và chất lượng vẫn cho phép |
| Snapshot đã quá tuổi, chưa có nguồn dự phòng hợp lệ | Tạm ngừng tạo hoặc chấp nhận báo giá theo luồng nghiêm ngặt |
| Giao diện chỉ hiển thị thông tin tham khảo | Có thể hiển thị dữ liệu cũ nếu sản phẩm cho phép và ghi rõ thời điểm, tình trạng |
| Có cam kết giữ giá riêng còn hiệu lực | Xử lý theo cam kết và trạng thái của nó, không đổi tuổi dữ liệu nguồn |
| Nguồn có bản mới nhưng đến muộn hoặc sai thứ tự | Áp dụng quy tắc sequence, revision và thời điểm theo hợp đồng nguồn |

Một tác vụ refresh mỗi phút không chứng minh dữ liệu luôn mới dưới một phút. Tác vụ có thể lỗi, nguồn có thể trả lại bản cũ hoặc hàng đợi có thể bị chậm.

Cơ chế “trả bản cũ trong lúc tải bản mới” có thể hữu ích cho hiển thị, nhưng không được tự động trở thành chính sách chấp nhận giao dịch tiền tệ. Cần tách luồng có thể dùng dữ liệu cũ khỏi luồng có ràng buộc tuổi.

### 9.2. Nguồn dự phòng cần tương thích về nghĩa

Không thay nguồn A bằng nguồn B chỉ vì B trả một con số mới hơn. Cần so khớp:

- Cùng cặp tiền và chiều quy đổi.
- Cùng loại giá, chẳng hạn tham chiếu, mua, bán hoặc giá được phép thực hiện.
- Ý nghĩa timestamp và độ trễ nguồn.
- Chính sách spread, phí, hạn mức và làm tròn.
- Điều kiện chấp nhận nguồn và ngưỡng chất lượng.

Nếu phải nghịch đảo tỷ giá, cần định nghĩa đúng chiều và làm tròn theo chính sách. Không lấy giá mua của một chiều rồi mặc định nghịch đảo của nó chính là giá bán có thể thực hiện ở chiều ngược lại.

Quote đã phát hành phải giữ nguồn và điều kiện giá của chính nó. Chuyển nguồn cho các quote mới không được sửa âm thầm quote cũ.

### 9.3. Không dùng sai lịch thị trường

Một nguồn có thể công bố giá theo phiên, theo ngày hoặc chỉ khi có sự kiện. Trong khoảng không có phiên mới, một giá cũ theo thời gian thực có thể vẫn là bản công bố mới nhất.

“Bản mới nhất” và “đủ mới để giao dịch” là hai khái niệm khác nhau. Sản phẩm phải định nghĩa có cho phép dùng giá đóng cửa hoặc fixing ngoài phiên hay không, trong thời gian nào, với loại nghiệp vụ và hạn mức nào.

Nếu cho phép, lưu `sourceKind` và chính sách tương ứng để không gắn nhãn dữ liệu đó thành giá thị trường trực tiếp vừa được quan sát. Không nới ngưỡng tùy tiện chỉ vì hệ thống gặp lỗi nguồn; lịch dự kiến và sự cố nguồn là hai tình huống cần được nhận diện riêng.

### 9.4. Phát hiện đồng hồ và độ trễ bất thường

Nên theo dõi ít nhất:

- Tuổi snapshot được dùng để tạo quote và chấp nhận conversion.
- Khoảng trễ giữa thời điểm nguồn và thời điểm nhận.
- Thời gian từ lúc nhận dữ liệu tới lúc quote được dùng.
- Độ trễ hàng đợi và thời gian chờ khóa.
- Tần suất timestamp tương lai hoặc dữ liệu sai thứ tự.
- Số lần từ chối vì stale rate, quote hết hạn hoặc nguồn không hợp lệ.
- Tỷ lệ fallback và những lần nguồn dự phòng không đạt điều kiện.

Những chỉ số này giúp phân biệt “provider đang chậm” với “worker xử lý chậm” hoặc “đồng hồ node bị lệch”. Ngưỡng cảnh báo phải xuất phát từ cửa sổ chấp nhận thực tế của sản phẩm, không chỉ từ tỷ lệ lỗi HTTP.

Trong audit của conversion, lưu quote ID, snapshot ID, nguồn, phiên bản chính sách, `observedAt`, `expiresAt` và `acceptedAt`. Không chỉ lưu con số tỷ giá, vì con số đó không chứng minh giao dịch đã được chấp nhận đúng thời hạn.

## 10. Những cách lạm dụng cần nhận diện

### 10.1. Sửa tỷ giá hoặc thời hạn trong request

Người gọi gửi `rate` có lợi hơn, kéo dài `expiresAt` hoặc đổi `observedAt` thành hiện tại.

Biện pháp bảo vệ là dùng quote đã lưu hoặc nội dung quote được bảo vệ toàn vẹn bằng cơ chế server kiểm chứng. Dữ liệu do client trả lại chỉ là tham chiếu hoặc nội dung cần đối chiếu. Chữ ký hợp lệ của quote vẫn không thay thế kiểm tra trạng thái chưa dùng, quyền theo đối tượng và thời hạn hiện tại.

Nếu dùng quote tự chứa được ký, phải xác thực khóa, phạm vi sử dụng, phiên bản, hết hạn và các trường đã ràng buộc. Vẫn cần cơ chế tiêu thụ hoặc định danh nghiệp vụ để ngăn phát lại khi sản phẩm yêu cầu quote dùng một lần.

### 10.2. Làm mới timestamp mà không có quan sát mới

Một tiến trình đọc cache cũ rồi ghi lại `cachedAt=now`. Service sau dùng `cachedAt` để tính tuổi tỷ giá, khiến dữ liệu sống mãi.

Giữ nguyên timestamp nguồn và nguồn gốc dữ liệu qua mọi lớp cache. Mỗi lần copy không được trở thành một lần quan sát giá mới.

### 10.3. Giữ nhiều quote rồi chọn quote có lợi

Người dùng liên tục xin quote ở nhiều thời điểm và chỉ sử dụng quote tốt nhất khi thị trường đã đổi. Trong giới hạn mà sản phẩm đã chấp thuận, đây có thể là hành vi hợp lệ; nhưng nếu mô hình giá không dự tính quyền lựa chọn đó, hệ thống sẽ chịu rủi ro ngoài dự kiến.

Cần quy định thời hạn, số lượng quote hoạt động, phạm vi số tiền, điều kiện thay thế hoặc chi phí giữ giá. Giới hạn tần suất có thể giảm lạm dụng tài nguyên, nhưng không thay thế điều kiện hết hạn và phạm vi quote.

### 10.4. Bỏ qua phê duyệt hoặc dùng quote của người khác

Một người lấy `quoteId` từ log, lịch sử hoặc tài khoản khác, rồi xác nhận bằng danh tính của mình. Một người khác thay tài khoản nguồn sau khi quote đã được duyệt.

Backend phải kiểm tra quan hệ đối tượng, quyền chi tiền và nội dung đã phê duyệt. Quote khó đoán không tạo ra quyền sử dụng. Những thay đổi ảnh hưởng tới nghĩa vụ tiền tệ phải làm mất hiệu lực chấp thuận cũ hoặc đi qua quy trình sửa đổi đã định nghĩa.

### 10.5. Đẩy request vào hàng đợi trước hạn

Người gọi gửi hàng loạt request gần hết hạn và kỳ vọng chỉ cần timestamp lúc nhận HTTP là đủ. Nếu worker dùng thời gian đó thay vì điểm quyết định, quote có thể được chấp nhận lâu sau cửa sổ cho phép.

Ghi tách `requestReceivedAt` và `acceptedAt`. Không dùng mốc thứ nhất thay cho mốc thứ hai trong mô hình của bài.

### 10.6. Dùng lỗi nguồn để kéo dài giá cũ

Người dùng chờ lúc provider gián đoạn hoặc cố gây áp lực lên refresh để tận dụng quy tắc “nếu lỗi thì dùng giá gần nhất mãi mãi”.

Không kéo dài hạn khi lỗi. Nếu sản phẩm có chế độ giá dự phòng được phê duyệt, nó phải có giới hạn tuổi, hạn mức, nguồn và điều kiện riêng, đồng thời được ghi nhận trong audit.

## 11. Kiểm thử tình huống tấn công và ranh giới thời gian

Các ví dụ dưới đây dùng đồng hồ điều khiển được, không cần chờ thời gian thực. Cố định dữ liệu ở `09:00:00Z`, `maxRateAge=120s`, quote được tạo lúc `09:01:45Z` với `quoteTtl=60s`. Hạn hợp lệ là `09:02:00Z`.

| Tình huống | Kết quả cần chứng minh |
|---|---|
| Tạo quote từ dữ liệu đã quá tuổi | Bị từ chối; không phát hành quote có hiệu lực giả |
| Tạo quote lúc 09:01:45 | Hạn là 09:02:00, không phải 09:02:45 |
| Chấp nhận ngay trước 09:02:00 | Có thể thành công nếu mọi điều kiện khác hợp lệ |
| Chấp nhận đúng 09:02:00 | Bị từ chối theo quy tắc hết hạn tại biên |
| Chấp nhận sau 09:02:00 | Bị từ chối; không có biến động tiền |
| Client kéo dài `expiresAt` hoặc sửa `observedAt` | Không ảnh hưởng điều kiện server |
| Client chỉnh đồng hồ hoặc múi giờ | Không kéo dài quote |
| Dữ liệu nguồn có timestamp tương lai | Bị từ chối hoặc cách ly theo chính sách đã chọn, không nhận tuổi âm là còn mới |
| Cache vừa được ghi lại từ snapshot cũ | `observedAt` không đổi; dữ liệu vẫn bị coi là cũ |
| Provider trả lại cùng bản cũ sau refresh | Không được xem đó là một quan sát mới |
| Snapshot cũ đến sau snapshot mới | Không làm cache hoặc kho dữ liệu lùi về bản cũ ngoài quy tắc revision |
| Quote được gửi trước hạn nhưng worker quyết định sau hạn | Bị từ chối trong mô hình chấp nhận của bài |
| Request chờ khóa qua thời điểm hết hạn | Kiểm tra sau khi có khóa và từ chối |
| Người khác dùng quote còn hạn | Bị từ chối theo quyền đối tượng; không lộ chi tiết ngoài phạm vi |
| Thay số tiền, chiều tiền hoặc tài khoản sau khi duyệt | Không dùng lại quote và phê duyệt cũ trái chính sách |
| Hai request đồng thời tiêu thụ cùng quote | Chỉ một conversion có thể được chấp nhận |
| Dùng khóa idempotency khác để tiêu thụ lại quote | Không tạo conversion thứ hai |
| Retry sau hết hạn với lệnh đã commit | Trả kết quả cũ theo quyền đọc, không chuyển tiền thêm |
| Retry sau hết hạn với lệnh chưa được chấp nhận | Bị từ chối; không dùng timestamp request cũ |
| Cùng khóa idempotency nhưng đổi quote | Báo xung đột, không thay lệnh âm thầm |
| Lỗi ghi ledger hoặc ghi có trong transaction | Rollback cả biến động tiền, tiêu thụ quote và dữ liệu hạn mức liên quan |
| Provider gián đoạn, snapshot đã quá tuổi | Không tạo hoặc chấp nhận lệnh mới theo luồng nghiêm ngặt |
| Fallback có chiều tỷ giá hoặc loại giá khác | Bị từ chối trước khi tạo nghĩa vụ tiền tệ |
| Provider timeout sau khi có thể đã thực hiện | Không tự tạo lệnh thứ hai hoặc tự kết luận chưa đổi tiền |
| Quote được bảo đảm nhưng cam kết đã hết hạn hoặc sai số tiền | Bị từ chối dù snapshot lịch sử vẫn được lưu |
| Hạn mức độ mới được siết trong lúc quote đang hoạt động | Tuân theo chính sách phiên bản đã công bố; không tự kéo dài hạn đã lưu |

Kiểm thử đồng thời cần điều khiển thời điểm các request gặp nhau, chẳng hạn dùng barrier trong môi trường kiểm thử. Không dựa vào sleep ngẫu nhiên rồi suy ra race condition đã được xử lý.

Kiểm tra kết quả bền vững, không chỉ mã HTTP:

~~~text
Số conversion được chấp nhận.
Quote nào đã bị tiêu thụ và gắn với conversion nào.
Số dư, khoản giữ và hạn mức đã dùng.
Các bút toán ledger cùng loại tiền và chiều quy đổi.
Bản ghi idempotency cùng fingerprint.
acceptedAt so với expiresAt và rateDeadline.
Trạng thái lệnh gửi ra ngoài và dấu vết đối soát.
~~~

Với lệnh bị từ chối vì hết hạn, có thể lưu audit từ chối nhưng không được có tác động tiền tệ hoặc tiêu thụ hạn mức ngoài chính sách. Với lệnh đã commit rồi retry, phải chứng minh chỉ có một tác động tiền tệ.

Có thể kiểm tra các tính chất qua nhiều chuỗi thao tác:

~~~text
Mọi conversion mới trong mô hình nghiêm ngặt đều có:
  acceptedAt < quote.expiresAt
  acceptedAt < snapshot.observedAt + effectiveMaxRateAge

Không quote dùng một lần nào gắn với hai conversion thành công.
Không retry nào sửa giá trị đã chấp nhận của conversion cũ.
Không thao tác cache nào tự tăng thời điểm quan sát của dữ liệu nguồn.
Mọi conversion đều truy được quote, snapshot, nguồn và chính sách giá.
~~~

Khi chuyển sang mô hình giữ giá có bảo đảm, thay invariant tuổi dữ liệu tại lúc chấp nhận bằng các invariant cam kết tương ứng. Không giữ một kiểm thử luôn bỏ qua freshness chỉ vì hệ thống có một trường `guaranteed`.

## 12. Rà soát một đường xử lý tỷ giá

Có thể lần theo một giao dịch đổi tiền qua chuỗi sau:

~~~text
Nguồn dữ liệu và ý nghĩa timestamp
    → snapshot đúng cặp tiền và chiều đổi
    → tuổi dữ liệu theo chính sách
    → quote bất biến và có quyền sử dụng
    → thời hạn được tính từ căn cứ hợp lệ
    → kiểm tra tại điểm chấp nhận thực tế
    → tiêu thụ quote và cập nhật tiền nguyên tử
    → retry, hệ thống ngoài và đối soát
~~~

Với mỗi bước, xác định dữ liệu nào do server chứng minh, mốc thời gian nào đang được dùng và điều gì có thể thay đổi trước khi quyết định được lưu bền vững.

Một luồng bảo vệ tốt độ mới tỷ giá phải giải thích được **đã dùng dữ liệu nào, dữ liệu đó phản ánh thời điểm nào, căn cứ nào cho phép dùng nó, và lệnh được chấp nhận vào lúc nào**. Chỉ có một con số tỷ giá và trạng thái cache hit chưa đủ để bảo vệ quy tắc nghiệp vụ.
