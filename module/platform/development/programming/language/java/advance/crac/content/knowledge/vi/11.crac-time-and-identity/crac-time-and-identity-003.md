# TTL, thời điểm hết hạn và vô hiệu hóa dữ liệu đã cũ

TTL (Time To Live) quy định một dữ liệu được xem là còn hợp lệ trong bao lâu. Trong ứng dụng Java chạy liên tục, cache thường kiểm tra TTL khi đọc hoặc dùng tác vụ nền để làm mới dữ liệu. Với CRaC, tiến trình có thể được checkpoint rồi tạm dừng trong một khoảng thời gian. Trong thời gian đó, đồng hồ vẫn tiến lên và hệ thống bên ngoài vẫn thay đổi, nhưng các thread, scheduler và cache trong heap không nhất thiết thực hiện công việc làm mới như khi ứng dụng đang chạy.

Khi restore, object cache và các mốc thời gian đã lưu có thể vẫn tồn tại. Một entry từng hợp lệ trước checkpoint có thể đã hết hạn; một lease có thể đã bị hệ thống khác cấp lại; một token có thể đã bị thu hồi; một sự kiện invalidation có thể đã được phát ra khi ứng dụng không hoạt động. Vì vậy, ứng dụng không nên coi dữ liệu trong heap là mới chỉ vì nó vừa được khôi phục. Cần kiểm tra thời điểm hết hạn, xác minh version và vô hiệu hóa hoặc làm mới dữ liệu trước khi dùng lại.

## 1. TTL và thời điểm hết hạn

TTL là khoảng thời gian một dữ liệu được phép tồn tại hoặc được xem là có thể sử dụng. Thời điểm hết hạn (`expiresAt`) là mốc cụ thể mà sau đó dữ liệu không còn hợp lệ theo chính sách.

Ví dụ, ứng dụng đọc một cấu hình lúc 10:00 với TTL 5 phút:

```text
fetchedAt = 10:00
TTL       = 5 phút
expiresAt = 10:05
```

Nếu ứng dụng checkpoint lúc 10:02 và restore lúc 10:20, entry đã hết hạn dù object vẫn còn trong heap. Không được tính TTL từ thời điểm restore và tự gia hạn thành 10:25, trừ khi chính sách nghiệp vụ nói rõ TTL bắt đầu lại khi dữ liệu được nạp mới.

Một số thuật ngữ thường gặp:

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| TTL | Khoảng thời gian hợp lệ tính từ một mốc xác định, thường là lúc tạo hoặc lấy dữ liệu. |
| `fetchedAt` / `createdAt` | Thời điểm dữ liệu được lấy hoặc tạo. |
| `expiresAt` | Thời điểm dữ liệu hết hạn theo nguồn có thẩm quyền hoặc chính sách cache. |
| Soft TTL | Mốc nên làm mới dữ liệu; trong một số chính sách, dữ liệu cũ vẫn có thể được phục vụ tạm thời. |
| Hard TTL | Mốc hết hạn bắt buộc; sau mốc này không được sử dụng dữ liệu như thể còn hợp lệ. |
| Lease | Quyền sử dụng tài nguyên trong một khoảng thời gian, thường do hệ thống bên ngoài cấp và có thể bị hết hạn hoặc cấp lại. |
| Invalidation | Hành động đánh dấu hoặc loại bỏ dữ liệu cache vì dữ liệu nguồn đã thay đổi, bị thu hồi hoặc không còn được phép sử dụng. |

TTL là một chính sách về tính hợp lệ, không chỉ là cơ chế dọn bộ nhớ. Một cache có thể vẫn giữ entry hết hạn trong heap nhưng phải từ chối trả entry đó cho caller. Việc xóa vật lý có thể diễn ra sau đó.

## 2. TTL tương đối và thời điểm hết hạn tuyệt đối

Có hai cách phổ biến để biểu diễn thời gian hết hạn.

**TTL tương đối:** lưu khoảng thời gian còn hiệu lực hoặc một deadline tính từ đồng hồ monotonic. Cách này phù hợp cho các khoảng chờ trong cùng một vòng đời runtime vì không bị ảnh hưởng bởi việc đồng hồ hệ thống được chỉnh nhanh hoặc chậm.

**Thời điểm hết hạn tuyệt đối:** lưu một mốc thời gian như `Instant` hoặc epoch timestamp. Cách này phù hợp khi hạn sử dụng được quyết định bởi hệ thống bên ngoài, ví dụ token JWT, credential, lease hoặc cache record được chia sẻ giữa nhiều tiến trình.

