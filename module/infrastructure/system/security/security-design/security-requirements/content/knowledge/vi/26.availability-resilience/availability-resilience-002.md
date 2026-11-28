# Graceful degradation

## 1. Giữ được điều gì khi một phần hệ thống không hoạt động?

Một nền tảng học tập có trang khóa học, tiến độ cá nhân, gợi ý nội dung và chức năng nộp bài. Khi dịch vụ gợi ý timeout, người học vẫn nên xem được nội dung được phép truy cập. Tuy nhiên, khi không thể xác minh quyền xem tiến độ cá nhân, hệ thống không được mở dữ liệu đó cho mọi người chỉ để trang tiếp tục trả thành công.

**Graceful degradation** là cách hệ thống giảm một phần chức năng, độ mới hoặc chất lượng phục vụ theo một hợp đồng đã thiết kế khi gặp lỗi hay thiếu tài nguyên, trong khi vẫn giữ các điều kiện bắt buộc của chức năng còn hoạt động.

Điều kiện bắt buộc bao gồm tính đúng nghiệp vụ và ranh giới bảo mật. Một fallback nhanh nhưng làm lộ dữ liệu, bỏ xác thực hoặc báo giao dịch thành công giả không phải một phương án suy giảm chấp nhận được.

Trong chương Availability và resilience, yêu cầu cần chỉ rõ:

- Chức năng tối thiểu nào còn được cung cấp.
- Điều kiện nào cho phép dùng fallback hoặc dữ liệu cũ.
- Hành động nào phải dừng vì không còn đủ căn cứ an toàn.
- Hạn mức tài nguyên, hàng đợi và retry khi hệ thống suy giảm.
- Cách thể hiện trạng thái và mở lại chức năng khi phục hồi.

Sau bài này, người học có thể chuyển các mục tiêu sẵn sàng và an toàn thông tin thành ma trận suy giảm, yêu cầu đo được và ca kiểm thử có bằng chứng.

## 2. Phân biệt cơ chế chịu lỗi và chính sách suy giảm

### 2.1. Cơ chế không tự quyết định hành vi đúng

| Cơ chế | Vai trò | Điều chưa tự quyết định |
|---|---|---|
| Timeout | Giới hạn thời gian chờ | Có được tiếp tục, dùng cache hoặc thực hiện lại không |
| Circuit breaker | Hạn chế tiếp tục gọi dependency đang lỗi | Fallback nào bảo toàn quyền và dữ liệu |
| Bulkhead | Cô lập tài nguyên giữa nhóm tải hoặc chức năng | Chức năng nào nên được ưu tiên |
| Retry | Thử lại trong điều kiện xác định | Thao tác có thể thực hiện lặp an toàn không |
| Cache | Cung cấp dữ liệu từ bản đã lưu | Bản đó còn đúng scope, quyền và độ mới không |
| Queue | Tách thời điểm nhận và xử lý | Dữ liệu đã bền vững, còn quyền và còn thời hạn không |
| Feature flag | Điều khiển việc bật chức năng | Người nào được thay đổi và trạng thái nào được phép |

Graceful degradation là hợp đồng sử dụng những cơ chế đó để giữ phần phục vụ có giá trị mà không làm mất bất biến. Thêm một circuit breaker nhưng fallback trả dữ liệu của tenant khác vẫn là một thiết kế sai.

### 2.2. Quan hệ với fail closed

Một hành động cần quyết định phân quyền hợp lệ phải dừng nếu không thiết lập được điều kiện đó. Trong cùng thời gian, chức năng công khai hoặc chức năng có căn cứ độc lập vẫn có thể hoạt động.

Hai lựa chọn không mâu thuẫn: đóng hành động chưa đủ điều kiện và duy trì những hành động đã đủ điều kiện chính là một cách suy giảm theo phạm vi.

Không gọi toàn bộ dependency bảo mật là “optional” để tăng uptime. Nếu một kiểm tra là điều kiện của hành động, sự cố không tự làm điều kiện đó biến mất.

### 2.3. Chỉ đọc không tự đồng nghĩa an toàn

Xem điểm, đọc hồ sơ, tải file và export đều có thể làm lộ dữ liệu. Khi quyền đọc chưa được xác lập, chuyển hệ thống sang read-only chưa giải quyết được vấn đề.

Chế độ read-only cần định nghĩa hành động nào còn được phép, dữ liệu nào được phục vụ, độ mới nào được chấp nhận và các đường ghi nào thực sự bị chặn ở backend.

## 3. Xác định chức năng và bất biến theo hành động

### 3.1. Bắt đầu từ mục tiêu người dùng

Không chỉ lập danh sách dependency rồi gắn nhãn quan trọng hay không quan trọng. Một dependency có thể bắt buộc với hành động này nhưng không liên quan đến hành động khác.

Ví dụ, kho danh tính có thể cần cho việc thiết lập một phiên mới. Một trang giới thiệu khóa học công khai có thể không cần truy vấn kho đó cho mỗi request. Khả năng phục vụ phiên đã có lại phụ thuộc hợp đồng xác minh và thu hồi riêng, không thể suy từ hai trường hợp trên.

