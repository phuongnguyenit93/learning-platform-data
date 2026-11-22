# Chính sách, giá và hợp đồng có phiên bản theo thời gian

Trong Domain-Driven Design (DDD), nhiều quy tắc nghiệp vụ thay đổi theo thời gian. Giá bán hôm nay có thể khác giá hôm qua; chính sách hoàn tiền có thể được cập nhật từ đầu tháng sau; hợp đồng có thể được ký hôm nay nhưng chỉ có hiệu lực từ một ngày trong tương lai. Khi cần giải thích một quyết định cũ, hệ thống phải biết **phiên bản nào có hiệu lực tại thời điểm nghiệp vụ xảy ra**.

Nếu chỉ lưu một giá trị hiện tại rồi ghi đè khi có thay đổi, lịch sử sẽ biến mất. Một đơn hàng cũ có thể bị tính lại theo giá mới; một yêu cầu đã được duyệt có thể không giải thích được vì sao policy lúc đó cho phép; một tranh chấp hợp đồng có thể không xác định được điều khoản mà hai bên đã chấp thuận.

Cách tiếp cận là mô hình hóa **phiên bản, khoảng hiệu lực và lịch sử thay đổi** như dữ liệu nghiệp vụ có chủ đích. Cần phân biệt thời điểm một sự kiện có hiệu lực trong thế giới nghiệp vụ với thời điểm hệ thống ghi nhận thông tin đó. Khi hai thời điểm này có thể khác nhau, mô hình bitemporal giúp trả lời cả “điều gì đúng vào lúc đó?” và “lúc đó hệ thống đã biết điều gì?”.

## 1. Vì sao chính sách, giá và hợp đồng cần phiên bản?

### 1.1. Ghi đè giá trị hiện tại làm mất căn cứ của quyết định cũ

Giả sử một sản phẩm có giá 1.000.000 VND trong tháng 3 và tăng lên 1.100.000 VND từ ngày 1 tháng 4.

Nếu bảng Product chỉ lưu một field `current_price`, sau khi cập nhật giá, hệ thống không còn biết:

- Đơn hàng ngày 20 tháng 3 đã được báo giá bao nhiêu?
- Giá 1.100.000 có hiệu lực từ ngày nào?
- Một thay đổi giá được nhập ngày 5 tháng 4 nhưng áp dụng hồi tố từ ngày 1 tháng 4 có ý nghĩa gì?
- Nhân viên đã nhìn thấy mức giá nào khi tạo đơn?

Lịch sử giá cần là dữ liệu có thể truy vấn, không chỉ là một bản ghi log khó liên kết với quyết định nghiệp vụ.

### 1.2. Policy thay đổi nhưng quyết định cũ phải giữ được ý nghĩa

Một chính sách hoàn tiền có thể cho phép hoàn trong 30 ngày. Sau đó doanh nghiệp thay đổi thành 14 ngày từ một ngày hiệu lực cụ thể.

Nếu hệ thống chỉ giữ policy mới, việc xem lại yêu cầu hoàn tiền được xử lý trước ngày thay đổi sẽ có nguy cơ áp dụng sai quy tắc. Cần xác định policy version tại thời điểm đánh giá và lưu căn cứ của quyết định.

### 1.3. Hợp đồng có nhiều mốc thời gian khác nhau

Một hợp đồng có thể:

- Được soạn vào ngày 10 tháng 5.
- Được hai bên ký ngày 15 tháng 5.
- Có hiệu lực từ ngày 1 tháng 6.
- Được sửa đổi bằng phụ lục ngày 20 tháng 8.
- Hết hạn ngày 31 tháng 12.

Ngày ký, ngày có hiệu lực, ngày hệ thống nhận tài liệu và ngày chấm dứt là các khái niệm khác nhau. Gộp chúng thành một field `updated_at` sẽ làm mất ý nghĩa nghiệp vụ.

## 2. Hai loại thời gian quan trọng: Valid Time và Transaction Time

### 2.1. Valid Time — thời gian hiệu lực trong nghiệp vụ

Valid Time mô tả khoảng thời gian mà một sự thật được xem là đúng trong thế giới nghiệp vụ.

Ví dụ:

- Giá mới có hiệu lực từ ngày 1 tháng 4.
- Chính sách bảo hành áp dụng cho sản phẩm bán từ ngày 1 tháng 7.
- Hợp đồng có hiệu lực từ ngày 1 tháng 6 đến hết ngày 31 tháng 12.
- Một khách hàng thuộc hạng Gold từ ngày 15 tháng 2.

Valid Time trả lời: **sự thật này có hiệu lực khi nào?**

### 2.2. Transaction Time — thời gian hệ thống ghi nhận

Transaction Time mô tả khoảng thời gian một phiên bản thông tin tồn tại trong hệ thống lưu trữ hoặc được hệ thống xem là thông tin đã biết.

Ví dụ:

- Nhân viên nhập giá mới vào hệ thống ngày 28 tháng 3.
- Một thay đổi chính sách được ghi nhận ngày 5 tháng 4 nhưng có hiệu lực từ ngày 1 tháng 4.
- Một phụ lục hợp đồng ký ngày 20 tháng 8 được tải lên hệ thống ngày 22 tháng 8.

Transaction Time trả lời: **hệ thống biết và lưu phiên bản thông tin này từ khi nào?**

### 2.3. Hai thời gian có thể khác nhau

Giả sử ngày 5 tháng 4, doanh nghiệp phát hiện giá áp dụng từ ngày 1 tháng 4 đã được nhập sai. Hệ thống cần sửa dữ liệu để phản ánh đúng giá có hiệu lực từ ngày 1 tháng 4.

- Valid Time bắt đầu: 1 tháng 4.
- Transaction Time bắt đầu của thông tin sửa: 5 tháng 4.

Từ đó có hai câu hỏi khác nhau:

1. Giá nào có hiệu lực ngày 2 tháng 4 theo thông tin hệ thống đang biết hiện nay?
2. Vào ngày 2 tháng 4, hệ thống đã tin rằng giá nào đang có hiệu lực?

Câu thứ nhất hỏi theo Valid Time của dữ liệu hiện tại. Câu thứ hai cần cả Transaction Time để tái hiện tri thức tại thời điểm lịch sử.

### 2.4. Ví dụ dòng thời gian

~~~mermaid
gantt
    title Ví dụ thay đổi giá có hiệu lực hồi tố
    dateFormat YYYY-MM-DD
    axisFormat %d/%m
    section Valid Time
    Giá A có hiệu lực :a1, 2026-03-01, 31d
    Giá B có hiệu lực :a2, 2026-04-01, 30d
    section Transaction Time
    Hệ thống ghi Giá B lần đầu :b1, 2026-04-05, 10d
    Hệ thống ghi bản sửa Giá B :b2, 2026-04-15, 15d