| Nhu cầu | Biểu diễn phù hợp | Lưu ý khi restore |
| --- | --- | --- |
| Chờ một thao tác tối đa 5 giây trong callback | Deadline dựa trên `System.nanoTime()` | Chỉ dùng trong thao tác hiện tại; không lưu deadline monotonic làm hạn sử dụng lâu dài qua checkpoint. |
| Token có `exp` do issuer cấp | `Instant expiresAt` | So sánh với thời gian hiện tại sau restore; không tự gia hạn token. |
| Cache entry có TTL do ứng dụng đặt | Lưu `fetchedAt` và TTL hoặc `expiresAt` | Tính lại thời gian còn lại sau restore, hoặc xóa và nạp lại cache. |
| Lease do database/service cấp | Expiry/version do bên cấp lease xác định | Xác minh lại với bên cấp trước khi tiếp tục thao tác có tác động. |
| Scheduled refresh | Lưu mốc refresh/expiry theo thời gian tuyệt đối hoặc tính lại từ policy | Hủy hoặc xây dựng lại lịch sau restore; không giả định timer cũ đã chạy trong thời gian checkpoint. |

Không nên nhầm `System.nanoTime()` với thời gian lịch. Giá trị của nó chỉ có ý nghĩa khi so sánh các lần đọc trong cùng một miền thời gian chạy; không đại diện cho ngày giờ và không thể chuyển thành timestamp dùng chung giữa các máy. Khi dữ liệu cần sống qua checkpoint, hãy lưu mốc expiry có ý nghĩa bên ngoài hoặc metadata đủ để tính lại deadline.

## 3. Dùng đồng hồ đúng mục đích trong Java

### Đồng hồ monotonic cho khoảng thời gian

`System.nanoTime()` phù hợp để đo elapsed time và deadline trong một thao tác đang chạy:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);

if (System.nanoTime() - deadline >= 0) {
    throw new TimeoutException("Operation deadline exceeded");
}
```

Phép trừ theo cách này tránh so sánh trực tiếp hai giá trị deadline khi bộ đếm có thể wrap quanh, miễn là khoảng thời gian được đo nhỏ hơn phạm vi biểu diễn hợp lệ của phép so sánh. Không dùng giá trị `nanoTime` làm thời điểm hết hạn được lưu vào database hoặc gửi qua network.

Trong CRaC, không nên giả định deadline `nanoTime` đã lưu trong heap vẫn có cùng ý nghĩa sau restore. Thời gian checkpoint có thể khiến một deadline cũ không còn phản ánh đúng khoảng thời gian cần thiết; cách triển khai restore và clock của nền tảng cũng cần được xem xét. Với TTL cần tính cả thời gian ứng dụng tạm dừng, hãy lưu `expiresAt` tuyệt đối rồi dựng lại deadline monotonic mới sau restore.

### Đồng hồ wall-clock cho expiry tuyệt đối

`Instant.now()` hoặc `Clock` cho phép so sánh với một mốc thời gian lịch:

```java
Instant expiresAt = Instant.parse("2026-11-13T10:30:00Z");