### 3.2. Bất biến minh họa

```text
I-01: Dữ liệu cá nhân chỉ được phát hành khi có quyền hợp lệ
      cho đúng chủ thể, tenant, tài nguyên và hành động.

I-02: Dữ liệu bắt buộc mã hóa không được chuyển sang bản rõ
      vì dịch vụ khóa hoặc pipeline đang lỗi.

I-03: Không báo một thao tác ghi đã hoàn tất khi chỉ mới tiếp nhận,
      hoặc khi kết quả thực tế còn chưa xác định.

I-04: Điều kiện audit bắt buộc của hành động phải được đáp ứng
      bởi mức bền vững mà policy đã chốt.

I-05: Suy giảm không được chuyển tải thành tài nguyên vô hạn
      hoặc làm một tenant chiếm hết năng lực phục vụ.
```

Các bất biến là đầu vào cho thiết kế và kiểm thử. Chúng không tự chỉ ra một công nghệ triển khai cụ thể.

### 3.3. Phân loại lỗi theo ảnh hưởng

Lỗi thiếu gợi ý có thể chỉ làm giảm chất lượng giao diện. Lỗi không biết người dùng nào có quyền xem bài nộp ảnh hưởng trực tiếp tới bảo mật. Lỗi không xác định bài nộp đã được lưu hay chưa ảnh hưởng tới tính đúng của kết quả.

Không dùng một fallback chung “trả object rỗng và status thành công” cho mọi loại. Mỗi lỗi cần hành vi phù hợp ngữ nghĩa của hành động.

## 4. Lập ma trận graceful degradation

Một ma trận cho nền tảng học tập giả định:

| Hành động | Điều kiện bị lỗi | Phương án có thể chấp nhận | Điều không được làm |
|---|---|---|---|
| Xem trang khóa học | Gợi ý nội dung không khả dụng | Bỏ phần gợi ý, giữ nội dung đã đủ điều kiện truy cập | Chờ vô hạn khiến trang chính bị nghẽn |
| Xem catalog công khai | Nguồn catalog tạm lỗi | Dùng snapshot công khai còn trong policy độ mới | Trộn bản cache riêng tư vào snapshot công khai |
| Xem tiến độ cá nhân | Nguồn đọc chính lỗi | Dùng cache đúng scope, quyền và độ mới được cho phép | Dùng cache chỉ theo course ID mà bỏ subject hoặc tenant |
| Xem dữ liệu riêng tư | Không xác lập được quyền | Chặn phần riêng tư; giữ phần có căn cứ độc lập | Dùng role mặc định rộng hoặc bỏ bộ lọc tenant |
| Lưu tiến độ | Kho ghi không khả dụng | Từ chối có kiểm soát hoặc tiếp nhận bền vững theo hợp đồng riêng | Báo đã đồng bộ khi dữ liệu chỉ ở bộ nhớ |
| Nộp bài | Trạng thái xử lý chưa xác định | Hiển thị pending hoặc unknown đúng nghĩa và đối soát | Tự gửi lại mù hoặc báo chắc chắn chưa nộp |
| Tạo dữ liệu bắt buộc mã hóa | Không thiết lập được điều kiện khóa | Dừng hành động phụ thuộc | Lưu bản rõ để xử lý sau |
| Export cần audit trước khi cấp dữ liệu | Không có nơi audit bền vững được chấp nhận | Không phát hành dữ liệu | Bỏ audit và gửi trace vào response để bù |

Mỗi hàng cần có chủ sở hữu, phạm vi triển khai và bằng chứng nghiệm thu. Không mặc định các phương án trong bảng đều phù hợp với mọi sản phẩm.

### 4.1. Tách trạng thái chức năng khỏi trạng thái cả service

Một service có thể vẫn phục vụ nội dung cốt lõi khi một thành phần phụ lỗi. Nếu health check coi mọi lỗi gợi ý là service chết rồi loại toàn bộ instance, thiết kế có thể làm mất phần chức năng vẫn phục vụ được.

Phân biệt tín hiệu tiến trình còn hoạt động, khả năng nhận tải và khả năng của từng chức năng. Không dùng restart liên tục như cách chữa một dependency ngoài tiến trình đang ngừng hoạt động.

Đồng thời, không báo mọi chức năng sẵn sàng chỉ vì một endpoint health trả thành công. Ma trận phải khớp hành vi thực của route và worker.

## 5. Deadline, cô lập tài nguyên và tải trong chế độ suy giảm

### 5.1. Ngân sách thời gian theo đường xử lý

Đặt deadline cho request và ngân sách cho những dependency cần thiết. Thành phần phụ không nên dùng hết thời gian khiến phần cốt lõi không kịp trả kết quả.

Nếu các bước chạy nối tiếp, cần tính ngân sách tổng. Nếu chạy song song, vẫn cần giới hạn chờ và tài nguyên; gọi song song không làm request có thời gian vô hạn hoặc không còn rủi ro cạn connection.

Không coi timeout của người gọi là xác nhận thao tác ở dependency đã bị hủy. Worker hoặc hệ thống từ xa có thể vẫn đang thực hiện, đặc biệt với thao tác ghi.