~~~

Sơ đồ chỉ minh họa hai trục thời gian. Một mô hình bitemporal thực tế cần giữ lại cả phiên bản thông tin cũ và phiên bản sửa, thay vì ghi đè.

## 3. Mô hình khoảng thời gian hiệu lực

### 3.1. Dùng khoảng nửa mở [from, to)

Một quy ước dễ xử lý là dùng khoảng nửa mở:

\[
[from, to)
\]

Nghĩa là thời điểm bắt đầu được tính vào khoảng, còn thời điểm kết thúc không được tính vào khoảng.

Ví dụ:

- Phiên bản A: [2026-03-01, 2026-04-01).
- Phiên bản B: [2026-04-01, 2026-05-01).

Tại đúng 2026-04-01T00:00, chỉ phiên bản B có hiệu lực. Không có khoảng trống hoặc chồng lấn ở ranh giới.

### 3.2. Vì sao không nên dùng hai đầu đều inclusive?

Nếu cả hai đầu đều inclusive, hai phiên bản liền kề có thể cùng đúng tại thời điểm chuyển tiếp. Nếu cả hai đầu đều exclusive, lại có thể xuất hiện khoảng trống.

Khoảng nửa mở giúp phép kiểm tra nhất quán:

~~~text
from <= instant AND instant < to
~~~

Nếu `to` không có giá trị, khoảng có thể được hiểu là chưa xác định ngày kết thúc hoặc kéo dài vô hạn theo quy ước của domain.

### 3.3. Value Object cho khoảng hiệu lực

~~~java
public record EffectivePeriod(
        Instant from,
        Instant toExclusive) {

    public EffectivePeriod {
        Objects.requireNonNull(from, "from is required");

        if (toExclusive != null && !from.isBefore(toExclusive)) {
            throw new IllegalArgumentException(
                "Period end must be after period start"
            );
        }
    }

    public boolean contains(Instant instant) {
        Objects.requireNonNull(instant);

        return !instant.isBefore(from)
            && (toExclusive == null || instant.isBefore(toExclusive));
    }

    public boolean overlaps(EffectivePeriod other) {
        boolean thisEndsBeforeOtherStarts =
            toExclusive != null && !toExclusive.isAfter(other.from);
        boolean otherEndsBeforeThisStarts =
            other.toExclusive != null && !other.toExclusive.isAfter(from);

        return !thisEndsBeforeOtherStarts && !otherEndsBeforeThisStarts;
    }
}
~~~

Value Object bảo vệ invariant của khoảng thời gian. Các phép so sánh phải thống nhất với quy ước nửa mở và kiểu thời gian được chọn.

### 3.4. Chọn kiểu thời gian theo ngữ nghĩa

Không phải mọi mốc thời gian đều nên dùng `Instant`.

| Kiểu | Ý nghĩa | Ví dụ |
|---|---|---|
| `Instant` | Một thời điểm tuyệt đối trên timeline | Event được ghi nhận lúc 08:30 UTC |
| `LocalDate` | Ngày lịch không gắn múi giờ | Chính sách áp dụng từ ngày 1 tháng 6 |
| `LocalDateTime` | Ngày và giờ địa phương chưa gắn timezone | Lịch hẹn 09:00 theo giờ địa phương, chưa biết vùng |
| `ZonedDateTime` | Ngày giờ cùng múi giờ cụ thể | Hạn đóng cửa theo `Asia/Ho_Chi_Minh` |
| `OffsetDateTime` | Ngày giờ cùng UTC offset | Timestamp có offset trong API |

Giá có hiệu lực theo ngày kinh doanh thường phù hợp với `LocalDate`. Một event xảy ra tại một thời điểm tuyệt đối thường phù hợp với `Instant`. Một lịch chạy lúc 09:00 theo múi giờ của chi nhánh cần lưu cả giờ địa phương và ZoneId.

Không nên dùng `LocalDateTime` để đại diện một thời điểm toàn cầu nếu không có timezone hoặc offset.

## 4. Version bất biến và vòng đời phiên bản

### 4.1. Tạo phiên bản mới thay vì sửa nội dung đã có hiệu lực

Khi policy hoặc price version đã được công bố và có thể đã được dùng để ra quyết định, nên xem nội dung phiên bản đó là bất biến.

Thay đổi chính sách tạo một version mới:

- Policy `REFUND`, revision 4: tối đa 30 ngày.
- Policy `REFUND`, revision 5: tối đa 14 ngày.

Version 4 vẫn tồn tại để giải thích quyết định cũ. Version 5 có khoảng hiệu lực riêng.

### 4.2. Tách nội dung phiên bản khỏi trạng thái phát hành

Một phiên bản có thể trải qua các trạng thái:

- Draft: đang soạn và chưa được áp dụng.
- Approved: đã được phê duyệt.
- Scheduled: đã lên lịch có hiệu lực trong tương lai.
- Published/Active: đã được công bố hoặc đang được áp dụng.
- Retired: không còn được dùng cho quyết định mới.

Trạng thái vòng đời và khoảng hiệu lực là hai khía cạnh khác nhau. Một version có thể đã được phê duyệt nhưng chưa đến ngày hiệu lực. Một version cũ có thể đã hết hiệu lực nhưng vẫn phải được giữ để tra cứu lịch sử.

Không nên chỉ dựa vào field `status = ACTIVE` để xác định phiên bản áp dụng. Cần kiểm tra cả scope và khoảng Valid Time.

### 4.3. Mô hình version

~~~java
public record PolicyVersion(
        PolicyVersionId id,
        PolicyId policyId,
        int revision,
        EffectivePeriod effectivePeriod,
        PolicyRules rules,
        Instant publishedAt,
        String contentHash) {

    public PolicyVersion {
        Objects.requireNonNull(id);
        Objects.requireNonNull(policyId);
        Objects.requireNonNull(effectivePeriod);
        Objects.requireNonNull(rules);

        if (revision < 1) {
            throw new IllegalArgumentException(
                "Revision must be positive"
            );
        }
    }
}
~~~

`contentHash` có thể giúp xác minh nội dung tài liệu hoặc rule set đã công bố. Hash không thay thế chữ ký, audit hay cơ chế lưu trữ bất biến.

## 5. Chính sách có phiên bản theo thời gian

### 5.1. Policy cần định danh và scope rõ ràng

Một policy không chỉ có mã và revision. Nó thường áp dụng trong một phạm vi cụ thể:

- Loại sản phẩm.
- Quốc gia hoặc khu vực.
- Kênh bán hàng.
- Nhóm khách hàng.
- Loại giao dịch.
- Đơn vị kinh doanh.

Hai policy cùng tên có thể hợp lệ nếu áp dụng cho scope khác nhau. Vì vậy, truy vấn policy phải xác định đủ scope trước khi tìm version hiệu lực.

