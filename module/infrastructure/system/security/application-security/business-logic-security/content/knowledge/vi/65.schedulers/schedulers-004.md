# Diễn giải thời gian của lịch chạy (Schedule time interpretation)

Trong chương **Schedulers** của module **Bảo mật logic nghiệp vụ**, bài học này giải thích cách chuyển một lịch chạy thành thời điểm thực thi cụ thể mà vẫn giữ đúng quy tắc nghiệp vụ. Trọng tâm là tránh các lỗi như áp dụng giá trước giờ, gia hạn quyền ngoài ý muốn, tính phí hai lần hoặc bỏ sót thu hồi quyền khi scheduler hiểu sai thời gian.

Một biểu thức “chạy lúc 02:30 hằng ngày” chưa phải mô tả đầy đủ. Cần biết 02:30 ở múi giờ nào, xử lý ra sao nếu giờ đó không tồn tại hoặc xuất hiện hai lần, và một tác vụ chạy muộn có còn được phép tạo tác động hay không.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt thời điểm tuyệt đối, giờ địa phương, múi giờ, độ lệch UTC và khoảng thời gian.
- Mô tả lịch chạy đủ rõ để các máy chủ khác nhau cùng tính ra một kết quả.
- Xác định chính sách cho giờ không tồn tại, giờ lặp, lịch bị lỡ và thay đổi lịch.
- Tách thời điểm dự kiến chạy khỏi thời điểm hiệu lực và điều kiện được phép thực thi.
- Kết hợp phiên bản lịch, quyền theo đối tượng, transaction và idempotency để ngăn lạm dụng.
- Thiết kế kiểm thử cho ranh giới thời gian thay vì chỉ kiểm tra một lần chạy thông thường.

## 2. Sai cách hiểu thời gian có thể phá vỡ bất biến

Giả sử một chương trình giảm giá có hiệu lực từ 09:00 ngày 15 theo giờ của đơn vị bán hàng. Nếu máy chủ diễn giải 09:00 theo múi giờ hệ điều hành, giá có thể được mở sớm hoặc muộn nhiều giờ.

Các tình huống tương tự:

| Nghiệp vụ | Cách hiểu sai | Hậu quả |
| --- | --- | --- |
| Hết hạn quyền tạm thời | Đợi tác vụ thu hồi chạy xong mới coi quyền hết hạn | Quyền còn được sử dụng sau hạn |
| Tính phí theo ngày | Coi hai lần xuất hiện của 01:30 là hai nghĩa vụ tính phí | Khách hàng bị tính phí trùng |
| Dừng nhận yêu cầu | So sánh ngày địa phương của máy chủ với ngày của khách hàng | Yêu cầu được nhận sau giờ chốt |
| Kết thúc khuyến mãi | Xem “đến ngày 30” như một thời điểm chưa được định nghĩa | Kéo dài ưu đãi hoặc kết thúc quá sớm |
| Phê duyệt có thời hạn | Tin thời gian do máy khách gửi | Người gọi lùi thời gian để dùng phê duyệt hết hạn |
| Chạy bù sau sự cố | Thực thi mọi lịch đã lỡ như thể điều kiện vẫn giữ nguyên | Chuyển trạng thái, thu tiền hoặc gửi lệnh đã không còn hợp lệ |

Trong bảo mật logic nghiệp vụ, thời gian là một đầu vào của quyết định. Nó phải được diễn giải theo hợp đồng rõ ràng, giống như số tiền, đối tượng và thẩm quyền.

## 3. Những khái niệm không được dùng thay thế cho nhau

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Thời điểm tuyệt đối, instant | `2026-11-22T10:00:00Z` | Một điểm trên trục thời gian, dùng để so sánh thứ tự và hạn chót |
| Ngày giờ địa phương | `2026-11-22 17:00` | Thông tin lịch trên đồng hồ địa phương; tự nó chưa xác định được một instant |
| Múi giờ có quy tắc | `Asia/Ho_Chi_Minh`, `America/New_York` | Tập quy tắc ánh xạ ngày giờ địa phương sang độ lệch UTC |
| Độ lệch UTC | `+07:00`, `-04:00` | Độ lệch cố định tại một thời điểm; không mô tả toàn bộ quy tắc của một vùng |
| Khoảng thời gian | 24 giờ | Độ dài trên trục thời gian |
| Quy tắc lịch | Mỗi ngày lúc 09:00 địa phương | Quy tắc chọn ngày giờ, có thể tạo các instant cách nhau không đúng 24 giờ |

Một giá trị `LocalDateTime` không mang múi giờ. Một giá trị `Instant` không giữ lại ý định “09:00 hằng ngày tại địa phương”. Lưu đúng kiểu dữ liệu giúp tránh việc các tầng tự suy đoán ý nghĩa.

UTC thường phù hợp để lưu các thời điểm đã xác định, nhưng chỉ lưu UTC là chưa đủ cho lịch lặp theo giờ địa phương. Cần giữ cả quy tắc lịch và múi giờ để tính các lần chạy tương lai đúng ý định.