### 5.2. Retry có ngân sách và đúng ngữ nghĩa

Nhiều tầng retry có thể nhân số lần gọi. Với fixture ba tầng cùng tối đa ba lần thử, một đường lỗi có thể tạo tới 27 lần thử ở tầng sâu nếu thiết kế cho phép toàn bộ chuỗi lặp như vậy.

Chốt tầng nào chịu trách nhiệm retry, giới hạn lần thử, deadline và điều kiện áp dụng. Retry thao tác ghi cần cơ chế tránh tác động lặp và xử lý kết quả chưa xác định.

Khi lỗi quá tải, retry đồng loạt có thể làm phục hồi chậm hơn. Backoff và phân tán thời điểm thử lại là cơ chế hỗ trợ; không thay thế hạn mức tổng và admission control.

### 5.3. Fallback cũng có thể bị quá tải

Khi nguồn chính lỗi, tải có thể dồn vào cache, kho snapshot hoặc queue. Những thành phần đó phải có dung lượng, connection và quyền phù hợp với tải suy giảm dự kiến.

Dùng bulkhead, quota và giới hạn backlog để giữ chức năng cốt lõi. Không để một job nặng hoặc một tenant lớn chiếm hết năng lực phục vụ các luồng khác.

Nếu không còn đủ tài nguyên cho mức tối thiểu đã chốt, từ chối có kiểm soát theo hợp đồng tốt hơn giả nhận mọi công việc rồi mất dữ liệu hoặc cạn bộ nhớ.

## 6. Cache và dữ liệu cũ: độ mới không thay thế quyền

### 6.1. Điều kiện dùng một snapshot

Trước khi phục vụ cache, cần xác định:

- Dữ liệu thuộc đúng tenant, chủ thể, tài nguyên và loại kết quả.
- Nguồn tạo, tính toàn vẹn và phân loại dữ liệu phù hợp.
- Quyền phục vụ dữ liệu đã được xác lập theo policy hiện hành của luồng.
- Tuổi dữ liệu và version đáp ứng giới hạn được chấp nhận.
- Những thay đổi như xóa dữ liệu, thu hồi quyền hoặc đổi phạm vi được xử lý ra sao.

TTL của dữ liệu không phải TTL của quyền. Snapshot còn mới không chứng minh người đang yêu cầu vẫn được xem nó.

### 6.2. Cache riêng tư không được trở thành cache công khai

Khóa cache chỉ theo course ID có thể làm tiến độ của người trước xuất hiện cho người sau. Cần scope theo hợp đồng dữ liệu, không chỉ theo URL hoặc định danh tài nguyên chung.

Không dùng token hoặc password làm cache key để giải quyết scope. Dùng reference phù hợp từ context tin cậy và kiểm soát quyền truy cập cache.

Nếu không còn đủ thông tin để xác minh scope hoặc quyền, cache đó không phải một nguồn fallback hợp lệ cho dữ liệu được bảo vệ.

### 6.3. Giới hạn stale phải có ý nghĩa nghiệp vụ

Một bản catalog công khai có thể chấp nhận độ trễ khác với kết quả đánh giá, điều kiện truy cập hoặc dữ liệu đã được yêu cầu xóa. Không đặt một giới hạn stale chung cho mọi field.

Khi dùng dữ liệu chưa mới nhất, trình bày trạng thái đủ để người dùng quyết định theo chức năng, chẳng hạn mốc cập nhật. Không gắn nhãn “hiện tại” nếu hệ thống chỉ có snapshot cũ.

Không tự kéo dài tuổi hợp lệ sau mỗi lần nguồn chính lỗi. Stale-while-revalidate hoặc cơ chế tương tự vẫn cần giới hạn và điều kiện phục vụ rõ, đặc biệt với quyền và dữ liệu nhạy cảm.

## 7. Hàng đợi, pending và thao tác chưa xác định kết quả

### 7.1. Tiếp nhận không phải hoàn tất

Nếu hệ thống trả trạng thái đã tiếp nhận để xử lý sau, cần xác định dữ liệu đã được lưu ở mức bền vững nào, cách tra trạng thái và những điều kiện còn có thể làm công việc thất bại.

Một object trong bộ nhớ của request chưa đủ để cam kết sẽ đồng bộ sau. Không hiển thị “đã nộp thành công” nếu hợp đồng mới chỉ bảo đảm job được lưu để xử lý.

Có thể dùng những trạng thái như ACCEPTED, PROCESSING, COMPLETED, FAILED và UNKNOWN theo mô hình cụ thể. Người dùng không cần thấy thuật ngữ nội bộ, nhưng nội dung hiển thị phải giữ đúng sự thật của trạng thái.

### 7.2. Điều kiện cho enqueue an toàn

Cần chốt quyền tiếp nhận và quyền thực thi, phạm vi dữ liệu, dung lượng queue, thời hạn job, idempotency và cách xử lý khi quyền thay đổi.

Không dùng queue để bỏ qua xác thực hoặc biến thiếu tenant thành principal dịch vụ toàn quyền. Consumer cần mô hình ủy quyền rõ thay vì mặc định mọi message đều được chạy với quyền quản trị.