### 5.2. Truy vấn policy tại một thời điểm

Ví dụ truy vấn:

~~~sql
SELECT *
FROM policy_version
WHERE policy_code = :policy_code
  AND region_code = :region
  AND effective_from <= :valid_at
  AND (effective_to IS NULL OR :valid_at < effective_to)
  AND publication_state = 'PUBLISHED';
~~~

Truy vấn phải trả về đúng một version cho scope và thời điểm đã chọn. Nếu không có version hoặc có nhiều version cùng khớp, đó là lỗi dữ liệu/quy tắc cần được phát hiện; không nên chọn tùy tiện bằng `LIMIT 1`.

### 5.3. Quyết định nghiệp vụ cần ghi lại version đã dùng

Giả sử hệ thống đánh giá một yêu cầu hoàn tiền ngày 12 tháng 4 bằng policy revision 4. Một tháng sau revision 5 được công bố.

Hồ sơ quyết định nên giữ:

- Policy ID và revision.
- Thời điểm đánh giá.
- Ngày nghiệp vụ dùng để xác định hiệu lực.
- Kết quả và reason code.
- Các dữ kiện đầu vào cần thiết để giải thích.
- Người hoặc quy trình khởi tạo quyết định.

~~~java
public record PolicyDecision(
        UUID decisionId,
        PolicyVersionId policyVersionId,
        Instant evaluatedAt,
        LocalDate businessDate,
        DecisionOutcome outcome,
        List<ReasonCode> reasons,
        String inputReference) {
}
~~~

Không nên chỉ lưu `policyCode = REFUND` rồi lúc tra cứu mới lấy version hiện tại. Điều đó khiến lịch sử phụ thuộc vào trạng thái cấu hình hôm nay.

### 5.4. Lưu snapshot đầu vào khi cần tái hiện quyết định

Chỉ lưu version policy có thể chưa đủ nếu quyết định phụ thuộc vào dữ liệu khách hàng, trạng thái đơn, thời hạn giao hàng hoặc các nguồn ngoài.

Tùy mức độ kiểm toán, có thể lưu:

- Snapshot các giá trị đầu vào liên quan.
- ID/version của dữ liệu nguồn.
- Hash của payload đầu vào.
- Reference tới hồ sơ immutable được lưu ở nơi phù hợp.
- Phiên bản thuật toán hoặc rule engine.

Chỉ lưu dữ liệu cần thiết và áp dụng chính sách bảo vệ dữ liệu. Không cần sao chép toàn bộ hồ sơ khách hàng nếu chỉ vài thuộc tính quyết định kết quả.

## 6. Giá có hiệu lực theo thời gian

### 6.1. Giá là dữ liệu nghiệp vụ có scope

Giá có thể phụ thuộc vào:

- Product hoặc SKU.
- Price list.
- Currency.
- Khu vực.
- Kênh bán.
- Nhóm khách hàng.
- Số lượng hoặc bậc giá.
- Thời gian bắt đầu/kết thúc.

Một giá trị `product.price` duy nhất thường không đủ để diễn tả các chiều này.

### 6.2. Price Version

~~~java
public record PriceVersion(
        PriceVersionId id,
        ProductId productId,
        PriceListId priceListId,
        Money amount,
        EffectivePeriod effectivePeriod,
        int revision) {
}
~~~

`Money` cần mang currency và áp dụng quy tắc làm tròn rõ ràng. Không nên dùng `double` để biểu diễn tiền. Giá tiền cần được so sánh và tính toán bằng kiểu decimal có độ chính xác phù hợp.

### 6.3. Truy vấn giá theo thời điểm nghiệp vụ

~~~sql
SELECT id, amount, currency, revision
FROM product_price_version
WHERE product_id = :product_id
  AND price_list_id = :price_list_id
  AND currency = :currency
  AND effective_from <= :price_at
  AND (effective_to IS NULL OR :price_at < effective_to)
ORDER BY revision DESC;
~~~

Ví dụ có `ORDER BY` để hỗ trợ kiểm tra hoặc hiển thị, nhưng trong một scope được thiết kế đúng, truy vấn phải có tối đa một version hợp lệ. Không dùng revision cao nhất để che việc hai khoảng hiệu lực bị chồng lấn.

### 6.4. Chụp giá tại thời điểm tạo đơn hoặc báo giá

Khi tạo đơn, nên lưu giá đã chốt trên dòng đơn:

- PriceVersionId đã được áp dụng.
- Unit price và currency.
- Quantity.
- Discount/tax snapshot nếu thuộc hợp đồng giá tại thời điểm mua.
- Thời điểm báo giá hoặc xác nhận.

Đơn hàng là hồ sơ giao dịch. Khi giá niêm yết thay đổi, đơn cũ không nên tự đổi tổng tiền theo bảng giá hiện tại.

~~~java
public record OrderLinePricing(
        PriceVersionId sourcePriceVersion,
        Money unitPrice,
        BigDecimal quantity,
        Money discount,
        Instant pricedAt) {
}
~~~

Nếu báo giá có thời hạn, lưu thêm `expiresAt`. Khi người dùng xác nhận sau thời hạn, hệ thống có thể yêu cầu định giá lại theo chính sách. Việc đó phải là một hành vi nghiệp vụ rõ ràng.

### 6.5. Giá hồi tố và điều chỉnh giao dịch

Giá được nhập ngày 5 tháng 4 nhưng có hiệu lực từ ngày 1 tháng 4 không đồng nghĩa mọi đơn hàng từ ngày 1 tháng 4 tự động thay đổi.

Cần có quy tắc nghiệp vụ xác định:

- Đơn đã xác nhận có được giữ nguyên giá đã chốt không?
- Báo giá chưa xác nhận có phải tính lại không?
- Có cần lập hóa đơn điều chỉnh hoặc khoản hoàn/thu thêm không?
- Ai có quyền phê duyệt thay đổi hồi tố?
- Có cần lưu căn cứ và người thực hiện?

Lịch sử giá và điều chỉnh giao dịch là hai khái niệm khác nhau. Không nên âm thầm cập nhật dữ liệu giao dịch đã phát sinh để làm cho nó khớp với bảng giá mới.

## 7. Hợp đồng và điều khoản có phiên bản

### 7.1. Hợp đồng không chỉ là một file PDF

Trong domain model, hợp đồng có thể bao gồm:

- Contract ID và các bên tham gia.
- Loại hợp đồng và phạm vi đối tượng.
- Revision hoặc amendment.
- Nội dung điều khoản đã chấp thuận.
- Ngày tạo, ngày ký và ngày hiệu lực.
- Ngày hết hạn hoặc ngày chấm dứt.
- Chữ ký, bằng chứng chấp thuận và trạng thái phê duyệt.