if (!Clock.systemUTC().instant().isBefore(expiresAt)) {
    throw new IllegalStateException("Credential has expired");
}
```

Quy tắc biên thường dùng là `now >= expiresAt` thì dữ liệu đã hết hạn. Nên dùng `Clock` được inject vào service để kiểm thử dễ dàng, thay vì gọi `Instant.now()` rải rác khắp code.

Wall-clock có thể bị ảnh hưởng bởi clock skew, NTP adjustment hoặc cấu hình sai trên host. Với token/lease do server cấp, hãy dùng nguồn thời gian đáng tin cậy, dành safety margin phù hợp và xử lý sai lệch đồng hồ. Không nên kéo dài hiệu lực token chỉ vì đồng hồ local có thể chậm.

## 4. Fixed TTL, sliding TTL và hard expiry

TTL có thể được áp dụng theo các chính sách khác nhau:

| Chính sách | Cách tính | Trường hợp phù hợp | Rủi ro |
| --- | --- | --- | --- |
| Fixed TTL | Hết hạn sau một khoảng cố định kể từ lúc lấy/tạo dữ liệu | Cấu hình, metadata, cache kết quả truy vấn | Dữ liệu có thể hết hạn dù vẫn được truy cập thường xuyên. |
| Sliding TTL | Mỗi lần truy cập hợp lệ lại kéo dài thời gian hết hạn | Session inactivity timeout hoặc cache nội bộ theo chính sách cụ thể | Một entry có thể sống rất lâu nếu liên tục được truy cập, dù nguồn đã thay đổi. |
| Absolute expiry | Hết hạn tại một mốc do issuer hoặc hệ thống nghiệp vụ quyết định | Token, credential, certificate, lease và dữ liệu có hạn sử dụng | Không được tự dời mốc expiry khi restore hoặc khi cache được đọc lại. |
| Soft TTL + hard TTL | Làm mới từ soft TTL, nhưng chỉ được phục vụ stale đến hard TTL nếu chính sách cho phép | Dữ liệu tham khảo có thể chấp nhận độ trễ ngắn | Dễ vô tình phục vụ dữ liệu đã bị thu hồi nếu không phân biệt loại dữ liệu. |

Với dữ liệu xác thực, quyền truy cập, lease khóa hoặc trạng thái thu hồi, cần áp dụng hard expiry và kiểm tra trạng thái có thẩm quyền. Không dùng sliding TTL để biến một token đã hết hạn thành token hợp lệ.

## 5. Vì sao TTL cần được kiểm tra lại sau restore?

Checkpoint bảo toàn trạng thái bộ nhớ tại thời điểm tạo ảnh. Nó không đóng băng đồng hồ của hệ thống bên ngoài và cũng không ngăn các actor khác thay đổi dữ liệu nguồn.

Ví dụ, cache quyền truy cập có TTL 10 phút được nạp lúc 08:00. Ứng dụng checkpoint lúc 08:04. Đến 08:06, quản trị viên thu hồi quyền của một user. Ứng dụng restore lúc 08:15. Nếu chỉ dùng object cache trong heap, ứng dụng có thể tiếp tục cho phép hành động dựa trên quyền cũ.

Các nguyên nhân khiến dữ liệu cũ sau restore gồm:

- TTL đã hết trong thời gian checkpoint.
- Nguồn dữ liệu đã cập nhật nhưng cache invalidation event bị bỏ lỡ.
- Secret, token hoặc certificate đã bị xoay vòng/thu hồi.
- Lease đã hết hạn và được cấp cho một instance khác.
- Endpoint hoặc service version đã thay đổi.
- Scheduled refresh đã đến hạn nhưng scheduler không chạy trong lúc process bị checkpoint.
- Một request đang chạy trước checkpoint đã tạo kết quả cũ và kết quả đó được ghi vào cache sau khi hệ thống nguồn đã đổi version.

Do đó, restore cần có một pha kiểm tra freshness trước khi cache hoặc tài nguyên được dùng để phục vụ request.

## 6. Lưu expiry trong cache entry

Với cache entry có hạn tuyệt đối, nên lưu giá trị cùng metadata về thời điểm lấy và hết hạn:

```java
import java.time.Instant;

public record CacheEntry<V>(
        V value,
        Instant fetchedAt,
        Instant expiresAt,
        long sourceVersion) {

    public boolean isExpired(Instant now) {
        return !now.isBefore(expiresAt);
    }
}
```

Khi đọc cache:

```java
import java.time.Clock;
import java.util.Optional;

public <V> Optional<V> getFresh(
        CacheEntry<V> entry,
        Clock clock) {
    if (entry == null || entry.isExpired(clock.instant())) {
        return Optional.empty();
    }
    return Optional.of(entry.value());
}
```

Nếu TTL được cấp bởi source, nên lưu `expiresAt` hoặc metadata đủ để tái dựng chính xác thời điểm đó. Không đặt lại `fetchedAt = Instant.now()` khi restore cho một entry cũ vì điều đó vô tình cấp thêm TTL.

Nếu source chỉ cung cấp TTL tương đối, hãy xác định rõ TTL bắt đầu tính từ lúc source tạo dữ liệu, lúc response được phát, hay lúc client nhận response. Khi cần bảo toàn qua checkpoint, chuyển mốc đó thành `expiresAt` theo quy ước đã thống nhất.

## 7. Dựng lại deadline monotonic sau restore

Một cache có thể cần deadline monotonic để kiểm tra nhanh khi ứng dụng chạy. Hãy giữ `expiresAt` tuyệt đối làm metadata có thể khôi phục, rồi tính lại deadline monotonic khi nạp cache sau restore:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public final class RuntimeDeadline {
    private final long deadlineNanos;

    private RuntimeDeadline(long deadlineNanos) {
        this.deadlineNanos = deadlineNanos;
    }

    public static RuntimeDeadline fromExpiry(
            Instant expiresAt,
            Clock clock) {
        Duration remaining = Duration.between(clock.instant(), expiresAt);
        if (remaining.isNegative() || remaining.isZero()) {
            throw new IllegalArgumentException("Entry already expired");
        }
        return new RuntimeDeadline(
                System.nanoTime() + remaining.toNanos());
    }

    public boolean isExpired() {
        return System.nanoTime() - deadlineNanos >= 0;
    }
}
```