Nếu một yêu cầu chưa được phép thực hiện chỉ được lưu như ý định chờ xác minh, đó là một hành động riêng với dữ liệu và quyền riêng. Không coi một lệnh đã sẵn sàng chạy đặc quyền là “chỉ lưu tạm” để bỏ kiểm soát.

### 7.3. Timeout sau thao tác ghi

Một bài nộp có thể đã được lưu nhưng response bị mất. Trả lời chắc chắn “chưa nộp” hoặc tự gửi lại không kiểm soát có thể gây kết quả lặp hoặc mâu thuẫn.

Yêu cầu cần có định danh thao tác, cách đối soát và quy tắc thực hiện lại phù hợp. Idempotency key phải gắn đúng tenant, chủ thể và nội dung thao tác theo hợp đồng, không chỉ là một chuỗi toàn cục do client tự đặt.

Rollback cục bộ không tự thu hồi message, email hoặc lệnh đã gửi tới hệ thống khác. Nếu có cơ chế bù, nêu rõ nó sửa được điều gì và điều gì không thể thu hồi.

## 8. Không hạ mức kiểm soát bảo mật để giữ dịch vụ

### 8.1. Xác thực và phân quyền

Không kiểm tra được bằng chứng xác thực không cho phép chỉ đọc payload rồi tin nó. Không gọi được policy service không tự cho phép dùng ALLOW cũ vô thời hạn.

Căn cứ cache hoặc quyền giới hạn có thể được thiết kế cho trạng thái mất kết nối, nhưng phải có phạm vi, hiệu lực, thu hồi và nguồn tin cậy rõ. Đó là một chính sách trước sự cố, không phải nhánh chữa cháy tự cấp quyền.

### 8.2. Mã hóa và dữ liệu nhạy cảm

Lỗi lấy khóa không cho phép lưu dữ liệu bắt buộc mã hóa dưới dạng bản rõ. Một cache có dữ liệu đã giải mã cũng chỉ được sử dụng nếu đáp ứng policy dữ liệu và quyền liên quan, không phải vì “dữ liệu vốn đã ở bộ nhớ”.

Không chuyển payload nhạy cảm sang file tạm hoặc dead-letter queue rộng quyền để tránh mất request. Các nơi đó là bên nhận dữ liệu và cần hợp đồng bảo vệ riêng.

### 8.3. Audit và log chẩn đoán

Nếu audit bền vững là điều kiện của hành động, fallback phải đáp ứng mức bền vững được chấp nhận. Collector lỗi nhưng outbox bền vững còn hoạt động có thể khác hoàn toàn việc cả hai đều không ghi được.

Log chẩn đoán best effort không nhất thiết là điều kiện dừng nghiệp vụ. Phải phân biệt hai loại thay vì quy định mọi lỗi logging đều bỏ qua hoặc mọi lỗi logging đều tắt cả hệ thống.

Trong mọi trạng thái, response và log không được phát hành secret, raw exception hoặc PII ngoài mục đích. Chế độ suy giảm không phải ngoại lệ cho yêu cầu giảm dữ liệu.

### 8.4. Điều khiển chế độ suy giảm

Feature flag hoặc cấu hình fallback là bề mặt quản trị cần xác thực, phân quyền và audit phù hợp. Một tham số request không được tự bật đường bỏ kiểm tra quyền, quota hoặc mã hóa.

Ẩn nút trên UI chưa chặn endpoint hoặc consumer phía sau. Mọi hạn chế phải được thi hành tại ranh giới thực hiện hành động.

## 9. Ví dụ Java: chọn nguồn đọc mà không mở quyền

Ví dụ dùng Java 17 trở lên cho một màn hình riêng tư đã có hợp đồng quyền cụ thể. Verdict quyền và cache được tạo từ thành phần tin cậy cho đúng context; chúng không phải cờ do client gửi.

```java
import java.util.Objects;

public final class DegradedReadPlanner {
    private DegradedReadPlanner() {}

    public enum PermissionVerdict {
        ALLOWED,
        DENIED,
        INDETERMINATE
    }

    public enum CacheVerdict {
        USABLE,
        NOT_USABLE,
        UNKNOWN
    }

    public enum DataSource {
        LIVE,
        APPROVED_CACHE,
        NONE
    }

    public enum ServiceMode {
        NORMAL,
        DEGRADED,
        UNAVAILABLE
    }

    public enum Reason {
        NONE,
        OPTIONAL_COMPONENT_UNAVAILABLE,
        PRIMARY_READ_UNAVAILABLE,
        ACCESS_NOT_ESTABLISHED,
        NO_SAFE_DATA_SOURCE
    }

    public record Plan(
        DataSource source,
        boolean includeRecommendations,
        ServiceMode mode,
        Reason reason
    ) {}

    public static Plan choose(
        PermissionVerdict permission,
        boolean primaryReadReady,
        CacheVerdict cache,
        boolean recommendationsReady
    ) {
        Objects.requireNonNull(permission);
        Objects.requireNonNull(cache);

        if (permission != PermissionVerdict.ALLOWED) {
            return new Plan(
                DataSource.NONE, false, ServiceMode.UNAVAILABLE,
                Reason.ACCESS_NOT_ESTABLISHED
            );
        }
        if (primaryReadReady) {
            return new Plan(
                DataSource.LIVE,
                recommendationsReady,
                recommendationsReady
                    ? ServiceMode.NORMAL : ServiceMode.DEGRADED,
                recommendationsReady
                    ? Reason.NONE : Reason.OPTIONAL_COMPONENT_UNAVAILABLE
            );
        }
        if (cache == CacheVerdict.USABLE) {
            return new Plan(
                DataSource.APPROVED_CACHE, false, ServiceMode.DEGRADED,
                Reason.PRIMARY_READ_UNAVAILABLE
            );
        }
        return new Plan(
            DataSource.NONE, false, ServiceMode.UNAVAILABLE,
            Reason.NO_SAFE_DATA_SOURCE
        );
    }
}
```