Không dùng các tên viết tắt mơ hồ như `CST` làm hợp đồng lịch. Một tên viết tắt có thể mang nhiều nghĩa và không diễn đạt đầy đủ quy tắc thay đổi theo thời gian.

## 4. Hai loại lịch cần phân biệt

### 4.1. Lịch theo giờ địa phương

Ví dụ: “Mỗi ngày lúc 09:00 tại múi giờ của đơn vị”.

Lịch này bảo toàn ý định theo đồng hồ địa phương. Tại vùng có đổi giờ mùa hè, khoảng cách giữa hai lần chạy có thể là 23 hoặc 25 giờ ở các ngày chuyển đổi, nếu giờ được chọn vẫn hợp lệ.

Ứng dụng thường gặp: chốt báo cáo cuối ngày, kích hoạt giá theo ngày kinh doanh, gửi thông báo theo giờ làm việc.

### 4.2. Lịch theo khoảng thời gian

Ví dụ: “Mỗi 24 giờ tính từ mốc đã chọn”.

Lịch này bảo toàn khoảng cách trên trục thời gian. Giờ địa phương hiển thị có thể thay đổi sau khi vùng đó đổi độ lệch UTC.

Cần xác định thêm cách lấy mốc:

- **Fixed rate:** các mốc dự kiến được tính từ mốc gốc theo chu kỳ.
- **Fixed delay:** lần tiếp theo được tính sau khi lần trước kết thúc hoặc sau một sự kiện đã định.

Nếu cứ lấy thời điểm hoàn tất cộng 24 giờ, tác vụ chạy muộn sẽ làm lịch trôi dần. Đây có thể là ý định hợp lệ của fixed delay, nhưng không thể tự thay thế lịch chốt lúc 09:00 mỗi ngày.

Chọn loại lịch theo nghiệp vụ trước khi chọn cú pháp cron. Hai biểu diễn đều chứa “mỗi ngày” nhưng có thể tạo ra các thời điểm khác nhau.

## 5. Giờ không tồn tại và giờ xuất hiện hai lần

Quy tắc múi giờ có thể làm một khoảng giờ địa phương bị bỏ qua hoặc lặp lại. Không được để thư viện tự chọn một cách âm thầm nếu lựa chọn đó ảnh hưởng tiền, quyền hoặc hạn chót.

### 5.1. Khoảng trống thời gian: gap

Ví dụ lịch sử tại `America/New_York`: ngày 10-03-2024, đồng hồ chuyển từ 01:59:59 sang 03:00:00. Giờ địa phương 02:30 hôm đó không tồn tại.

Một lịch 02:30 cần chính sách rõ:

| Chính sách | Cách hiểu | Điều cần chú ý |
| --- | --- | --- |
| Bỏ lần chạy | Không tạo lần chạy cho ngày đó | Có thể bỏ sót một nghĩa vụ bắt buộc |
| Dịch theo độ dài khoảng trống | 02:30 thành 03:30 trong ví dụ này | Không giống chạy ngay lúc 03:00 |
| Chọn thời điểm hợp lệ đầu tiên sau khoảng trống | Chạy lúc 03:00 trong ví dụ này | Có thể làm nhiều lịch hội tụ vào cùng một thời điểm |
| Từ chối hoặc yêu cầu xử lý riêng | Không tự sinh một instant | Cần đường giải quyết nếu lịch đang hoạt động gặp tình huống này |

Không giả định mọi thay đổi độ lệch đều dài một giờ. Cách giải quyết phải dựa trên quy tắc của múi giờ tại ngày được tính.

### 5.2. Khoảng giờ lặp: overlap

Ví dụ lịch sử tại `America/New_York`: ngày 03-11-2024, giờ 01:30 xuất hiện hai lần:

| Ngày giờ địa phương | Độ lệch | Thời điểm UTC |
| --- | --- | --- |
| 03-11-2024 01:30 | `-04:00` | `2024-11-03T05:30:00Z` |
| 03-11-2024 01:30 | `-05:00` | `2024-11-03T06:30:00Z` |

Các chính sách có thể là chọn lần sớm, chọn lần muộn, chạy cả hai hoặc từ chối xử lý tự động. Lựa chọn phải phù hợp với nghĩa vụ nghiệp vụ.

Nếu hệ thống tính một khoản phí mỗi ngày, chạy cả hai lần không được tạo hai khoản phí cho cùng nghĩa vụ. Nếu nghiệp vụ thực sự cần hai lần đo lường theo từng instant, hai lần chạy phải có định danh phân biệt rõ.

### 5.3. Dữ liệu đầu vào phải đủ để phát hiện mâu thuẫn

Nếu API nhận cả ngày giờ địa phương, múi giờ và độ lệch, phải kiểm tra chúng khớp nhau. Không lặng lẽ bỏ qua độ lệch do người dùng chọn hoặc chấp nhận một độ lệch không có trong quy tắc của vùng đó.