File PDF đã ký là một bằng chứng quan trọng, nhưng domain cần lưu identity, version, thời gian và quan hệ giữa hợp đồng gốc với phụ lục.

### 7.2. Revision và Amendment

Khi hai bên sửa đổi hợp đồng, nên tạo amendment hoặc revision mới liên kết với hợp đồng trước đó.

Ví dụ:

| Revision | Ngày ký | Ngày hiệu lực | Nội dung |
|---|---|---|---|
| 1 | 15/05 | 01/06 | Hợp đồng gốc |
| 2 | 20/08 | 01/09 | Thay đổi mức phí |
| 3 | 10/11 | 01/12 | Gia hạn thời hạn |

Revision 1 vẫn cần được giữ lại để xác định điều khoản áp dụng trước ngày 1 tháng 9. Không ghi đè file và điều khoản cũ bằng nội dung revision 2.

### 7.3. Ngày ký khác ngày hiệu lực

Ngày ký thường phản ánh thời điểm các bên chấp thuận hoặc hoàn tất chữ ký. Ngày hiệu lực phản ánh thời điểm các nghĩa vụ bắt đầu áp dụng.

Một hợp đồng ký ngày 15 tháng 5 nhưng có hiệu lực từ ngày 1 tháng 6 cần hai field riêng. Nếu hợp đồng được ký sau ngày dự kiến hiệu lực, hệ thống phải áp dụng quy tắc pháp lý/nghiệp vụ tương ứng thay vì tự suy ra.

### 7.4. Lưu bằng chứng chấp thuận

Tùy yêu cầu, có thể lưu:

- Người ký và vai trò.
- Thời điểm ký hoặc chấp thuận.
- Phương thức ký.
- Hash tài liệu đã ký.
- Reference tới file bất biến.
- Chứng thư hoặc dữ liệu xác minh chữ ký theo hệ thống sử dụng.
- Phiên bản điều khoản đã được chấp thuận.

Không nên chỉ lưu URL tới một file có thể bị thay thế. Cần bảo đảm khả năng xác định chính xác nội dung mà các bên đã ký.

### 7.5. Chấm dứt hợp đồng

Hợp đồng có thể chấm dứt trước ngày hết hạn. Nên phân biệt:

- Expiration: hết hiệu lực theo thời hạn.
- Termination: chấm dứt theo một hành vi hoặc điều kiện.
- Suspension: tạm đình chỉ trong một khoảng thời gian.
- Amendment: thay đổi điều khoản theo một revision mới.

Các mốc này có ý nghĩa khác nhau và có thể kéo theo nghĩa vụ còn tồn tại sau chấm dứt, ví dụ thanh toán hoặc bảo mật.

## 8. Bitemporal: lưu cả hiệu lực nghiệp vụ và lịch sử hệ thống

### 8.1. Khi nào cần bitemporal?

Một bảng chỉ có Valid Time đủ cho nhiều hệ thống: cần biết giá hoặc policy có hiệu lực ở ngày nào.

Bitemporal cần thiết khi doanh nghiệp còn phải trả lời:

- Hệ thống đã biết thông tin nào vào một ngày lịch sử?
- Ai đã thay đổi dữ liệu và từ thời điểm nào?
- Một điều chỉnh hồi tố đã làm thay đổi cách nhìn hiện tại về quá khứ ra sao?
- Quyết định trước đó được đưa ra dựa trên dữ liệu nào có sẵn lúc ấy?

### 8.2. Hai cặp khoảng thời gian

Một bản ghi bitemporal có hai khoảng:

- Valid period: khoảng thời gian sự thật có hiệu lực trong nghiệp vụ.
- System period: khoảng thời gian hệ thống xem phiên bản thông tin đó là phiên bản đang được ghi nhận.

Ví dụ một mức giá:

| Phiên bản | Valid From | Valid To | System From | System To | Giá |
|---|---|---|---|---|---:|
| A | 01/04 | Không giới hạn | 01/04 | 05/04 | 1.100.000 |
| B | 01/04 | Không giới hạn | 05/04 | Hiện tại | 1.050.000 |

Ngày 5 tháng 4, hệ thống sửa giá hồi tố cho cùng khoảng hiệu lực:

- Hỏi “giá có hiệu lực ngày 2 tháng 4 theo dữ liệu hiện nay?” → 1.050.000.
- Hỏi “ngày 2 tháng 4 hệ thống đã ghi nhận giá nào?” → 1.100.000.

### 8.3. Ví dụ schema bitemporal

~~~sql
CREATE TABLE product_price_history (
    price_version_id UUID NOT NULL,
    product_id VARCHAR(100) NOT NULL,
    price_list_id VARCHAR(100) NOT NULL,
    currency CHAR(3) NOT NULL,
    amount NUMERIC(19, 4) NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE,
    system_from TIMESTAMPTZ NOT NULL,
    system_to TIMESTAMPTZ,
    recorded_by VARCHAR(120) NOT NULL,
    change_reason VARCHAR(500),
    PRIMARY KEY (price_version_id, system_from),
    CHECK (valid_to IS NULL OR valid_from < valid_to),
    CHECK (system_to IS NULL OR system_from < system_to)
);
~~~

Ví dụ này mô tả cấu trúc khái niệm. Một triển khai production cần thêm constraint/index phù hợp để bảo vệ tính duy nhất và chống chồng lấn theo cả hai trục thời gian.

### 8.4. Truy vấn “đúng vào lúc đó” và “hệ thống biết lúc đó”

Giá có hiệu lực theo thông tin hiện tại:

~~~sql
SELECT *
FROM product_price_history
WHERE product_id = :product_id
  AND valid_from <= :business_date
  AND (valid_to IS NULL OR :business_date < valid_to)
  AND system_to IS NULL;
~~~

Giá mà hệ thống đã ghi nhận tại một thời điểm trong quá khứ:

~~~sql
SELECT *
FROM product_price_history
WHERE product_id = :product_id
  AND valid_from <= :business_date
  AND (valid_to IS NULL OR :business_date < valid_to)
  AND system_from <= :known_at
  AND (system_to IS NULL OR :known_at < system_to);
~~~

Truy vấn thứ hai chọn phiên bản mà cả Valid Time và System Time đều chứa thời điểm cần hỏi.

### 8.5. Sửa dữ liệu bitemporal mà không xóa lịch sử

Khi phát hiện dữ liệu sai:

1. Đóng System Time của bản ghi đang được xem là hiện hành.
2. Giữ nguyên bản ghi cũ để biết hệ thống từng ghi nhận điều gì.
3. Tạo bản ghi mới với Valid Time chính xác.
4. Đặt System Time bắt đầu bằng thời điểm sửa.
5. Ghi người sửa và lý do thay đổi.

Không cập nhật đè cả hai trục thời gian. Nếu sửa bằng cách xóa bản ghi cũ, hệ thống sẽ mất khả năng tái hiện tri thức lịch sử.