Trong ví dụ này, `RuntimeDeadline` được tạo lại sau restore từ `expiresAt`. Không serialize hoặc giữ `deadlineNanos` như nguồn sự thật xuyên qua checkpoint. Nếu thời gian đã hết, entry phải bị loại bỏ hoặc refresh trước khi được sử dụng.

Với TTL cực lớn, cần xử lý overflow khi chuyển `Duration` sang nanoseconds và chọn cách biểu diễn phù hợp. Hạn sử dụng thực tế thường ngắn hơn nhiều, nhưng code thư viện dùng chung không nên giả định mọi Duration đều chuyển đổi an toàn.

## 8. Invalidation: xóa, đánh dấu stale và thay version

TTL chỉ là một cơ chế hết hạn theo thời gian. Invalidation xảy ra khi có sự kiện cho biết dữ liệu không còn hợp lệ trước cả khi TTL kết thúc.

Ba cách xử lý phổ biến:

1. **Remove:** xóa entry khỏi cache. Lần đọc tiếp theo phải lấy lại từ nguồn.
2. **Mark stale:** giữ entry để quan sát hoặc phục vụ theo chính sách stale-while-revalidate, nhưng không coi entry là fresh.
3. **Version/generation change:** tăng version hoặc generation của nguồn; entry chỉ hợp lệ nếu version khớp với version hiện hành.

Ví dụ một cache có thể lưu version:

```java
import java.time.Instant;

public record VersionedValue<V>(V value, long version, Instant expiresAt) {}

public boolean isUsable(
        VersionedValue<?> entry,
        long currentVersion,
        Instant now) {
    return entry != null
            && entry.version() == currentVersion
            && now.isBefore(entry.expiresAt());
}
```

Version giúp phát hiện entry cũ ngay cả khi TTL chưa hết. Đây là điều quan trọng khi quản lý quyền truy cập, cấu hình có version hoặc metadata thay đổi theo release.

Không phải mọi nguồn đều có version tăng dần. Có thể dùng ETag, revision, generation id, sequence number hoặc token version do hệ thống nguồn cung cấp. Nếu không có version, cần refresh snapshot hoặc invalidate toàn bộ cache liên quan sau restore.

## 9. Sự kiện invalidation có thể bị bỏ lỡ trong thời gian checkpoint

Nhiều hệ thống phát invalidation qua message broker, pub/sub hoặc event stream. Khi ứng dụng bị checkpoint, consumer thread có thể dừng; các sự kiện phát ra trong khoảng đó có thể không được xử lý ngay. Tùy cơ chế broker, message có thể được giữ lại, hết retention, bị ack trước checkpoint hoặc không được replay nếu offset đã tiến quá xa.

Không nên giả định listener trong heap sẽ tự nhận đầy đủ các sự kiện đã phát khi tiến trình không hoạt động.

Các chiến lược khôi phục:

- **Replay event bền vững:** lưu offset/sequence và đọc lại tất cả sự kiện từ sau watermark đã xử lý.
- **Refresh snapshot:** lấy snapshot mới nhất từ nguồn có thẩm quyền sau restore, sau đó tiếp tục nhận event.
- **Invalidate toàn bộ cache cục bộ:** phù hợp khi cache có thể nạp lại với chi phí chấp nhận được.
- **Version check on read:** so sánh version của entry với version hiện tại từ nguồn hoặc một metadata service.
- **Generation switch:** tăng generation của cache khi restore; entry thuộc generation cũ không được trả ra.

Khi dùng event stream, cần xử lý race giữa việc lấy snapshot và subscribe. Một cách là lấy watermark từ source, đăng ký consumer từ watermark đó, sau đó lấy snapshot tương ứng và áp dụng event theo sequence. Một cách khác là subscribe trước, buffer event, lấy snapshot có version rõ ràng rồi áp dụng event mới hơn snapshot. Thiết kế cụ thể phụ thuộc khả năng của event platform; mục tiêu là không bỏ sót thay đổi xảy ra giữa hai bước.