Với giờ lặp, giao diện có thể yêu cầu người có quyền chọn rõ lần thứ nhất hay lần thứ hai. Với giờ không tồn tại, hiển thị kết quả điều chỉnh trước khi lưu nếu chính sách cho phép điều chỉnh. Việc tự sửa có thể làm thay đổi thời điểm một phê duyệt có hiệu lực.

## 6. Ví dụ Java: giải quyết giờ địa phương theo chính sách tường minh

Ví dụ dưới đây dùng `java.time` để minh họa. Nó hỗ trợ bỏ hoặc từ chối gap, cùng các lựa chọn overlap; không tự thực hiện chính sách dịch giờ.

```java
enum GapPolicy { REJECT, SKIP }
enum OverlapPolicy { REJECT, EARLIER, LATER, BOTH }

record ResolvedTime(
    LocalDateTime requestedLocal,
    String zoneId,
    ZoneOffset selectedOffset,
    Instant scheduledFor
) {}

List<ResolvedTime> resolve(
    LocalDateTime local,
    ZoneId zone,
    GapPolicy gapPolicy,
    OverlapPolicy overlapPolicy
) {
    List<ZoneOffset> offsets = zone.getRules().getValidOffsets(local);

    if (offsets.isEmpty()) {
        if (gapPolicy == GapPolicy.SKIP) {
            return List.of();
        }
        throw new IllegalArgumentException("NON_EXISTENT_LOCAL_TIME");
    }

    List<ZoneOffset> selected;
    if (offsets.size() == 1) {
        selected = offsets;
    } else if (offsets.size() == 2) {
        selected = switch (overlapPolicy) {
            case EARLIER -> List.of(offsets.get(0));
            case LATER -> List.of(offsets.get(1));
            case BOTH -> offsets;
            case REJECT -> throw new IllegalArgumentException(
                "AMBIGUOUS_LOCAL_TIME"
            );
        };
    } else {
        throw new IllegalStateException("UNSUPPORTED_ZONE_TRANSITION");
    }

    return selected.stream()
        .map(offset -> new ResolvedTime(
            local,
            zone.getId(),
            offset,
            ZonedDateTime.ofStrict(local, offset, zone).toInstant()
        ))
        .toList();
}
```

Cần import các lớp tương ứng trong `java.time` và `java.util.List`. Mã minh họa không thay thế bộ sinh ngày lặp, bộ phân tích cron hoặc kiểm tra quyền sửa lịch.

Những điểm đáng chú ý:

- `getValidOffsets` cho biết ngày giờ địa phương có ánh xạ hợp lệ nào.
- `ofStrict` yêu cầu ngày giờ, độ lệch và múi giờ khớp nhau; không tự điều chỉnh một bộ giá trị không hợp lệ.
- Chọn `BOTH` chỉ tạo hai ứng viên thời gian. Tầng nghiệp vụ vẫn phải quyết định có hai nghĩa vụ hay chỉ một nghĩa vụ.
- Trả danh sách rỗng theo `SKIP` là một quyết định có chủ ý. Hệ thống cần lưu được việc bỏ lần chạy nếu nó ảnh hưởng đối soát hoặc nghĩa vụ.
- Không dùng `ZoneId.systemDefault()` để thay cho múi giờ đã được duyệt của lịch.

Một lời gọi tiện dụng như `local.atZone(zone)` có cơ chế giải quyết gap và overlap mặc định. Với nghiệp vụ nhạy cảm, cần chọn và ghi nhận chính sách tường minh thay vì dựa vào mặc định mà người thiết kế chưa đánh giá.

## 7. Hợp đồng thời gian của một lịch

Một lịch có thể cần các trường sau:

```yaml
# Dữ liệu minh họa cho hợp đồng lịch.
scheduleId: schedule-431
tenantId: tenant-17
action: APPLY_DAILY_PRICE
calendarRule: "Mỗi ngày lúc 09:00"
zoneId: Asia/Ho_Chi_Minh
gapPolicy: REJECT
overlapPolicy: EARLIER
missedRunPolicy: REEVALUATE_LATEST
effectiveFrom: 2026-11-01T00:00:00Z
effectiveUntil: 2026-12-01T00:00:00Z
scheduleVersion: 4
approvalVersion: 4
```

Ví dụ dùng một quy tắc mô tả dễ đọc; khi triển khai, cần biểu diễn máy có thể kiểm tra và tính toán nhất quán.

Hợp đồng còn phải quy định:

- Cách hiểu ngày trong tuần, ngày trong tháng và lịch ngày nghỉ nếu có.
- Khoảng hiệu lực có bao gồm đầu mút nào.
- Phép chạy bù, độ muộn tối đa và giới hạn số lần chạy bù.
- Hành động được phép khi đối tượng đã đổi trạng thái.
- Cách xử lý lịch bị sửa, bị hủy hoặc bị thay thế khi đã có thông điệp chờ.
- Quy tắc gắn một lần chạy với kỳ nghiệp vụ hoặc nghĩa vụ chống trùng.