## 9. Ngăn khoảng hiệu lực chồng lấn hoặc bị hở

### 9.1. Xác định invariant theo scope

Với cùng một policy code, region và loại khách hàng, có thể yêu cầu tối đa một policy version được công bố cho mỗi thời điểm.

Với giá, scope có thể là:

`product + price list + currency + region + channel + customer segment`.

Không thể chỉ kiểm tra overlap theo Product ID nếu giá được phép khác nhau giữa các price list hoặc kênh bán.

### 9.2. Overlap và gap là hai vấn đề khác nhau

- Overlap: hai version cùng hiệu lực trong một thời điểm và cùng scope.
- Gap: không có version hiệu lực trong một khoảng thời gian.

Overlap thường gây ra kết quả chọn version mơ hồ. Gap có thể hợp lệ nếu sản phẩm tạm ngừng bán hoặc policy chưa áp dụng; cũng có thể là lỗi nếu nghiệp vụ yêu cầu luôn có một chính sách.

Không nên tự động loại bỏ mọi gap. Hãy xác định invariant theo domain.

### 9.3. Kiểm tra overlap bằng SQL

Với khoảng ngày nửa mở trong PostgreSQL, có thể dùng range và exclusion constraint. Ví dụ khái niệm:

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE product_price_version
ADD CONSTRAINT no_overlapping_price_periods
EXCLUDE USING gist (
    product_id WITH =,
    price_list_id WITH =,
    currency WITH =,
    daterange(effective_from, effective_to, '[)') WITH &&
)
WHERE (publication_state = 'PUBLISHED');
~~~

Exclusion constraint ngăn các khoảng của cùng scope chồng lấn. Cần kiểm tra kiểu dữ liệu, hỗ trợ extension và cách quản lý version tương lai theo schema thực tế.

Nếu chỉ kiểm tra overlap bằng một câu SELECT trước khi INSERT, hai transaction đồng thời có thể cùng thấy không có xung đột rồi cùng ghi các khoảng chồng lấn. Constraint ở database hoặc cơ chế khóa/serialize phù hợp mới bảo vệ được invariant dưới concurrency.

### 9.4. Version mới nối tiếp version cũ

Khi publish version mới từ thời điểm T:

- Đóng khoảng hiệu lực của version cũ tại T.
- Tạo version mới bắt đầu tại T.
- Hai thao tác phải được kiểm soát trong cùng transaction.
- Constraint bảo vệ không overlap.
- Nếu có yêu cầu không gap, cần kiểm tra tính liên tục theo scope.

Không nên sửa version cũ nếu nội dung đã được dùng để đưa ra quyết định và cần giữ nguyên lịch sử nội dung. Có thể cập nhật phần quản lý khoảng hiệu lực theo một quy trình được audit, hoặc ghi thêm temporal revision tùy mô hình.

## 10. Thay đổi hồi tố và thay đổi có hiệu lực trong tương lai

### 10.1. Prospective change

Prospective change là thay đổi được công bố hôm nay nhưng có hiệu lực từ một thời điểm trong tương lai.

Ví dụ ngày 15 tháng 5 công bố policy revision 6, có hiệu lực từ ngày 1 tháng 6.

Hệ thống cần:

- Lưu version mới ở trạng thái đã phê duyệt/lên lịch.
- Giữ version cũ có hiệu lực đến đúng thời điểm chuyển tiếp.
- Ngăn version mới được dùng trước thời điểm hiệu lực.
- Kiểm tra các báo giá, giao dịch hoặc quy trình đã tạo trước ngày chuyển tiếp.

### 10.2. Retroactive change

Retroactive change là thay đổi được ghi nhận hôm nay nhưng có hiệu lực từ một thời điểm trong quá khứ.

Ví dụ ngày 10 tháng 6 phát hiện chính sách cần áp dụng từ ngày 1 tháng 6.

Cần xác định rõ:

- Có được phép hồi tố theo quy định nghiệp vụ/pháp lý không?
- Những quyết định đã hoàn tất có được xem xét lại không?
- Giao dịch nào cần điều chỉnh?
- Dữ liệu lịch sử nào phải giữ nguyên?
- Ai phê duyệt và lý do gì?

Không nên mặc định cập nhật hồi tố sẽ tự động chạy lại mọi workflow. Một quyết định đã thực hiện có thể cần quy trình điều chỉnh riêng thay vì thay đổi lại bản ghi cũ.

### 10.3. Correction khác với business change

Correction sửa một dữ liệu trước đó bị ghi sai. Business change là một quyết định thay đổi chính sách hoặc điều khoản từ một thời điểm xác định.

Hai loại thay đổi nên có reason code và audit khác nhau:

- Correction: sửa lỗi nhập liệu, lỗi mapping, sai nguồn dữ liệu.
- Business change: phê duyệt giá mới, sửa điều khoản, thay đổi quy tắc.

Điều này giúp người đọc lịch sử hiểu vì sao dữ liệu được sửa.

## 11. Chọn thời điểm đánh giá trong use case

### 11.1. Không dùng thời gian hiện tại một cách ngầm định

Một phương thức như `findCurrentPrice(productId)` có thể không rõ “current” là:

- Thời điểm hiện tại của server.
- Ngày kinh doanh tại chi nhánh.
- Thời điểm tạo đơn.
- Thời điểm giao hàng.
- Thời điểm xuất hóa đơn.

Hãy truyền thời điểm nghiệp vụ rõ ràng:

~~~java
PriceVersion price = prices.findApplicable(
    productId,
    priceListId,
    businessContext,
    pricingAt
);
~~~

Tên biến `pricingAt` thể hiện thời điểm định giá. Không để repository tự gọi `Instant.now()` vì caller sẽ khó kiểm soát và test.

### 11.2. Event Time và Processing Time

Trong hệ thống bất đồng bộ:

- Event Time là thời điểm sự kiện nghiệp vụ thực sự xảy ra hoặc được tạo.
- Processing Time là thời điểm consumer xử lý message.
- Ingestion/Recorded Time là thời điểm hệ thống tiếp nhận hoặc ghi message.

Một event được phát lúc 10:00 nhưng consumer xử lý lúc 10:05. Nếu policy thay đổi lúc 10:03, consumer phải biết nghiệp vụ yêu cầu dùng policy tại 10:00 hay policy hiện hành lúc 10:05.

Không có câu trả lời chung. Với một quyết định giá đã chốt, thường phải dùng snapshot/version được producer ghi trong event. Với một quyết định mới được consumer thực hiện khi nhận event, cần xác định business effective time theo quy tắc use case.

### 11.3. Lưu mốc đánh giá và mốc hiệu lực riêng

Một decision record có thể cần:

- `evaluatedAt`: lúc hệ thống thực hiện đánh giá.
- `validAt`: thời điểm nghiệp vụ dùng để chọn version.
- `recordedAt`: lúc decision được ghi vào hệ thống.

Ba giá trị có thể khác nhau, nhất là với batch processing hoặc xử lý sự kiện đến trễ.

## 12. Múi giờ, ngày kinh doanh và thời điểm tuyệt đối

### 12.1. Lưu timestamp theo UTC, giữ timezone khi ngữ nghĩa cần

Một thời điểm tuyệt đối nên được lưu bằng Instant/UTC. Nếu quy tắc phụ thuộc múi giờ địa phương, cần lưu ZoneId hoặc cấu hình timezone của đơn vị nghiệp vụ.

Ví dụ:

- Hợp đồng hết hiệu lực lúc 00:00 ngày 1 tháng 7 theo giờ Việt Nam.
- Cửa hàng đóng bán lúc 22:00 theo múi giờ của chi nhánh.
- Một chính sách áp dụng từ ngày lịch tại từng quốc gia.

Chỉ lưu `2026-07-01T00:00:00` mà không có timezone sẽ không xác định được một thời điểm toàn cầu.

### 12.2. LocalDate phù hợp cho ngày hiệu lực theo lịch

Nếu hợp đồng ghi “có hiệu lực từ ngày 1 tháng 6”, có thể đó là một ngày lịch, không phải một instant chính xác. Dùng LocalDate giúp giữ đúng ngữ nghĩa.

Khi cần chuyển ngày lịch thành thời điểm bắt đầu, hãy dùng ZoneId của nơi áp dụng:

~~~java
LocalDate effectiveDate = LocalDate.of(2026, 6, 1);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant effectiveAt = effectiveDate
    .atStartOfDay(zone)
    .toInstant();
~~~

`atStartOfDay` xử lý quy tắc timezone của ngày đó. Không tự cộng cố định 24 giờ để tính ngày kế tiếp trong vùng có DST.

### 12.3. Daylight Saving Time

Ở các vùng có DST, một giờ địa phương có thể bị lặp hoặc không tồn tại khi đồng hồ chuyển đổi. Lịch chạy lúc 01:30 có thể mơ hồ vào ngày chuyển DST.

Với lịch nghiệp vụ theo giờ địa phương:

- Lưu ZoneId, không chỉ UTC offset.
- Xác định cách xử lý giờ không tồn tại hoặc bị lặp.
- Chọn quy tắc rõ ràng: chạy sớm hơn, muộn hơn hay yêu cầu cấu hình lại.
- Kiểm thử các ngày chuyển DST.

Việt Nam hiện không áp dụng DST, nhưng phần mềm có thể phục vụ chi nhánh hoặc hợp đồng ở các quốc gia khác.

### 12.4. Clock trong domain/application

Tránh gọi trực tiếp `Instant.now()` ở nhiều nơi. Tiêm `Clock` để use case kiểm soát thời gian và test có thể cố định mốc:

~~~java
Clock clock = Clock.fixed(
    Instant.parse("2026-04-01T00:00:00Z"),
    ZoneOffset.UTC
);
~~~

Trong hệ thống phân tán, timestamp từ node khác có thể lệch. Nếu thứ tự tuyệt đối quan trọng, dùng sequence, database ordering hoặc cơ chế đồng bộ phù hợp; không dựa duy nhất vào đồng hồ hệ thống.

## 13. Các chiến lược lưu lịch sử

Không phải mọi module đều cần bitemporal. Chọn cách lưu theo câu hỏi nghiệp vụ cần trả lời.

### 13.1. Current state only

Chỉ lưu trạng thái hiện tại.

Phù hợp khi:

- Lịch sử không có giá trị nghiệp vụ.
- Không cần giải thích quyết định cũ.
- Dữ liệu có thể được tái tạo từ nguồn khác.

Không phù hợp với giá, policy hoặc hợp đồng cần kiểm toán và truy vấn lịch sử.

### 13.2. Versioned rows / SCD Type 2

Mỗi thay đổi tạo một row version mới, có `valid_from`, `valid_to`, revision hoặc cờ current.

Ưu điểm:

- Truy vấn lịch sử đơn giản.
- Dễ tham chiếu version cụ thể từ giao dịch.
- Có thể giữ nội dung cũ bất biến.

Giới hạn:

- Cần quản lý khoảng hiệu lực.
- Có thể cần constraint để chống overlap.
- Không tự trả lời hệ thống đã biết gì tại một thời điểm nếu không lưu Transaction Time.

### 13.3. Audit log

Audit log ghi ai đã thay đổi gì, lúc nào và vì sao. Nó hữu ích cho kiểm soát thay đổi, nhưng không tự động là mô hình dữ liệu để truy vấn giá/policy có hiệu lực.

Audit nên có actor, timestamp, action, target, reason và correlation/reference phù hợp. Cần phân biệt audit event với phiên bản dữ liệu được dùng trong domain query.

### 13.4. Bitemporal table

Bitemporal lưu Valid Time và System/Transaction Time.

Phù hợp khi cần:

- Truy vấn hiệu lực nghiệp vụ tại một thời điểm.
- Tái hiện tri thức hệ thống tại một thời điểm.
- Sửa hồi tố mà vẫn giữ lịch sử nhận thức.
- Điều tra và kiểm toán các quyết định quan trọng.

Đánh đổi là schema và truy vấn phức tạp hơn, cần quy tắc cập nhật hai trục thời gian.

### 13.5. Temporal table do database quản lý

Một số database hỗ trợ system-versioned temporal table để tự động giữ lịch sử row theo transaction/system time. Tính năng này có thể giúp audit trạng thái lưu trữ, nhưng chưa chắc đại diện Valid Time nghiệp vụ.

Hãy phân biệt:

- System-versioned history: database ghi lại row thay đổi khi nào.
- Business valid time: quy tắc nói dữ liệu có hiệu lực từ ngày nào.

Một hệ thống có thể kết hợp cả hai nếu cần.

### 13.6. Event Sourcing

Event Sourcing lưu chuỗi sự kiện làm nguồn sự thật và dựng trạng thái bằng cách replay. Nó khác với việc chỉ lưu lịch sử phiên bản hoặc audit log.

Event Sourcing phù hợp khi lịch sử hành vi là trung tâm của domain và có nhu cầu tái dựng trạng thái. Đổi lại, cần quản lý event schema, replay, snapshot, projection và thay đổi model.

Không nên chọn Event Sourcing chỉ vì cần lưu giá hoặc policy cũ. Versioned rows hoặc bitemporal table thường đơn giản hơn nếu câu hỏi chính là “version nào có hiệu lực tại thời điểm T?”.

## 14. Ranh giới aggregate và sở hữu lịch sử

### 14.1. Version là một phần của mô hình nghiệp vụ