Các lựa chọn có ý nghĩa trong mẫu:

- Chỉ ALLOWED mới cho chọn một nguồn dữ liệu riêng tư.
- Nguồn chính lỗi không làm UNKNOWN cache trở thành USABLE.
- Cache USABLE đã phải đáp ứng scope, quyền liên quan, độ mới và tính toàn vẹn theo hợp đồng.
- Khi đọc từ cache trong nhánh suy giảm này, hệ thống chủ động bỏ gợi ý để giữ ngân sách cho phần cốt lõi.
- Không có nguồn an toàn thì kết quả là UNAVAILABLE, không phải object thành công giả.

Planner không thực hiện xác thực, kiểm tra tenant, đọc cache hay áp deadline. Kiểu enum không tự chứng minh verdict đúng; chúng phải đến từ các kiểm soát đã xác minh cho đúng người và tài nguyên.

`primaryReadReady` là một quan sát có thể cũ ngay sau khi chọn plan. Nếu thao tác thực tế vẫn lỗi, runtime phải giữ hợp đồng fallback và bất biến, không coi plan là bảo đảm rằng lời gọi sẽ thành công.

Mỗi component được trả ra vẫn phải có quyền riêng nếu hợp đồng yêu cầu. Việc đủ quyền xem phần cốt lõi không tự cho quyền mọi nội dung gợi ý hoặc phần bổ sung.

## 10. Hợp đồng API và trải nghiệm khi suy giảm

### 10.1. Trạng thái phải giúp người dùng quyết định đúng

Ví dụ nội dung phù hợp theo tình huống:

- Gợi ý lỗi: “Chưa tải được gợi ý. Bạn vẫn có thể xem nội dung khóa học.”
- Dữ liệu từ snapshot: nêu mốc cập nhật và giới hạn liên quan theo chức năng.
- Job đã được tiếp nhận bền vững: “Đã tiếp nhận bài nộp, đang chờ xử lý.”
- Kết quả thao tác ghi chưa xác định: hướng dẫn kiểm tra trạng thái trước khi thử lại.
- Không có căn cứ phục vụ dữ liệu: thông báo lỗi theo hợp đồng, không phát hành dữ liệu dự phòng ngoài quyền.

Không đưa hostname, tên exception hoặc chi tiết circuit breaker vào thông báo chỉ để giải thích trạng thái. Giữ code công khai ổn định và reference hỗ trợ không cấp quyền khi phù hợp.

### 10.2. HTTP status không thay toàn bộ ngữ nghĩa

Phản hồi có phần optional bị thiếu có thể vẫn là kết quả hợp lệ nếu API đã đặc tả rõ. Thao tác chỉ mới được tiếp nhận phải phân biệt với hoàn tất. Lỗi quyền và lỗi thiếu dependency cũng cần hành vi theo hợp đồng của luồng.

Không biến tất cả thành status thành công để giữ dashboard xanh. Cũng không đổi mọi lỗi của một thành phần phụ thành lỗi của toàn bộ trang nếu phần cốt lõi vẫn đáp ứng hợp đồng.

Client cần biết field vắng mặt là không có dữ liệu, chưa tải được hay bị hạn chế theo quyền nếu sự phân biệt đó được phép công khai và cần cho chức năng. Không dùng một object rỗng không có ngữ nghĩa cho mọi trạng thái.

### 10.3. Dữ liệu đã gửi không thể được thu hồi bằng lỗi sau đó

Với stream hoặc tải file, kiểm soát cần thiết phải có trước khi phát hành byte được bảo vệ. Lỗi xảy ra sau đó không cho phép nối trace hoặc nội dung ngoài hợp đồng vào luồng.

Không phát hành trước rồi dự định chặn ở cuối nếu bước kiểm tra quyền thất bại. Fallback là lựa chọn nguồn và hành vi hợp lệ, không phải cách sửa việc dữ liệu đã đi sai ranh giới.

## 11. Chuyển trạng thái và phục hồi có kiểm soát

### 11.1. Một mô hình trạng thái minh họa

```text
NORMAL
  -> DEGRADED khi thiếu một số khả năng nhưng vẫn đủ điều kiện tối thiểu
  -> RESTRICTED khi một hành động không còn đủ điều kiện bắt buộc
  -> RECOVERING khi nguồn đã trở lại nhưng còn cần xác minh và mở tải
  -> NORMAL sau khi các điều kiện phục hồi đạt hợp đồng
```