Nếu sử dụng cron, phải chỉ rõ dialect của bộ phân tích: số trường, trường giây nếu có, quy tắc phối hợp ngày trong tháng với ngày trong tuần và ngữ nghĩa ký hiệu đặc biệt. Không giả định một chuỗi cron có cùng ý nghĩa ở mọi sản phẩm hoặc thư viện.

Múi giờ là một phần của nội dung được phê duyệt nếu thay đổi nó làm đổi thời điểm tác động. Tương tự, đổi chính sách overlap từ một lần sang hai lần hoặc bật chạy bù có thể làm tăng tác động, nên phải được kiểm soát như sửa lịch nghiệp vụ.

## 8. Phân biệt thời điểm dự kiến, thời điểm chạy và thời điểm hiệu lực

Một lần chạy nên lưu riêng các mốc có ý nghĩa khác nhau:

| Mốc | Ý nghĩa | Không nên suy diễn thành |
| --- | --- | --- |
| `scheduledFor` | Instant được tính từ hợp đồng lịch | Thời gian worker chắc chắn bắt đầu |
| `enqueuedAt` | Thời gian đưa vào hàng đợi | Bằng chứng nghiệp vụ đã thực hiện |
| `startedAt` | Thời gian worker bắt đầu xử lý | Thời điểm được phép bỏ qua kiểm tra hết hạn |
| `authorizationCheckedAt` | Thời gian dùng trong quyết định thẩm quyền | Cam kết mọi hệ thống đã tạo tác động cùng lúc |
| `completedAt` | Thời gian ghi nhận hoàn tất theo thiết kế | Ngày nghiệp vụ của nghĩa vụ gốc |
| `businessDate` hoặc `periodId` | Kỳ nghiệp vụ mà công việc thuộc về | Ngày địa phương của máy đang xử lý |

Ví dụ, lịch 09:00 tại `Asia/Ho_Chi_Minh` ngày 22-11-2026 tương ứng `2026-11-22T02:00:00Z`. Worker bắt đầu lúc 09:07 không được tự đổi `scheduledFor` thành 09:07 để che độ trễ hoặc đặt lại hạn xử lý.

Nếu một tác vụ đối soát của ngày hôm trước chạy sau nửa đêm, kỳ nghiệp vụ vẫn phải được xác định theo hợp đồng của tác vụ. Không lấy `LocalDate.now()` của worker để quyết định kỳ rồi hạch toán sang ngày mới.

Ngược lại, giữ kỳ nghiệp vụ cũ không có nghĩa được giả mạo thời gian tạo tác động. Cần lưu cả kỳ gốc lẫn thời gian thực tế. Những thao tác hồi tố phải có chính sách riêng, điều kiện phê duyệt và dấu vết kiểm toán.

## 9. Ranh giới hiệu lực: dùng khoảng thời gian rõ ràng

Một quy tắc thông dụng là dùng khoảng nửa mở:

```text
validAt(now) = effectiveFrom <= now AND now < effectiveUntil
```

Theo quy tắc này, đúng bằng `effectiveUntil` thì điều kiện không còn hiệu lực. Không để API dùng `<=` ở đầu mút cuối trong khi worker dùng `<`, vì hai đường có thể quyết định khác nhau tại cùng một mốc.

Với yêu cầu “có hiệu lực hết ngày 30 tại múi giờ của đơn vị”, cách mô hình hóa thường là:

1. Xác định ngày 30 theo lịch và múi giờ nghiệp vụ.
2. Xác định ranh giới bắt đầu ngày tiếp theo theo chính sách giải quyết thời gian của vùng đó.
3. Dùng ranh giới đó làm đầu mút loại trừ.

Tránh dựng mốc `23:59:59.999`: độ chính xác dữ liệu giữa các tầng có thể khác nhau, còn một ngày địa phương không phải lúc nào cũng dài đúng 24 giờ. Một số vùng có thể chuyển quy tắc ở gần nửa đêm, nên việc tính ranh giới ngày cũng cần chính sách rõ chứ không chỉ ghép chuỗi ngày với `00:00`.

Không dùng thời gian do máy khách tự khai làm `now`. Máy khách có thể gửi một thời điểm mong muốn để lập lịch nếu được phép, nhưng máy chủ phải kiểm tra nó theo nguồn thời gian và giới hạn của hệ thống.

## 10. Scheduler kích hoạt công việc; đường nghiệp vụ vẫn giữ điều kiện thời gian

Một lỗi nguy hiểm là dùng scheduler làm cơ chế duy nhất để bảo vệ hạn chót.

Ví dụ sai với quyền tạm thời:

```text
09:00: quyền đáng lẽ hết hạn
09:00: tác vụ thu hồi chưa được chạy
09:10: API chỉ kiểm tra active = true nên vẫn cho truy cập
```

Đường truy cập cần tự kiểm tra `now < expiresAt` theo chính sách. Scheduler có thể thu hồi dữ liệu phụ, dọn cache hoặc gửi thông báo, nhưng việc chậm chạy không được tự gia hạn quyền.