## 10. Xóa cache sau restore hay refresh từng phần?

Không có một chiến lược chung cho mọi cache. Chọn dựa trên tính chất dữ liệu, chi phí nạp lại và hậu quả nếu dữ liệu cũ được sử dụng.

| Loại dữ liệu | Chiến lược thường phù hợp | Lý do |
| --- | --- | --- |
| Cache quyền, policy và trạng thái thu hồi | Invalidate hoặc xác minh version trước khi cho phép hành động | Dữ liệu cũ có thể gây truy cập trái phép. |
| Credential, access token, signing key | Đọc lại nguồn có thẩm quyền và kiểm tra expiry/revocation | Không được kéo dài hiệu lực secret cũ. |
| DNS/service discovery | Refresh endpoint hoặc để client phân giải lại theo policy hiện tại | IP và instance có thể thay đổi. |
| Cache cấu hình có version | Nạp snapshot mới hoặc so sánh generation | Cần bảo đảm mọi instance dùng cấu hình tương thích. |
| Cache dữ liệu tham khảo có thể stale ngắn | Soft TTL và refresh nền nếu chính sách cho phép | Có thể cân bằng độ trễ và tính mới. |
| Cache kết quả tính toán thuần, không phụ thuộc thời gian/nguồn thay đổi | Có thể giữ nếu dữ liệu đầu vào/version còn hợp lệ | Không cần xóa chỉ vì đã restore. |

Với cache lớn, có thể refresh từng phần theo key hoặc partition. Nhưng trước khi mở traffic, cần xác định nhóm dữ liệu nào bắt buộc phải fresh và nhóm nào được phép stale trong một khoảng thời gian cụ thể.

## 11. Stale-while-revalidate và stale-if-error

Một số cache cho phép tiếp tục trả dữ liệu cũ trong khi làm mới (`stale-while-revalidate`) hoặc tiếp tục trả dữ liệu cũ khi source tạm thời lỗi (`stale-if-error`). Các chiến lược này có thể cải thiện availability nhưng phải có giới hạn rõ ràng.

Nên xác định:

- Soft TTL: khi nào bắt đầu refresh.
- Hard TTL: thời điểm tuyệt đối không còn được phép phục vụ entry.
- Max stale age: dữ liệu được phép cũ tối đa bao lâu, nếu có.
- Loại dữ liệu được phép stale: ví dụ danh mục tham khảo có thể chấp nhận, quyền truy cập thì không.
- Hành vi khi refresh thất bại: trả stale, trả lỗi, hoặc chuyển ứng dụng sang `NOT_READY`.

Không dùng stale-while-revalidate cho credential đã hết hạn, quyền đã bị thu hồi, lease độc quyền hoặc dữ liệu có yêu cầu nhất quán mạnh. Sau restore, nếu chưa xác minh được policy hoặc version hiện hành, cần từ chối thao tác nhạy cảm thay vì dùng dữ liệu cũ.

## 12. Lease, lock phân tán và fencing token

Lease là quyền sử dụng tài nguyên trong một khoảng thời gian. Một tiến trình có thể giữ lease trước checkpoint nhưng lease đã hết hạn trong lúc nó tạm dừng. Trong thời gian đó, hệ thống điều phối có thể cấp lease cho một tiến trình khác.

Sau restore, tiến trình cũ không được giả định nó vẫn sở hữu lease. Cần xác minh hoặc xin lease mới trước khi tiếp tục thao tác có tác động.

Với lock phân tán, chỉ kiểm tra thời gian hết hạn ở client chưa đủ. Một tiến trình cũ có thể thức dậy sau khi lease hết hạn và tiếp tục ghi dữ liệu. **Fencing token** giúp bảo vệ tài nguyên: mỗi lần cấp lease mới, hệ thống phát một token/sequence tăng dần; storage hoặc service đích từ chối thao tác mang token cũ hơn token đã chấp nhận.

Ví dụ logic:

```text
Instance A nhận lease với fencing token 41
          |
          v
       Checkpoint
          |
          v
Lease A hết hạn; Instance B nhận token 42
          |
          v
Instance A restore và cố ghi với token 41
          |
          v
Storage từ chối token 41 vì token 42 đã được chấp nhận
```