Các trạng thái có thể áp dụng cho từng chức năng hoặc nhóm hành động. Không nhất thiết toàn service chuyển cùng một lúc.

### 11.2. Tránh dao động liên tục

Một lần probe thành công chưa chứng minh dependency đã ổn định. Có thể cần cửa sổ quan sát, số điều kiện đạt hoặc cách mở tải tăng dần theo policy của hệ thống.

Chốt điều kiện vào và ra, thời gian, người hoặc cơ chế có quyền điều khiển. Dùng ngưỡng hoặc khoảng giữ trạng thái phù hợp để tránh bật tắt liên tục khi nguồn chập chờn.

Không giữ một fallback quá lâu sau khi điều kiện của nó đã hết hiệu lực chỉ để tránh đổi trạng thái. Giới hạn dữ liệu và quyền vẫn phải được thi hành trong mọi chế độ.

### 11.3. Phục hồi không chỉ là kết nối lại

Cần kiểm tra revision cấu hình, policy hiệu lực, cache, quyền đã thu hồi và job tồn đọng. Một cache bị stale hoặc một job không còn quyền không được chạy chỉ vì nguồn chính vừa khỏe lại.

Xả backlog có giới hạn để không làm nguồn vừa phục hồi quá tải. Đối soát thao tác UNKNOWN trước khi thực hiện lại những lệnh có thể tạo tác động lặp.

Nếu có thay đổi dữ liệu xung đột trong thời gian gián đoạn, cách hòa giải cần được đặc tả theo nghiệp vụ. Không mặc định bản đến cuối luôn đúng hoặc dữ liệu offline luôn thắng.

## 12. Bộ yêu cầu bảo mật và sẵn sàng có thể nghiệm thu

Các mã sau là mẫu cho dự án, chưa phải bằng chứng một sản phẩm đã đáp ứng.

| ID | Yêu cầu | Bằng chứng |
|---|---|---|
| GD-01 | Mỗi hành động có mức phục vụ tối thiểu, dependency và bất biến bắt buộc | Ma trận hành động và chủ sở hữu |
| GD-02 | Fallback không mở rộng quyền, bỏ tenant hoặc phát hành dữ liệu ngoài scope | Ca mất quyền, sai tenant và context thiếu |
| GD-03 | Cache chỉ được dùng khi nguồn, scope, độ mới, tính toàn vẹn và điều kiện quyền đáp ứng policy | Fixture cache và thay đổi quyền |
| GD-04 | Deadline, retry, connection, queue và tải mỗi nhóm có giới hạn rõ | Cấu hình hiệu lực cùng thử quá tải có kiểm soát |
| GD-05 | Thành phần optional không chiếm hết tài nguyên của chức năng cốt lõi | Ca dependency chậm và bulkhead |
| GD-06 | Tiếp nhận bền vững, hoàn tất và UNKNOWN được phân biệt ở trạng thái cùng phản hồi | Ca queue, timeout sau commit và đối soát |
| GD-07 | Enqueue, thực thi và replay giữ quyền cùng scope theo thời điểm policy yêu cầu | Thử job cũ, quyền đổi và principal sai |
| GD-08 | Không hạ điều kiện mã hóa hoặc audit bắt buộc khi dependency lỗi | Ca nguồn khóa và nơi audit bền vững không khả dụng |
| GD-09 | UI, API và worker cùng thi hành hạn chế; flag suy giảm chỉ được điều khiển đúng quyền | Thử gọi trực tiếp endpoint và thay đổi cấu hình |
| GD-10 | Trạng thái suy giảm, nguồn dữ liệu và pending được thể hiện đúng hợp đồng công khai | Kiểm tra response, client và luồng thử lại |
| GD-11 | Phục hồi có điều kiện kiểm tra, giới hạn mở tải và xử lý backlog rõ | Diễn tập nguồn chập chờn và khôi phục |
| GD-12 | Log, metric và lỗi suy giảm không phát hành secret hoặc PII ngoài mục đích | Canary và kiểm tra các sink |
| GD-13 | Chỉ số phân biệt phục vụ cốt lõi đúng, suy giảm hợp lệ và thành công giả | Đối chiếu kết quả nghiệp vụ với số liệu vận hành |
| GD-14 | Nghiệm thu gắn với build, ma trận, policy và giới hạn quan sát | Hồ sơ fixture và kết quả từng ca |

### 12.1. Đặc tả sâu hơn cho màn hình tiến độ cá nhân

```text
Phạm vi:
  Đọc tiến độ của chính người dùng trong tenant đã xác minh.

Bắt buộc:
  Có quyền hợp lệ và ràng buộc đúng subject, tenant, course.

Bình thường:
  Dùng nguồn chính; chỉ thêm gợi ý khi thành phần đó đủ điều kiện.

Khi nguồn chính lỗi:
  Chỉ dùng snapshot nếu các điều kiện cache đã được kiểm chứng.
  Nêu trạng thái cập nhật theo hợp đồng UI.

Khi không có quyền hoặc nguồn dữ liệu an toàn:
  Không trả tiến độ cá nhân từ một cache rộng hơn để cứu response.

Giới hạn:
  Deadline, tuổi snapshot và tải fallback lấy từ policy của dự án.

Nghiệm thu:
  Đo cả dữ liệu thực nhận, scope, latency và tín hiệu trạng thái.
```