Tương tự:

- Giá chưa đến giờ hiệu lực không được áp dụng chỉ vì tác vụ bị chạy sớm.
- Khuyến mãi hết hạn không được tiếp tục sử dụng chỉ vì tác vụ tắt chương trình đang kẹt.
- Phê duyệt còn hạn lúc lập lịch có thể hết hạn trước khi tác vụ tạo tác động.
- Một đơn đã hủy không được chuyển tiếp chỉ vì thông điệp cũ vẫn tồn tại.

Với dữ liệu đã sao chép ra cache hoặc dịch vụ khác, phải xác định nơi kiểm tra điều kiện cuối cùng. Một lần kiểm tra trong scheduler không bảo vệ được một dịch vụ đích tự áp dụng lệnh muộn mà không biết hạn hoặc phiên bản hiện tại.

## 11. Chính sách cho lịch bị lỡ và tác vụ chạy muộn

Khi scheduler dừng một giờ rồi hoạt động lại, “chạy bù” là một quyết định nghiệp vụ, không chỉ là tùy chọn hạ tầng.

| Chính sách | Cách xử lý | Ví dụ có thể phù hợp |
| --- | --- | --- |
| Bỏ lần đã lỡ | Không chạy một lần không còn giá trị | Một số thông báo nhắc theo thời điểm |
| Chạy bù từng nghĩa vụ | Giữ từng kỳ và xử lý các nghĩa vụ còn thiếu | Đối soát theo kỳ nếu mỗi kỳ phải có kết quả riêng |
| Gộp và đánh giá trạng thái hiện tại | Chọn thay đổi cuối cùng còn hiệu lực | Đồng bộ giá hiện hành sau nhiều mốc cập nhật |
| Từ chối quá muộn và chuyển xử lý | Không tự tạo tác động ngoài cửa sổ cho phép | Hành động có phê duyệt hoặc thời hạn chặt |

Ví dụ: giá A có hiệu lực lúc 09:00, giá B có hiệu lực lúc 10:00, scheduler phục hồi lúc 11:00. Nếu mục tiêu là trạng thái giá hiện hành, áp dụng B rồi lại áp dụng A do thông điệp đến ngược thứ tự là sai. Có thể cần đánh giá khoảng hiệu lực và phiên bản để chỉ áp dụng giá đang hợp lệ.

Với tính phí theo kỳ, bỏ hết kỳ cũ để chỉ chạy kỳ gần nhất lại có thể làm mất nghĩa vụ. Chính sách phải gắn với loại hành động, không chọn chung một cách cho mọi lịch.

Chạy bù cần giới hạn số lượng, tải và thời gian. Tuy nhiên, giới hạn tải không được làm biến mất nghĩa vụ còn thiếu; phải còn trạng thái chờ, bằng chứng bị bỏ theo chính sách hoặc yêu cầu xử lý tiếp.

Độ muộn tối đa phải tính từ mốc nghĩa vụ gốc. Retry, chuyển hàng đợi hay đổi worker không được đặt lại `scheduledFor` để tiếp tục hợp thức hóa một lệnh đã quá cửa sổ.

## 12. Định danh lần chạy và định danh nghĩa vụ nghiệp vụ

Hai tầng chống trùng giải quyết hai vấn đề khác nhau:

- **Lần chạy của lịch:** một ứng viên được sinh từ quy tắc, múi giờ, chính sách và phiên bản lịch.
- **Nghĩa vụ nghiệp vụ:** tác động thực tế cần tạo đúng số lần theo hợp đồng.

Một bản ghi lần chạy có thể lưu:

```yaml
scheduleId: schedule-431
scheduleVersion: 4
requestedLocalTime: 2026-11-22T09:00:00
zoneId: Asia/Ho_Chi_Minh
selectedOffset: "+07:00"
scheduledFor: 2026-11-22T02:00:00Z
businessDate: 2026-11-22
operationId: price-tenant-17-2026-11-22
state: PLANNED
```

Trong giờ lặp, hai ứng viên có thể cùng `requestedLocalTime` nhưng khác độ lệch và instant. Nếu chính sách chọn cả hai, định danh ứng viên phải phân biệt được chúng.

Nhưng nếu chỉ có một khoản phí cho mỗi ngày kinh doanh, khóa chống trùng nghiệp vụ có thể dựa trên đơn vị, hợp đồng, loại khoản phí và kỳ. Hai ứng viên khác nhau vẫn không được tạo hai khoản phí cho cùng nghĩa vụ đó.

Không dùng riêng `scheduleVersion` hoặc `scheduledFor` làm bằng chứng rằng một tác động mới được phép. Sửa lịch từ phiên bản 4 sang 5 có thể tạo ứng viên khác nhưng vẫn thuộc cùng nghĩa vụ đã hoàn tất.