Fencing token phải được kiểm tra tại hệ thống thực sự bảo vệ dữ liệu, không chỉ ở client. Nếu chỉ kiểm tra ở process cũ, một request đã gửi hoặc một tác vụ nền còn chạy có thể vượt qua kiểm tra cục bộ.

## 13. Lập lịch refresh và timer sau restore

Một scheduled task được tạo trước checkpoint có thể đang chờ đến giờ refresh hoặc đang ở giữa một lần refresh. Khi process bị checkpoint, không nên giả định scheduler tiếp tục chạy đúng lịch trong thời gian ứng dụng tạm dừng.

Trước checkpoint:

- Dừng tạo công việc refresh mới.
- Chờ hoặc hủy tác vụ refresh đang chạy theo deadline.
- Ghi lại version/expiry cần thiết, không dựa riêng vào trạng thái timer trong heap.

Sau restore:

- Tính lại thời điểm hiện tại và xác định những entry đã hết hạn.
- Refresh ngay các dữ liệu bắt buộc phải fresh.
- Tạo lại lịch refresh dựa trên `expiresAt` hoặc policy hiện hành.
- Chỉ mở traffic khi dữ liệu/credential quan trọng đã được xác minh.

Nếu một task đã quá hạn khi restore, thường cần chạy refresh ngay hoặc chuyển trạng thái sang `NOT_READY`; không nên đơn giản đặt lịch mới từ thời điểm restore rồi vô tình kéo dài hiệu lực dữ liệu cũ.

## 14. Ví dụ Resource vô hiệu hóa cache sau restore

Ví dụ dưới đây minh họa một Resource giữ cache cục bộ. Trước checkpoint, nó dừng refresh nền và đợi tác vụ đang chạy kết thúc. Sau restore, nó xóa cache và nạp snapshot mới từ nguồn có thẩm quyền trước khi mở nhận request.

```java
import org.crac.Context;
import org.crac.Resource;

public final class CacheResource implements Resource {
    private final LocalCache cache;
    private final SnapshotProvider snapshotProvider;
    private final RefreshScheduler refreshScheduler;

    public CacheResource(
            LocalCache cache,
            SnapshotProvider snapshotProvider,
            RefreshScheduler refreshScheduler) {
        this.cache = cache;
        this.snapshotProvider = snapshotProvider;
        this.refreshScheduler = refreshScheduler;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        refreshScheduler.stopAcceptingRefreshes();
        refreshScheduler.awaitCurrentRefreshWithTimeout();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        cache.invalidateAll();
        CacheSnapshot snapshot = snapshotProvider.fetchCurrentSnapshot();
        cache.load(snapshot);
        refreshScheduler.startFrom(snapshot.nextRefreshAt());
    }
}
```

`LocalCache`, `SnapshotProvider`, `RefreshScheduler` và `CacheSnapshot` là abstraction của ứng dụng. Trong triển khai thực tế, `fetchCurrentSnapshot()` cần timeout/retry có giới hạn, snapshot cần version hoặc watermark, và `load()` phải hoàn tất trước khi traffic được mở. Nếu nguồn không truy cập được, callback nên báo lỗi hoặc component giữ `NOT_READY` theo chính sách, thay vì âm thầm giữ cache cũ.

Nếu checkpoint bị abort sau khi `beforeCheckpoint` đã dừng scheduler, process ban đầu có thể tiếp tục mà không đi qua `afterRestore`. Lifecycle coordinator cần có nhánh rollback/resume scheduler cho trường hợp abort, hoặc bảo đảm ứng dụng giữ `NOT_READY` cho đến khi lịch refresh được khôi phục. Không dùng `afterRestore` như callback rollback cho checkpoint thất bại.

Với cache không thể xóa toàn bộ vì kích thước lớn, có thể tăng generation và chỉ nạp lại partition cần thiết. Tuy nhiên, mọi lần đọc phải kiểm tra generation/version để tránh trả entry cũ.

## 15. Tránh ghi đè dữ liệu mới bằng kết quả refresh cũ

Một race condition có thể xảy ra khi refresh bắt đầu trước checkpoint hoặc trước invalidation, nhưng hoàn tất sau đó. Kết quả cũ có thể ghi đè dữ liệu mới.

Ví dụ:

1. Refresh A đọc version 10.
2. Nguồn cập nhật thành version 11 và phát invalidation.
3. Refresh B đọc version 11 và ghi vào cache.
4. Refresh A hoàn tất muộn và ghi version 10 đè lên version 11.