Policy có thể là một aggregate quản lý các revision và lịch phát hành. Price List có thể là aggregate quản lý giá theo sản phẩm và scope. Contract có thể là aggregate root quản lý vòng đời, revision và bằng chứng chấp thuận.

Không nhất thiết gom mọi version của mọi sản phẩm vào một aggregate lớn. Cần xác định invariant và tần suất thay đổi để chọn ranh giới phù hợp.

### 14.2. Ai được phép công bố version?

Việc tạo Draft có thể được phép rộng hơn việc Publish. Publish có thể cần:

- Quyền phê duyệt.
- Kiểm tra không overlap.
- Kiểm tra đủ dữ liệu bắt buộc.
- Xác định thời điểm hiệu lực.
- Ghi người thực hiện và lý do.
- Tạo integration event thông báo version mới.

Đây là hành vi nghiệp vụ, không chỉ là thao tác CRUD đổi `status`.

### 14.3. Thay đổi lịch hiệu lực cần bảo vệ concurrency

Hai người có thể cùng tạo một version cho cùng scope và khoảng thời gian. Cả hai cùng kiểm tra “chưa có overlap” rồi cùng publish, tạo dữ liệu mâu thuẫn.

Có thể dùng:

- Exclusion/unique constraint tại database.
- Optimistic locking trên aggregate quản lý lịch phát hành.
- Khóa scope trong lúc publish.
- Transaction isolation phù hợp.

Validation trong application giúp đưa ra thông báo sớm; constraint hoặc cơ chế đồng bộ ở tầng lưu trữ mới bảo vệ invariant khi có request đồng thời.

## 15. Cache và dữ liệu có hiệu lực tương lai

### 15.1. Cache key phải phản ánh scope và version

Cache giá chỉ theo Product ID có thể trả sai giá nếu cùng sản phẩm có nhiều price list, currency hoặc channel.

Cache key nên chứa các chiều scope cần thiết. Có thể cache theo version ID hoặc theo key + khoảng hiệu lực.

### 15.2. Version tương lai làm cache phức tạp

Nếu giá mới có hiệu lực lúc 00:00 ngày mai, cache hiện tại có thể vẫn hợp lệ đến đúng thời điểm đó. Hãy:

- Đặt TTL không vượt quá thời điểm chuyển version.
- Phát invalidation khi version được publish hoặc lịch hiệu lực thay đổi.
- Cache kết quả có `validUntil` để consumer biết khi nào cần truy vấn lại.
- Kiểm thử thời điểm chuyển ngày theo timezone nghiệp vụ.

### 15.3. Không cache “current” vô thời hạn

Một giá trị được cache không có thời hạn hoặc invalidation rõ ràng có thể khiến node này áp dụng version mới trong khi node khác vẫn dùng version cũ.

Với quyết định tài chính hoặc hợp đồng, cần xác định nguồn dữ liệu có thẩm quyền và mức nhất quán cần thiết. Có thể yêu cầu đọc trực tiếp version đã chốt hoặc dùng một version reference được lưu trong giao dịch.

## 16. API và truy vấn lịch sử

### 16.1. API nên nói rõ trục thời gian

Một API truy vấn lịch sử nên dùng tên tham số có ý nghĩa:

- `validAt`: hỏi version có hiệu lực tại thời điểm nghiệp vụ.
- `knownAt`: hỏi hệ thống đã ghi nhận version nào tại thời điểm lịch sử.
- `revision`: lấy một version cụ thể.

Tránh một tham số mơ hồ như `date` nếu API hỗ trợ nhiều cách hiểu.

### 16.2. Không dùng `current=true` thay cho ngữ nghĩa thời gian

Current có thể có nghĩa:

- Version mới nhất được tạo.
- Version được publish mới nhất.
- Version đang có hiệu lực tại thời điểm hiện tại.
- Version được hệ thống ghi nhận hiện tại.

Đây là các khái niệm khác nhau. Tên API và query nên phản ánh đúng điều consumer cần.

### 16.3. Phân trang lịch sử ổn định

Khi lịch sử có nhiều revision, phân trang nên có thứ tự xác định, ví dụ `valid_from`, `system_from`, `revision` hoặc ID. Tránh chỉ sort theo timestamp có thể trùng.

Nếu người dùng đang duyệt lịch sử và dữ liệu tiếp tục thay đổi, có thể cần snapshot cursor hoặc `knownAt` cố định để các trang không thay đổi nội dung giữa chừng.

## 17. Kiểm thử mô hình thời gian

Thời gian là nguồn gây lỗi biên phổ biến. Test cần tập trung vào khoảng hiệu lực, timezone và thay đổi hồi tố.

### 17.1. Kiểm thử ranh giới khoảng

Với period [2026-04-01, 2026-05-01):

- Một instant trước 1 tháng 4: không hợp lệ.
- Đúng 00:00 ngày 1 tháng 4 theo timezone đã chọn: hợp lệ.
- Ngay trước 00:00 ngày 1 tháng 5: hợp lệ.
- Đúng 00:00 ngày 1 tháng 5: không hợp lệ.

### 17.2. Kiểm thử version selection

Tạo hai version liền kề và kiểm tra:

- Trước điểm chuyển tiếp trả version cũ.
- Tại điểm chuyển tiếp trả version mới.
- Sau điểm chuyển tiếp vẫn trả version mới.
- Không có hai version cùng khớp.
- Gap được xử lý đúng theo policy.

### 17.3. Kiểm thử bitemporal

Tạo một giá được ghi nhận ban đầu rồi sửa hồi tố:

- Query validAt theo dữ liệu hiện tại trả giá đã sửa.
- Query validAt + knownAt trước ngày sửa trả giá cũ.
- Query knownAt sau ngày sửa trả giá mới.
- Bản ghi cũ vẫn tồn tại với system_to đã đóng.

### 17.4. Kiểm thử thời gian không phụ thuộc sleep

Dùng `Clock.fixed` hoặc clock giả để kiểm soát thời gian:

~~~java
Clock clock = Clock.fixed(
    Instant.parse("2026-04-01T00:00:00Z"),
    ZoneOffset.UTC
);
~~~

Không dùng `Thread.sleep` để chờ ngày hoặc giây trôi qua trong unit test. Test nên điều khiển mốc thời gian trực tiếp.

### 17.5. Các tình huống đặc biệt

- Ngày cuối tháng và năm nhuận.
- Khoảng thời gian chỉ dài một ngày.
- Mốc hiệu lực trong tương lai.
- Thay đổi hồi tố.
- Hai người publish cùng lúc.
- Timestamp đến trễ từ message broker.
- DST và giờ địa phương mơ hồ ở vùng có DST.
- Chênh lệch đồng hồ giữa producer và consumer.

## 18. Những lỗi thiết kế thường gặp