Cần ràng buộc duy nhất và transaction ở kho dữ liệu phù hợp. Kiểm tra “chưa có lần chạy” rồi chèn mà không có bảo vệ nguyên tử vẫn có thể tạo trùng khi nhiều scheduler cùng tính một mốc.

## 13. Thay đổi lịch, hủy lịch và thông điệp cũ

Một lịch đã đổi không làm các thông điệp đang chờ tự biến mất.

Giả sử người có quyền đổi giờ kích hoạt giá từ 09:00 sang 12:00. Thông điệp của phiên bản cũ đã nằm trong hàng đợi lúc 08:55. Worker chạy lúc 09:00 phải kiểm tra xem phiên bản đó còn được phép áp dụng hay không.

Một giao thức thực thi có thể gồm:

```text
Trong transaction của nơi tạo tác động:
  1. Khóa hoặc bảo vệ phiên bản lịch, lần chạy và đối tượng liên quan.
  2. Lấy thời gian có thẩm quyền sau các bước chờ khóa cần thiết.
  3. Kiểm tra lịch chưa bị hủy và phiên bản lần chạy còn hợp lệ.
  4. Kiểm tra scheduledFor <= now và các cửa sổ hiệu lực, độ muộn.
  5. Kiểm tra thẩm quyền hiện tại, phê duyệt và trạng thái đối tượng.
  6. Kiểm tra hoặc chiếm khóa nghĩa vụ nghiệp vụ một cách nguyên tử.
  7. Tạo tác động, lưu kết quả, audit và outbox trong cùng phạm vi phù hợp.
```

Các luồng sửa, hủy và thực thi phải phối hợp bằng cùng cơ chế khóa hoặc phiên bản. Đọc lịch từ cache rồi cập nhật đối tượng sau đó không tự bảo đảm rằng lịch chưa bị hủy trong khoảng giữa.

Cần công bố cách xử lý tác vụ đang chạy. Nếu transaction thực thi đã giành quyền hợp lệ trước transaction hủy theo giao thức tuần tự hóa đã chọn, nó có thể hoàn tất trước khi hủy có hiệu lực. Không hứa hủy hồi tố một tác động đã commit.

Với dịch vụ đích khác cơ sở dữ liệu, khóa nội bộ không tự khóa được tác động bên ngoài. Có thể cần phiên bản, fencing token, khóa idempotency hoặc cơ chế kiểm tra điều kiện tại phía đích. Hiệu lực hủy phải được xác định trong giao thức đó; chỉ thêm một trường phiên bản vào thông điệp là chưa đủ.

Một lần chạy bị từ chối do phiên bản cũ phải có kết quả rõ như `SUPERSEDED` theo mô hình của hệ thống. Không retry vô hạn một lệnh mà điều kiện hợp lệ đã mất.

## 14. Nguồn thời gian, độ chính xác và thay đổi quy tắc múi giờ

### 14.1. Dùng nguồn thời gian nhất quán cho quyết định

Các máy chủ có thể lệch đồng hồ. Nếu API, scheduler và cơ sở dữ liệu mỗi nơi tự quyết định hạn theo đồng hồ riêng mà không có giới hạn rõ, tác vụ có thể được cho phép ở một nơi và bị từ chối ở nơi khác.

Cần xác định nguồn thời gian có thẩm quyền cho từng quyết định. Trong transaction nội bộ, có thể lấy thời gian từ cơ sở dữ liệu hoặc một nguồn được quy định, nhưng phải hiểu ngữ nghĩa của hàm đang dùng. Một số hàm trả thời gian bắt đầu transaction thay vì thời gian thực tại lúc gọi; sau khi chờ khóa lâu, giá trị đó có thể không phù hợp cho kiểm tra hạn mới.

Không tự cộng “vài phút dung sai” để biến một quyền hết hạn thành còn hiệu lực. Dung sai, nếu được phép, phải là một phần chính sách đã định và được đánh giá về tác động.

Một lần kiểm tra trước khi commit không tự bảo đảm commit xảy ra trước hạn chót tuyệt đối. Nếu yêu cầu chặt tới thời điểm áp dụng tác động, phải thiết kế điểm quyết định và cơ chế thực thi tương ứng, đồng thời quy định cách xử lý các thao tác đang chạy.

### 14.2. Đồng hồ tường và đồng hồ đơn điệu có vai trò khác nhau

`Instant` phù hợp để lưu mốc lịch, hạn và bằng chứng thời gian theo hợp đồng. Đồng hồ đơn điệu phù hợp để đo khoảng chờ hoặc thời gian chạy trong một tiến trình.

Ví dụ trong Java, `System.nanoTime()` có thể dùng để đo thời lượng cục bộ, nhưng không dùng làm thời điểm lịch để lưu sang cơ sở dữ liệu hoặc so sánh giữa hai máy. Ngược lại, thay đổi đồng hồ tường có thể ảnh hưởng phép đo thời lượng nếu cứ lấy hai giá trị ngày giờ trừ nhau mà không xét ngữ nghĩa.