Để tránh, cache nên chỉ chấp nhận kết quả có version mới hơn hoặc dùng compare-and-set theo generation. Có thể hủy task refresh trước checkpoint và drain trước khi đóng resource; nhưng vẫn nên có version guard vì cancellation không bảo đảm task đã dừng ngay.

Ví dụ:

```java
public void putIfNewer(CacheSnapshot incoming) {
    current.updateAndGet(existing -> {
        if (existing == null || incoming.version() >= existing.version()) {
            return incoming;
        }
        return existing;
    });
}
```

Trong hệ thống phân tán, version phải có ý nghĩa theo source và không được tự tăng độc lập trên từng instance nếu cần so sánh toàn cục. Dùng revision, sequence hoặc generation do nguồn có thẩm quyền cấp.

## 16. Các lỗi thường gặp sau restore

| Hiện tượng | Nguyên nhân có thể gặp | Hướng xử lý |
| --- | --- | --- |
| Cache trả dữ liệu đã hết hạn | Entry vẫn còn trong heap và code chỉ kiểm tra null | Kiểm tra `expiresAt` ở thời điểm đọc; invalidate entry hết hạn. |
| Token bị từ chối dù object vẫn tồn tại | Token hết TTL hoặc bị thu hồi khi process checkpoint | Xin token mới và kiểm tra expiry/revocation trước khi dùng. |
| Quyền truy cập cũ vẫn được áp dụng | Invalidation event bị bỏ lỡ hoặc cache policy không kiểm tra version | Replay event, refresh policy snapshot hoặc fail closed. |
| Refresh nền không chạy sau restore | Scheduler/task state không được khởi động lại đúng cách | Rebuild lịch từ expiry metadata và chạy refresh quá hạn ngay. |
| Cache bị làm mới rồi lại trở thành cũ | Task refresh cũ ghi đè version mới | Dùng version/generation guard và hủy/drain task cũ. |
| Lease cũ tiếp tục ghi dữ liệu | Process restore không xác minh lease hoặc storage không kiểm tra fencing token | Xin lease mới và kiểm tra fencing token ở resource đích. |
| Cache chỉ stale ở một số instance | Invalidation stream, offset hoặc snapshot giữa instance không đồng nhất | Reconcile watermark/version và theo dõi lag của consumer. |
| Ứng dụng không thể restore vì source refresh tạm thời lỗi | Callback phụ thuộc nguồn bên ngoài không có retry/deadline rõ ràng | Dùng timeout/backoff có giới hạn và giữ component `NOT_READY` khi chưa xác minh được dữ liệu bắt buộc. |

## 17. Quan sát TTL và invalidation

Nên ghi nhận metadata để biết vì sao một entry được dùng hoặc bị từ chối:

- Cache key hoặc định danh đã được ẩn/mã hóa phù hợp; tránh log dữ liệu nhạy cảm.
- `fetchedAt`, `expiresAt`, TTL còn lại và thời điểm refresh gần nhất.
- Source version, generation hoặc event sequence.
- Thời điểm checkpoint/restore và restore attempt id.
- Số entry hết hạn, số entry invalidated và số entry được refresh sau restore.
- Invalidation event offset/watermark và độ trễ consumer.
- Số lần refresh thất bại, timeout và retry.
- Số lần đọc bị từ chối do stale/expired data.
- Trạng thái readiness trong khi cache bắt buộc đang được làm mới.

Metric hữu ích gồm cache hit/miss, expired-entry count, stale-served count (nếu policy cho phép), refresh duration, refresh failure, invalidation lag và version mismatch. Tránh dùng cache key hoặc user id làm metric label có cardinality cao.

## 18. Kiểm thử TTL và invalidation qua checkpoint–restore

Một kiểm thử tích hợp nên mô phỏng thời gian trôi qua và thay đổi dữ liệu bên ngoài:

1. Nạp một cache entry với TTL đã biết và ghi lại `fetchedAt`, `expiresAt`, version.
2. Tạo checkpoint khi entry còn hạn.
3. Trong lúc process ở trạng thái checkpoint, chờ qua expiry hoặc cập nhật source version và phát invalidation event.
4. Restore ứng dụng.
5. Xác nhận entry hết hạn không được trả ra và cache được refresh hoặc invalidate.
6. Xác nhận invalidation event bị phát trong thời gian checkpoint được replay hoặc được bao phủ bởi snapshot mới.
7. Kiểm tra task refresh cũ không thể ghi đè dữ liệu có version mới hơn.
8. Với lease, xác nhận process cũ không thể ghi sau khi lease được cấp cho instance khác; kiểm tra fencing token tại storage/service đích.
9. Kiểm tra ứng dụng không mở traffic nhạy cảm trước khi dữ liệu bắt buộc đã được xác minh.