**Ghi đè version cũ.** Hệ thống không thể giải thích giao dịch hoặc quyết định trước đây. Hãy giữ revision đã công bố và tạo version mới.

**Dùng `updated_at` làm lịch sử nghiệp vụ.** Timestamp cập nhật không cho biết thời gian hiệu lực. Tách Valid Time và thời điểm ghi nhận.

**Nhầm ngày ký với ngày hiệu lực.** Hợp đồng có thể được ký trước hoặc sau ngày bắt đầu nghĩa vụ. Lưu các mốc riêng.

**Dùng thời gian hiện tại ngầm định.** Repository tự gọi `now()` khiến kết quả khó test và không rõ business time. Truyền `validAt` hoặc business date rõ ràng.

**Dùng `LocalDateTime` như thời điểm tuyệt đối.** Không có timezone thì không xác định được instant. Chọn kiểu thời gian theo ngữ nghĩa.

**Dùng hai đầu khoảng đều inclusive.** Hai version liền kề có thể cùng hiệu lực tại điểm chuyển tiếp. Thống nhất khoảng nửa mở [from, to).

**Chọn version bằng revision lớn nhất khi có overlap.** Điều này che lỗi dữ liệu. Phát hiện và xử lý overlap theo invariant.

**Chỉ kiểm tra overlap ở application.** Hai transaction đồng thời vẫn có thể tạo khoảng chồng lấn. Dùng constraint hoặc khóa phù hợp.

**Tự động áp dụng giá mới lên đơn cũ.** Giao dịch đã chốt cần giữ snapshot giá và điều khoản đã áp dụng.

**Sửa hồi tố mà không có audit.** Không biết ai thay đổi, vì sao và quyết định cũ bị ảnh hưởng thế nào. Ghi actor, reason và Transaction Time.

**Dùng bitemporal cho mọi bảng.** Mô hình trở nên phức tạp mà không trả lời thêm câu hỏi có giá trị. Chỉ dùng khi cần cả lịch sử hiệu lực và lịch sử tri thức hệ thống.

**Coi audit log là version model.** Audit ghi hoạt động thay đổi; version model phục vụ truy vấn dữ liệu có hiệu lực. Hai thứ có thể liên kết nhưng không thay thế nhau.

**Dùng Event Sourcing chỉ để giữ lịch sử.** Event Sourcing có chi phí replay, versioning và projection. Chọn mô hình temporal đơn giản hơn nếu chỉ cần truy vấn as-of.

## 19. Quy trình thiết kế dữ liệu theo thời gian

1. Xác định câu hỏi lịch sử mà nghiệp vụ cần trả lời.
2. Phân biệt thời điểm hiệu lực với thời điểm hệ thống ghi nhận.
3. Xác định scope của policy, price list hoặc contract.
4. Chọn kiểu thời gian: LocalDate, Instant, ZonedDateTime hoặc kiểu phù hợp.
5. Chuẩn hóa khoảng hiệu lực, ưu tiên quy ước nửa mở [from, to).
6. Xác định version nào bất biến sau khi publish.
7. Định nghĩa lifecycle của draft, approval, schedule, active và retired.
8. Bảo vệ invariant không overlap và quy tắc gap theo scope.
9. Xác định có cần Transaction Time và bitemporal hay chỉ Valid Time.
10. Lưu version reference và snapshot dữ liệu quan trọng trong quyết định/giao dịch.
11. Định nghĩa quy trình prospective change, retroactive correction và audit.
12. Bảo vệ cập nhật đồng thời bằng constraint, lock hoặc optimistic version.
13. Thiết kế query/API có `validAt`, `knownAt` và revision rõ ràng.
14. Kiểm thử ranh giới thời gian, timezone, concurrency và lịch sử.

~~~mermaid
flowchart TD
    A["Yêu cầu thay đổi policy/price/contract"] --> B["Tạo revision mới"]
    B --> C["Kiểm tra nội dung và scope"]
    C --> D["Xác định Valid Time"]
    D --> E{"Khoảng có overlap hoặc gap trái quy tắc?"}
    E -->|Có| F["Từ chối publish và yêu cầu sửa"]
    E -->|Không| G["Phê duyệt và publish"]
    G --> H["Lưu version bất biến + audit"]
    H --> I["Truy vấn theo validAt"]
    I --> J["Lưu version reference trong quyết định/giao dịch"]
~~~

## 20. Checklist trước khi đưa mô hình temporal vào production

**Ngữ nghĩa thời gian**

- Đã phân biệt Valid Time và Transaction Time chưa?
- Ngày ký, ngày hiệu lực, ngày ghi nhận và ngày chấm dứt có được lưu riêng không?
- Kiểu thời gian có đúng ngữ nghĩa: ngày lịch hay instant?
- Timezone và quy tắc DST có được xác định không?
- Khoảng thời gian có thống nhất [from, to) không?

**Version và invariant**

- Version đã công bố có được giữ bất biến không?
- Revision có định danh và thứ tự rõ ràng không?
- Scope của policy/price/contract có đầy đủ không?
- Có constraint chống overlap dưới concurrency không?
- Gap có được xử lý theo đúng quy tắc nghiệp vụ không?
- Draft, approved, scheduled, active và retired có semantics rõ không?

**Quyết định và giao dịch**

- Quyết định có lưu version policy đã dùng không?
- Đơn hàng có lưu snapshot giá và điều khoản đã chốt không?
- Có lưu evaluatedAt, validAt và input reference khi cần không?
- Thay đổi hồi tố có quy trình phê duyệt và audit không?
- Có phân biệt correction với business change không?

**Truy vấn và vận hành**

- API có phân biệt validAt, knownAt và revision không?
- Cache có tính đến scope và thời điểm hết hiệu lực không?
- Có chiến lược retention và bảo vệ dữ liệu lịch sử không?
- Có thể giải thích dữ liệu hệ thống đã biết ở một thời điểm trong quá khứ không?

**Kiểm thử**

- Đã test chính xác tại điểm bắt đầu và kết thúc khoảng chưa?
- Đã test version liền kề, overlap và gap chưa?
- Đã test sửa hồi tố trên cả hai trục thời gian chưa?
- Đã test timezone, DST, ngày nhuận và cuối tháng chưa?
- Đã test hai thao tác publish đồng thời chưa?

Mô hình hóa chính sách, giá và hợp đồng theo thời gian giúp hệ thống giữ được căn cứ của quyết định đã xảy ra. Valid Time cho biết dữ liệu có hiệu lực khi nào; Transaction Time cho biết hệ thống ghi nhận điều đó khi nào. Kết hợp version bất biến, khoảng hiệu lực rõ ràng và snapshot trong giao dịch, các Bounded Context có thể giải thích lịch sử chính xác mà vẫn hỗ trợ thay đổi nghiệp vụ trong tương lai.