Nếu đồng hồ tường nhảy lùi rồi đi qua cùng một mốc lần nữa, khóa chống trùng nghiệp vụ vẫn phải ngăn tác động thứ hai. Nếu đồng hồ nhảy tiến, chính sách lịch bị lỡ vẫn phải quyết định xử lý, thay vì mặc nhiên thực thi mọi việc ngay lập tức.

### 14.3. Quy tắc múi giờ có thể thay đổi

Một lịch tương lai theo giờ địa phương phụ thuộc bộ quy tắc múi giờ đang sử dụng. Các máy chạy phiên bản dữ liệu khác nhau có thể tính khác nhau khi quy tắc liên quan đã được cập nhật.

Cần xác định ý định:

- **Giữ instant đã chốt:** phù hợp khi các bên đã thống nhất một thời điểm tuyệt đối và thay đổi cần quy trình riêng.
- **Giữ giờ địa phương:** các lần chạy tương lai có thể phải được tính lại khi quy tắc thay đổi, theo chính sách đã được phê duyệt.

Nên lưu đủ bằng chứng để giải thích cách tính: ngày giờ địa phương được yêu cầu, tên vùng, độ lệch đã chọn, instant kết quả và thông tin phiên bản quy tắc nếu nền tảng cung cấp.

Khi tính lại các lần chưa chạy, phải xử lý phiên bản lịch và thông điệp cũ để không tạo hai tác động. Những lần đã thực hiện phải giữ nguyên lịch sử; không viết lại instant cũ theo bộ quy tắc mới rồi làm mất bằng chứng ban đầu.

## 15. Quyền sửa thời gian cũng là quyền thay đổi tác động

Một người không được phép sửa số tiền vẫn có thể gây thiệt hại nếu được tự ý đổi thời điểm áp dụng giá hoặc lịch thu tiền.

Cần kiểm soát theo đối tượng đối với:

- Tạo, sửa và hủy lịch của từng đơn vị.
- Đổi múi giờ, ngày hiệu lực, chính sách giờ lặp và lịch bị lỡ.
- Cho phép chạy sớm, chạy bù hoặc thực hiện hồi tố.
- Thay đổi lịch của một đối tượng đã được phê duyệt.
- Phát lại thông điệp hoặc kích hoạt chạy thủ công.

Đổi một trong các trường đó có thể làm thay đổi tác động, nên phê duyệt phải gắn với nội dung và phiên bản cụ thể. Không giữ phê duyệt cũ khi người gọi đã dời thời điểm sang một cửa sổ mà họ không có quyền sử dụng.

API không được tin một trường như `force=true`, `timezoneOverride` hay `clientNow` để bỏ điều kiện. Nếu có quyền chạy khẩn cấp, đó phải là hành động riêng có phạm vi, lý do và kiểm toán phù hợp.

## 16. Tình huống xuyên suốt: áp dụng giá theo lịch

Giả sử `tenant-17` có giá A từ 09:00 và giá B từ 10:00 cùng ngày theo `Asia/Ho_Chi_Minh`.

1. Người có quyền tạo lịch với múi giờ, khoảng hiệu lực và chính sách chạy muộn rõ ràng. Nội dung được duyệt gắn với đúng phiên bản.
2. Scheduler chuyển các mốc địa phương thành instant và lưu thông tin giải quyết thời gian. Các bản sao scheduler không được tạo trùng cùng ứng viên theo khóa đã chọn.
3. Hệ thống ngừng xử lý đến 11:00. Hai thông điệp đều có thể xuất hiện sau khi khôi phục.
4. Worker lấy lại lịch và trạng thái hiện tại. Với mục tiêu duy trì giá hiện hành, nó đánh giá giá nào còn hiệu lực thay vì áp dụng tuần tự mọi thông điệp cũ.
5. Giá B được áp dụng theo quyền, phiên bản và bất biến. Thông điệp giá A đến sau không được ghi đè B chỉ vì nó vừa được nhận.
6. Nếu lịch B đã bị hủy trước điểm quyết định hợp lệ, worker xử lý theo phiên bản mới và chính sách hiện hành, không tin payload cũ.
7. Một yêu cầu chạy lại không tạo tác động trùng hoặc hồi tố đơn hàng đã chốt. Giá của đơn hàng được xác định theo quy tắc của đơn, không bị sửa lịch sử tùy ý bởi tác vụ đồng bộ giá.

Thiết kế này cũng có thể lưu các khoảng giá hiệu lực để đường đặt hàng tự chọn theo thời gian có thẩm quyền. Khi đó, scheduler phục vụ cập nhật dữ liệu phụ hoặc thông báo, còn quyết định giá không chỉ phụ thuộc việc một tác vụ đã chạy đúng giờ hay chưa.

## 17. Kiểm thử ranh giới thời gian và đường lạm dụng