Các trường hợp bổ sung:

- Restore trước và sau mốc hard TTL.
- Đồng hồ host lệch hoặc được điều chỉnh.
- Nguồn thời gian/token issuer và local clock có sai lệch.
- Invalidation event bị trễ, trùng lặp hoặc đến sai thứ tự.
- Secret/config version đổi nhiều lần trong khi checkpoint.
- Secret provider hoặc source snapshot tạm thời không truy cập được.
- Scheduler có task quá hạn tại thời điểm restore.
- Refresh cũ hoàn tất sau khi refresh mới đã ghi cache.
- Cache cho phép stale-while-revalidate nhưng không cho phép stale sau hard expiry.

Nên inject `Clock` để kiểm thử expiry logic bằng thời gian giả lập thay vì chờ thật nhiều phút. Tuy nhiên, việc xác nhận CRaC callback, scheduler và event replay vẫn cần kiểm thử tích hợp trên runtime và môi trường triển khai.

## 19. Checklist triển khai

- [ ] Mỗi loại dữ liệu có chính sách TTL/hard expiry rõ ràng.
- [ ] Biết TTL bắt đầu từ lúc source tạo, lúc client nhận hay lúc cache nạp dữ liệu.
- [ ] Dùng `Instant`/timestamp cho expiry có ý nghĩa bên ngoài; dùng `nanoTime` cho elapsed time trong runtime hiện tại.
- [ ] Không dựa vào deadline monotonic đã lưu trong heap như nguồn sự thật qua restore.
- [ ] Sau restore, tính lại deadline hoặc invalidate cache cần làm mới.
- [ ] Kiểm tra expiry ở thời điểm sử dụng, không chỉ khi chạy cleanup nền.
- [ ] Dữ liệu quyền, credential, token và lease có hard expiry/revocation check.
- [ ] Có version/generation hoặc cơ chế snapshot để phát hiện invalidation bị bỏ lỡ.
- [ ] Replay event từ watermark bền vững hoặc refresh snapshot sau restore.
- [ ] Xử lý race giữa subscribe và snapshot để không bỏ sót event.
- [ ] Không để refresh cũ ghi đè dữ liệu mới hơn.
- [ ] Hủy/drain scheduled task trước checkpoint và xây dựng lại lịch sau restore.
- [ ] Stale-while-revalidate chỉ áp dụng cho dữ liệu được phép stale và có hard TTL.
- [ ] Lease phân tán được xác minh lại; thao tác ghi được bảo vệ bằng fencing token khi cần.
- [ ] Dùng timeout/deadline cho việc refresh dữ liệu sau restore.
- [ ] Chỉ mở traffic khi dữ liệu bắt buộc đã fresh hoặc được xác minh hợp lệ.
- [ ] Có metric/log cho expiry, invalidation lag, version mismatch và refresh failure.
- [ ] Đã kiểm thử TTL hết hạn và invalidation xảy ra trong thời gian checkpoint.

## 20. Kết luận

TTL xác định thời gian dữ liệu được phép sử dụng; expiry là mốc mà dữ liệu không còn hợp lệ; invalidation xử lý trường hợp dữ liệu phải bị loại bỏ hoặc đánh dấu stale trước khi TTL kết thúc. Trong CRaC, trạng thái cache được khôi phục từ một thời điểm cũ trong khi đồng hồ, secret, quyền, lease và dữ liệu nguồn vẫn tiếp tục thay đổi.

Hãy lưu expiry có ý nghĩa tuyệt đối cho dữ liệu sống qua checkpoint, dùng đồng hồ monotonic cho deadline trong runtime, kiểm tra freshness khi đọc, và reconcile cache/version/event sau restore. Với credential, quyền và lease, cần fail closed khi chưa xác minh được trạng thái hiện hành. Với cache có thể refresh, hãy invalidate hoặc nạp snapshot mới, xây dựng lại scheduler và ngăn kết quả refresh cũ ghi đè dữ liệu mới. Nhờ đó, ứng dụng không nhầm dữ liệu còn nằm trong heap với dữ liệu vẫn còn hợp lệ.