Các tham số phải được chốt trước nghiệm thu. Không dùng từ “nhanh”, “mới” hoặc “tự phục hồi” mà không có mốc, điều kiện và cách đo.

## 13. Kiểm thử bằng fault injection và dữ liệu tổng hợp

### 13.1. Ma trận kiểm thử minh họa

| Ca | Điều kiện kích hoạt | Điều kiện đạt |
|---|---|---|
| TC-GD-01 | Mọi điều kiện bình thường | Chức năng đầy đủ đúng hợp đồng, có ca đối chứng cho phục hồi |
| TC-GD-02 | Gợi ý timeout hoặc lỗi | Nội dung cốt lõi vẫn đúng, không chờ vô hạn hoặc cạn tài nguyên |
| TC-GD-03 | Nguồn đọc chính lỗi, cache hợp lệ | Dùng đúng snapshot, scope và nhãn cập nhật |
| TC-GD-04 | Cache hết hạn, sai tenant hoặc sai subject | Không dùng làm fallback, không phát hành dữ liệu riêng tư |
| TC-GD-05 | Quyền DENY hoặc không xác lập được | Không dùng cache hoặc role mặc định để mở dữ liệu |
| TC-GD-06 | Nhiều tầng retry và dependency quá tải | Tổng lần gọi, deadline và tài nguyên nằm trong ngân sách |
| TC-GD-07 | Cache hoặc queue dự phòng cũng quá tải | Từ chối có kiểm soát, không nhận vô hạn hoặc rơi về payload thô |
| TC-GD-08 | Queue ghi thất bại hoặc chỉ còn bộ nhớ tạm | Không cam kết đã tiếp nhận bền vững hoặc sẽ hoàn tất |
| TC-GD-09 | Thao tác ghi commit rồi response timeout | Có trạng thái hoặc đối soát đúng, không tự tạo tác động lặp |
| TC-GD-10 | Job chờ tới khi quyền hoặc policy thay đổi | Thực thi theo hợp đồng hiện hành, không dùng principal mặc định quá rộng |
| TC-GD-11 | Không đạt điều kiện khóa hoặc audit bắt buộc | Không lưu bản rõ hoặc bỏ điều kiện bảo mật để tiếp tục |
| TC-GD-12 | UI đã ẩn chức năng nhưng gọi trực tiếp backend | Hạn chế vẫn được thi hành tại ranh giới thực hiện |
| TC-GD-13 | Nguồn khỏe lại rồi lỗi chập chờn | Điều kiện phục hồi và mở tải không gây dao động ngoài policy |
| TC-GD-14 | Xả backlog, job UNKNOWN và dữ liệu xung đột sau phục hồi | Giới hạn tải, đối soát và hòa giải đúng hợp đồng |
| TC-GD-15 | Canary trong input, error upstream và đường fallback | Không phát hành secret hoặc PII bị cấm qua log hay response |
| TC-GD-16 | Tải nhiều tenant cùng lúc trong trạng thái suy giảm | Cô lập tài nguyên và mức phục vụ tối thiểu đạt phạm vi đã chốt |

### 13.2. Oracle phải nhìn tác động thực tế

Không chỉ đo HTTP status hoặc nhìn banner trên giao diện. Kiểm tra dữ liệu trả về, số lần gọi dependency, thay đổi database, message, file tạm và trạng thái job phù hợp với ca.

Với lỗi sau commit, cần chứng minh dependency đã thực hiện trước khi làm mất response. Với cache sai tenant, cần dữ liệu fixture khác nhau để phát hiện rò rỉ thực sự, không chỉ kiểm tra tên key.

Với retry hoặc breaker, xác nhận trạng thái và số lần thử hiệu lực. Nếu request được đáp ứng từ cache trước khi tới dependency, chưa kiểm chứng được nhánh timeout mà ca thử dự định kích hoạt.

### 13.3. Kiểm tra cả suy giảm và khả năng phục vụ

Một hệ thống từ chối tất cả request có thể không làm lộ dữ liệu nhưng chưa đạt yêu cầu graceful degradation. Cần ca chứng minh chức năng còn đủ điều kiện vẫn phục vụ đúng.

Ngược lại, latency rất thấp do trả object rỗng hoặc báo hoàn tất giả không phải thành công. Đối chiếu với kết quả nghiệp vụ và bất biến trước khi tính đạt.

Không cần dùng dữ liệu thật hoặc secret production. Dùng tenant, principal, bản ghi, queue và dependency tổng hợp trong môi trường kiểm soát.

## 14. Quan sát vận hành và tiêu chí phục vụ

### 14.1. Phân biệt các loại kết quả

Theo dõi riêng phục vụ đầy đủ, suy giảm hợp lệ, bị hạn chế theo điều kiện bắt buộc, pending, UNKNOWN và lỗi ngoài hợp đồng.