Dùng đồng hồ có thể điều khiển, múi giờ cố định trong từng ca kiểm thử và nguồn quy tắc được xác định. Không chờ đến một ngày đổi giờ thực tế mới kiểm tra.

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| Cùng lịch chạy trên máy có múi giờ hệ điều hành khác nhau | Kết quả theo múi giờ lịch, không theo máy chủ |
| Đầu vào thiếu vùng cho một giờ địa phương cần vùng | Bị từ chối hoặc yêu cầu bổ sung theo hợp đồng; không tự đoán |
| Ngày giờ nằm trong gap | Xử lý đúng chính sách, có bằng chứng bỏ hoặc điều chỉnh |
| Ngày giờ nằm trong overlap | Chọn đúng một hoặc hai instant theo chính sách |
| Đầu vào có độ lệch không khớp vùng | Bị từ chối, không âm thầm đổi ý nghĩa |
| Đúng bằng thời điểm bắt đầu | Được xem xét hợp lệ theo đầu mút bao gồm |
| Đúng bằng thời điểm kết thúc | Không còn hợp lệ theo đầu mút loại trừ |
| Hạn quyền đã đến nhưng tác vụ thu hồi chưa chạy | Đường truy cập vẫn từ chối theo hạn |
| Tác vụ chạy sớm do tín hiệu hàng đợi | Không tạo tác động trước `scheduledFor` hoặc cửa sổ nghiệp vụ |
| Tác vụ chạy muộn sau khi phê duyệt hết hạn | Kiểm tra lại và từ chối hoặc chuyển xử lý đúng chính sách |
| Hai lần giờ lặp cùng thuộc một nghĩa vụ phí | Không tạo hai khoản phí |
| Đổi lịch tạo ứng viên mới cho nghĩa vụ đã xong | Không tạo lại tác động chỉ vì khác phiên bản hoặc instant |
| Thông điệp cũ đến sau khi hủy lịch | Không vượt qua kiểm tra phiên bản và trạng thái |
| Hai thay đổi giá đến ngược thứ tự | Giá cũ không ghi đè giá mới đang có hiệu lực |
| Chạy bù sau thời gian ngừng dài | Giữ đúng kỳ, giới hạn tải và dấu vết nghĩa vụ chưa xử lý |
| Đồng hồ nhảy lùi rồi đi qua cùng mốc | Không lặp tác động nghiệp vụ |
| Đồng hồ nhảy tiến qua nhiều mốc | Áp dụng chính sách lịch bị lỡ, không tự bỏ hoặc chạy tất cả |
| Người thuộc đơn vị khác sửa múi giờ hoặc giờ chạy | Bị chặn theo quyền đối tượng |
| Sửa thời gian sau phê duyệt | Không dùng phê duyệt cũ cho nội dung đã thay đổi |
| Cập nhật quy tắc múi giờ cho lịch tương lai | Tính lại hoặc giữ instant theo chính sách, không tạo trùng |

Với kiểm thử đồng thời, kiểm soát thứ tự sửa lịch, lấy khóa, kiểm tra thời gian, tạo tác động và commit. Chỉ kiểm tra chuỗi instant được tính ra chưa đủ; cần kiểm tra cả điều kiện nghiệp vụ cuối cùng và số tác động thực tế.

Với cron, dùng các ca chứng minh ngữ nghĩa của đúng parser đang triển khai, đặc biệt ở các tổ hợp ngày trong tuần, ngày trong tháng và múi giờ. Khi đổi thư viện hoặc cấu hình parser, phải đánh giá lại các lịch chịu ảnh hưởng.

## 18. Những quyết định phải rõ trong thiết kế

Một hợp đồng lịch đủ cụ thể cần trả lời được:

1. Đây là lịch theo giờ địa phương hay theo khoảng thời gian, và mốc gốc là gì?
2. Múi giờ thuộc đơn vị nào, ai được chọn và thay đổi nó?
3. Giờ không tồn tại, giờ lặp và ranh giới ngày được xử lý ra sao?
4. Mỗi lần chạy thuộc kỳ nghiệp vụ nào và khóa nghĩa vụ chống trùng là gì?
5. Các đầu mút hiệu lực có bao gồm hay loại trừ, theo độ chính xác nào?
6. Nếu chạy sớm, chạy muộn hoặc lỡ nhiều lần, hành động nào còn được phép?
7. Đường tạo tác động kiểm tra lại thời gian, quyền và trạng thái ở đâu?
8. Sửa hoặc hủy lịch ảnh hưởng thế nào đến thông điệp cũ và tác vụ đang chạy?
9. Khi quy tắc múi giờ thay đổi, lịch giữ instant hay giữ giờ địa phương?
10. Bằng chứng nào giúp giải thích vì sao một tác động đã xảy ra tại thời điểm đó?

Diễn giải thời gian chính xác giúp lịch chạy giữ được ý định nghiệp vụ qua nhiều máy chủ, nhiều múi giờ và các lần xử lý muộn. Các mốc thời gian, phiên bản và khóa nghĩa vụ phải cùng tham gia vào quyết định thực thi để lịch không trở thành đường vòng vượt hạn hoặc tạo tác động trùng.