Nếu tính tỷ lệ thành công cho chức năng cốt lõi, cần định nghĩa request nào đủ điều kiện và kết quả nào thực sự đạt. Không lấy mọi response có status thành công làm mẫu số hoặc tử số mà bỏ ngữ nghĩa.

Latency, tuổi snapshot, backlog, độ trễ xử lý và mức dùng tài nguyên cần được liên kết với chế độ và hành động. Một chỉ số trung bình chung có thể che việc một tenant hoặc chức năng quan trọng không được phục vụ.

### 14.2. Tín hiệu tối thiểu cho điều tra

Sự kiện chuyển chế độ có thể chứa action ID, chế độ trước và sau, mã nguyên nhân hữu hạn, revision policy, revision triển khai và reference đối chiếu không cấp quyền.

Không cần ghi credential, body người dùng hoặc toàn bộ cache để giải thích rằng nguồn chính không khả dụng. Metric dùng nhãn hữu hạn phù hợp, tránh subject, token hoặc request ID làm label cho từng chuỗi thời gian.

Theo dõi các điều kiện như fallback hết hạn, queue gần giới hạn, audit mất bền vững và recovery bị kẹt. Có runbook theo chủ sở hữu, không chỉ một banner “degraded” không dẫn tới hành động.

### 14.3. Thay đổi cần cập nhật bằng chứng

Thay dependency, policy quyền, loại dữ liệu, cache key, queue, retry, health check hoặc feature flag đều có thể thay hành vi suy giảm.

Cập nhật ma trận và ca thử liên quan. Một kết quả cũ về snapshot công khai không chứng minh fallback cho dữ liệu cá nhân mới cũng an toàn.

## 15. Truy vết rủi ro tới nghiệm thu

Một chuỗi minh họa:

```text
Rủi ro:
  Nguồn tiến độ lỗi khiến fallback trả cache chỉ khóa theo course ID,
  làm dữ liệu người học khác xuất hiện trong cùng tenant hoặc khác tenant.
    -> GD-02, GD-03, GD-10, GD-14
    -> cache có scope tin cậy và cổng quyền trước phục vụ
    -> TC-GD-03, TC-GD-04, TC-GD-05
    -> dữ liệu thực nhận, cache metadata và verdict quyền tổng hợp
    -> kết luận theo build, policy và fixture đã kiểm tra
```

Hồ sơ nghiệm thu cần có danh mục hành động, dependency, bất biến, budget, state transition, cấu hình hiệu lực và các ca đã chạy. Ghi riêng phần chưa quan sát được hoặc chưa có bằng chứng.

Một tiêu chí đo được có thể là:

> Với các hành động và tình huống lỗi đã liệt kê, hệ thống giữ mức phục vụ tối thiểu khi đủ điều kiện, không phát hành dữ liệu hoặc tác động ngoài bất biến, không vượt ngân sách tài nguyên đã chốt và phản ánh đúng pending hoặc UNKNOWN. Phục hồi đạt điều kiện mở lại cùng đối soát backlog. Các phần chưa kiểm chứng không được tính là PASS.

Kết luận này theo phạm vi kiểm thử, không bảo đảm mọi dependency và mọi kiểu sự cố tương lai đều có thể được che giấu bằng fallback. Một số hành động phải ngừng phục vụ khi không còn đủ điều kiện đúng và an toàn.

## 16. Thực hành đặc tả cho nền tảng học tập

Một trang học có nội dung khóa học, tiến độ cá nhân, gợi ý và nộp bài. Gợi ý dùng một dịch vụ ngoài; tiến độ có cache; bài nộp đi qua queue. Khi một dependency lỗi, code hiện bắt mọi exception, trả dữ liệu rỗng và hiển thị “đã lưu”. Consumer dùng một service account rộng quyền và hệ thống tự retry ở nhiều tầng.

Hãy xây dựng một đặc tả gồm:

1. Chức năng cốt lõi, phần optional và bất biến bảo mật của từng hành động.
2. Ma trận lỗi với fallback được phép và điều kiện buộc phải hạn chế.
3. Policy cache gồm scope, quyền, tuổi dữ liệu và hành vi khi thu hồi hoặc xóa.
4. Deadline, retry, bulkhead, hạn mức tenant và dung lượng fallback.
5. Hợp đồng tiếp nhận bền vững, trạng thái bài nộp và xử lý UNKNOWN.
6. Quyền enqueue, quyền thực thi và cách tránh tác động lặp.
7. Hành vi khi không đạt điều kiện mã hóa hoặc audit bắt buộc.
8. Nội dung API và UI thể hiện đúng suy giảm, pending và nguồn snapshot.
9. State machine phục hồi cùng cách mở tải, đối soát backlog và xử lý xung đột.
10. Bộ ca lỗi có bằng chứng cho cả tính sẵn sàng, tính đúng và ranh giới dữ liệu.

Hồ sơ hoàn thành cần cho người khác xác định được chức năng nào còn được phép hoạt động, vì sao fallback đó hợp lệ, khi nào phải dừng và bằng chứng nào xác nhận hệ thống phục hồi mà không đánh đổi các điều kiện bảo mật bắt buộc.
