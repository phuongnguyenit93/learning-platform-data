# Kiểm thử tải bộ giới hạn tốc độ (Rate limiter load)

Một endpoint xuất báo cáo có thể cho phép một tài khoản gửi nhiều request đồng thời, tạo hàng nghìn job hoặc làm nghẽn database. Thêm rate limiter giúp kiểm soát lượng việc được nhận, nhưng chỉ trả nhiều mã 429 chưa chứng minh cơ chế đó đúng: mỗi replica có thể cấp một ngân sách riêng ngoài dự kiến, người dùng có thể đổi key để lấy thêm lượt, hoặc request bị từ chối vẫn tạo job.

Trong chương **Load Testing** của module Business Logic Security, kiểm thử tải rate limiter phải nối ba câu hỏi: **ai đang dùng ngân sách nào, bao nhiêu chi phí thực sự được cho đi qua, và những request đó tạo hiệu lực nghiệp vụ gì?** Độ trễ và throughput có ý nghĩa khi được đối chiếu với hợp đồng giới hạn cùng dữ liệu đã commit.

## 1. Mục tiêu và phạm vi

Sau bài học, bạn có thể:

- Xác định thuật toán, phạm vi key, chi phí và ranh giới áp dụng của rate limiter.
- Thiết kế tải burst, tải duy trì và tải nhiều danh tính để kiểm tra đúng chính sách.
- Phân biệt tải dự kiến, request đã phát, quyết định admission và thao tác nghiệp vụ.
- Xây oracle theo token bucket hoặc cửa sổ đếm, không áp cùng một công thức cho mọi thuật toán.
- Kiểm tra tính đúng khi có nhiều replica, retry, mất phản hồi và lỗi kho trạng thái.
- Đo tác động của rate limiter lên caller hợp lệ, pipeline và khả năng phục hồi.
- Báo cáo riêng tính đúng, hiệu năng và các kết quả chưa xác định.

Rate limiting hạn chế mức sử dụng theo thời gian. Nó không thay thế quyền theo đối tượng, quy trình phê duyệt, giới hạn quota toàn kỳ, transaction hoặc idempotency. Hai request vẫn có thể cùng tranh một tài nguyên dù tốc độ tổng thấp hơn ngưỡng.

### 1.1. Phân biệt các loại giới hạn

| Cơ chế | Điều được giới hạn | Ví dụ |
|---|---|---|
| Rate limit | Lượng công việc theo thời gian | Ngân sách burst và tốc độ cấp lại cho một principal |
| Concurrency limit | Số tác vụ đang thực thi | Tối đa một số job nặng đang chạy cùng lúc |
| Quota nghiệp vụ | Tổng quyền sử dụng theo phạm vi/kỳ | Mỗi tenant có một số lượt xuất trong kỳ hợp đồng |
| Idempotency | Hiệu lực của cùng một ý định gửi lại | Retry không tạo job xuất thứ hai |
| Authorization | Chủ thể được làm gì trên object nào | Chỉ xuất dữ liệu thuộc phạm vi được phép |

Một rate limiter cho 10 request mỗi giây không tự ngăn 1.000 job tồn tại đồng thời nếu mỗi job kéo dài rất lâu. Cần quan sát cả hàng đợi và tác vụ đang chạy.

## 2. Chốt hợp đồng trước khi phát tải

### 2.1. Những thông số phải được định nghĩa

```text
Thuật toán và cấu hình:
    fixed window, sliding window, token bucket hoặc cơ chế khác

Scope:
    tenant, principal, operation class, IP, resource hoặc tổ hợp

Cost:
    mỗi request tốn một đơn vị hay cost do server tính

Admission boundary:
    request được tính trước hay sau xác thực, validation, idempotency

State:
    cục bộ, dùng chung, chia ngân sách hoặc xấp xỉ có giới hạn

Failure policy:
    kho trạng thái chậm/mất kết nối thì từ chối, chờ hay cho qua có kiểm soát

Response:
    mã, business code và thông tin chờ theo hợp đồng
```

Không có hợp đồng này, test dễ coi một hành vi đúng của thuật toán là lỗi, hoặc hợp thức hóa một lần cấp dư bằng cách tự thêm dung sai sau khi nhìn kết quả.

### 2.2. Mô hình xuyên suốt: endpoint xuất báo cáo

Fixture dùng:

```http
POST /v1/reports/exports HTTP/1.1
Host: reports.test
Authorization: Bearer <token-hop-le>
Content-Type: application/json
Idempotency-Key: export-operation-001

{
  "reportId": "REPORT-A",
  "format": "CSV"
}
```

Hợp đồng cơ sở:

- Key là `tenant + principal + operationClass`, với operationClass của thao tác xuất báo cáo.
- Token bucket có capacity B = 20 đơn vị, cấp lại r = 5 đơn vị mỗi giây.
- Ban đầu bucket đầy; mỗi attempt tới limiter có cost = 1.
- Xác thực danh tính diễn ra trước limiter nghiệp vụ này.
- Limiter quyết định admission trước idempotency và transaction tạo job.
- Attempt được nhận sẽ tiêu một đơn vị, kể cả sau đó bị từ chối do điều kiện nghiệp vụ.
- Attempt bị limiter từ chối không bị trừ thêm token theo chính sách cơ sở.
- Cùng operation gửi lại vẫn là một attempt dùng ngân sách, nhưng không tạo thêm job.
- Request mới hợp lệ được nhận trả 202 sau khi tạo job và dữ liệu cần thiết đã commit.
- Request bị rate limiter từ chối trả 429 với business code `RATE_LIMITED`.

Đây là thông số minh họa cho bài tập, không phải SLO hoặc cấu hình dùng sẵn. Một API chỉ tính cost cho operation mới cần hợp đồng và test khác.

### 2.3. Scope phải đến từ nguồn có thẩm quyền

Caller không được tạo ngân sách mới bằng cách đổi:

- tenantId hoặc userId tùy ý trong body.
- Idempotency key.
- Chữ hoa/thường hoặc biến thể route không làm thay đổi thao tác nghiệp vụ.
- Một header nhận diện caller mà hệ thống chưa xác thực.

Nếu có giới hạn theo IP, cần xác định địa chỉ client từ chuỗi proxy được tin cậy theo cấu hình. Không xem một giá trị forwarded header tùy ý do client gửi là danh tính đã được xác minh.

Giới hạn theo IP có thể chia sẻ giữa nhiều người dùng phía sau cùng một mạng. Nó không tương đương giới hạn theo principal và cần nhóm kiểm thử riêng.

## 3. Invariant và oracle theo thuật toán

### 3.1. Token bucket

Bucket chứa tối đa B token. Trong khoảng thời gian d, nó được cấp lại tối đa r × d, phần vượt B bị bỏ.

Với cùng một key và cost tính bằng đơn vị token, tổng cost được admission trong bất kỳ khoảng đo có độ dài T không vượt:

```text
admittedCost <= B + r * T
```

Đây là một giới hạn trên; không phải cam kết mọi lượt chạy sẽ dùng hết ngân sách. Với cost nguyên, phải tính chính xác phần token cần thiết thay vì làm tròn lên.

Quan hệ mạnh hơn cho mô hình tuần tự:

```text
tokensBefore = min(B, tokensPrevious + r * elapsed)

nếu cost <= tokensBefore:
    ADMITTED
    tokensAfter = tokensBefore - cost
ngược lại:
    DENIED
    tokensAfter = tokensBefore
```

Một request bị từ chối không trừ cost, nhưng token vẫn có thể tăng do thời gian trôi và timestamp nội bộ có thể thay đổi. Vì vậy không assert toàn bộ trạng thái limiter giống hệt trước request.

### 3.2. Fixed window và sliding window

Với fixed window, ngân sách tính trong từng cửa sổ cố định. Gần ranh giới, một burst cuối cửa sổ rồi burst đầu cửa sổ tiếp có thể tạo nhiều request trong một khoảng ngắn mà vẫn đúng thuật toán.

Với sliding window, giới hạn gắn với cửa sổ trượt theo thời gian; cách thực hiện có thể chính xác hoặc xấp xỉ.

Không lấy `B + r * T` của token bucket làm oracle cho fixed window. Cũng không gán cho một sliding counter xấp xỉ cam kết chính xác mà implementation không cung cấp. Sai số cho phép phải có trong thiết kế trước lượt thử.

### 3.3. Những invariant ngoài phép đếm

```text
Key và cost được xác định theo danh tính và quy tắc server.

Request bị limiter từ chối không tạo job hoặc tác dụng phụ nghiệp vụ mới.

Request được admission vẫn phải qua quyền theo object và state machine.

Replay không tạo hiệu lực nghiệp vụ trùng.

Các scope độc lập không chia sẻ nhầm trạng thái.
```

Nếu có giới hạn phân cấp theo principal và tenant, một attempt chỉ được coi là admission khi đáp ứng chính sách kết hợp. Phải nói rõ việc thất bại ở một tầng có được tính chi phí ở tầng khác không; không tự mặc định mọi triển khai đều hoàn nguyên tất cả counter.

## 4. Fixture, clock và điều kiện môi trường

### 4.1. Dữ liệu cần chuẩn bị

- Principal A và B cùng tenant T1; principal C thuộc tenant T2.
- Report thuộc đúng phạm vi mỗi caller và một report caller không có quyền.
- Key limiter mới hoặc trạng thái ban đầu đã biết.
- Idempotency key riêng cho operation mới, key giữ nguyên cho replay.
- Quyền quan sát quyết định admission, job, outbox và adapter xuất dữ liệu.
- Cấu hình limiter, số replica và giới hạn các lớp phía trước.

Không để nhiều bài test vô tình dùng chung bucket rồi làm sai giả định “ban đầu đầy”. Nếu quota hay concurrency limit có thể chặn endpoint trước limiter đang xét, cần biết và ghi rõ điều đó.

### 4.2. Hai cách kiểm soát thời gian

**Test thuật toán với clock điều khiển được:** phù hợp kiểm tra đúng số token, ranh giới và làm tròn. Đây là nơi có thể đóng băng refill để kiểm tra chính xác B lần admission ban đầu.

**Load test với thời gian thực:** phù hợp đánh giá distributed state, contention và độ trễ. Cần mốc quyết định đáng tin cậy hoặc oracle bảo thủ; không giả định request gửi gần nhau đều được xử lý tại cùng thời điểm.

Chỉ đổi clock của generator không đổi clock của server hoặc kho trạng thái. Clock test phải được đưa vào đúng thành phần sử dụng nó.

### 4.3. Kiểm tra baseline

Ở tải thấp, xác nhận:

1. Caller hợp lệ có thể tạo một job.
2. Caller không có quyền không xuất được report.
3. Replay trả về operation cũ mà không tạo job thứ hai.
4. Sự kiện admission có scope và cost dự kiến.

Nếu baseline sai vì token đăng nhập hết hạn, report không tồn tại hoặc payload không hợp lệ, chưa thể đánh giá cơ chế giới hạn tải.

## 5. Ma trận kịch bản tải

Các kịch bản dưới cần fixture riêng hoặc trạng thái bucket được kiểm soát, không dùng nối tiếp rồi giả định mỗi lần đều bắt đầu đầy.

| Kịch bản | Cách tạo tải | Điều cần chứng minh |
|---|---|---|
| Burst đầu bucket đầy | Nhiều attempt gần nhau trên một key | Tổng admission đúng ngân sách và refill thực tế |
| Tải duy trì dưới tốc độ cấp lại | Dòng request đủ chậm, payload hợp lệ | Không từ chối sai khi có token và không có giới hạn khác |
| Tải duy trì vượt tốc độ cấp lại | Giữ nhu cầu đến lớn hơn r | Hạn mức được giữ, độ trễ và lượng từ chối được quan sát |
| Nhiều principal cùng tenant | A và B dùng report hợp lệ | Scope cá nhân không trộn; quota tenant hoạt động theo cấu hình |
| Nhiều tenant | T1 và T2 có tải khác nhau | Không nhầm ngân sách hoặc rò dữ liệu giữa tenant |
| Cùng operation gửi lại | Cùng key idempotency | Attempt được tính theo hợp đồng, job không nhân đôi |
| Đổi key liên tục | Một principal, nhiều operation key | Không làm mới bucket của principal |
| Nhiều replica | Cùng key đi qua nhiều instance | Không cấp dư do mỗi process tự có ngân sách đầy |
| Cost khác nhau | Request hợp lệ có chi phí do server tính | Không đếm số request thay cho tổng cost |
| Kho trạng thái lỗi | Chậm, timeout, mất kết nối có kiểm soát | Fallback đúng chính sách, không bỏ qua quyền/nghiệp vụ |
| Phục hồi sau overload | Dừng đỉnh tải, tiếp tục probe hợp lệ | Hàng đợi giảm, token hồi phục và service tiếp tục hoạt động |

### 5.1. Burst không có nghĩa thời gian bằng không

Với B = 20, r = 5 và request cost 1, không thể kết luận “trên 20 admission là lỗi” nếu đợt burst thực sự kéo dài nhiều giây.

Muốn kiểm tra đúng 20 admission ban đầu, dùng clock đóng băng hoặc cấu hình refill bằng 0 trong một test thuật toán được xác định rõ. Muốn kiểm tra load thực, dùng khoảng thời gian quyết định và tính phần refill.

Một bài test dùng thời gian thực vẫn cần có khả năng phát hiện race cấp quá mức; chỉ cần oracle phản ánh thời gian thực, không tùy ý nới số token sau khi thấy kết quả.

### 5.2. Tải thấp cũng quan trọng

Một limiter từ chối toàn bộ request có thể giữ giới hạn trên nhưng không thực hiện đúng chức năng. Kiểm tra attempt hợp lệ khi bucket đầy và không có lớp chặn khác phải được nhận.

Với cost khác nhau, token còn 3 có thể nhận cost 2 nhưng chưa nhận cost 4. Không coi mọi từ chối là sai chỉ vì bucket không bằng 0.

### 5.3. Không trộn kiểm tra fairness vào cam kết chưa có

Rate limit tổng theo tenant không tự đảm bảo mỗi principal được một phần công bằng. Một principal ồn có thể dùng phần lớn ngân sách chung nếu không có cơ chế phân chia.

Nếu sản phẩm yêu cầu mỗi principal có ngân sách riêng hoặc dung lượng tối thiểu, phải có mô hình đó và phép thử noisy neighbor. Không đánh giá FIFO hoặc chia đều chỉ từ thứ tự gửi ở client.

## 6. Phát tải và ghi nhận kết quả

### 6.1. Tách số liệu của generator

Ghi riêng:

```text
scheduled = số attempt kế hoạch đến hạn
started = số attempt thực sự được bắt đầu
notStarted = phần không phát được theo chính sách lập lịch
httpResponses = attempt có response quan sát được
transportFailures = attempt kết thúc bằng lỗi truyền tải
```

Khi lịch đóng, không còn phần việc chờ và mọi lời gọi phía client đã kết thúc:

```text
scheduled = started + notStarted
started = httpResponses + transportFailures
```

Các đẳng thức này không xác định bao nhiêu attempt được limiter nhận hoặc bao nhiêu job đã commit. Request timeout có thể đã tạo hiệu lực.

### 6.2. Mô hình đóng và mô hình mở

Mô hình đóng giữ tối đa W request đang chạy rồi phát request mới khi có tác vụ kết thúc. Khi server chậm, tốc độ đến tự giảm; hữu ích cho đo mức cạnh tranh có giới hạn nhưng có thể che nhu cầu tăng cao.

Mô hình mở phát theo lịch đến độc lập, trong giới hạn của generator. Cần ghi scheduler lag, backlog hoặc attempt bị bỏ. Đừng tích lũy backlog vô hạn rồi gọi đó là đã tạo đúng tải mục tiêu.

Với cả hai, đặt giới hạn in-flight, tổng thời gian, request timeout và ngân sách retry. Đo CPU, connection và lỗi generator để không nhầm máy phát tải nghẽn với server có khả năng giới hạn tốt.

### 6.3. Pseudocode cho một lượt thử

```text
chuẩn bị scope và trạng thái bucket đã biết
chuẩn bị danh tính, operation key và payload
bắt đầu quan sát quyết định limiter và hiệu lực nghiệp vụ

theo lịch cấu hình:
    nếu còn ngân sách tài nguyên:
        bắt đầu attempt, ghi attemptId và thời gian
    ngược lại:
        ghi notStarted hoặc backlog theo chính sách

với mỗi attempt kết thúc:
    lưu response hoặc exception
    giữ operation key nếu retry cùng ý định
    chỉ retry khi hợp đồng và ngân sách cho phép

dừng tạo attempt mới
thu tác vụ còn lại
đối soát request/operation chưa rõ hiệu lực
chờ công việc thuộc fixture kết thúc trong deadline
đọc snapshot và kiểm tra oracle
```

Hủy future chỉ yêu cầu hủy phía client; không chứng minh server đã dừng. Không cleanup dữ liệu rồi để request cũ có thể commit vào fixture tái dùng.

### 6.4. Retry không được làm sai tải

Ghi lượt gốc và lượt phát sinh riêng. Một request bị 429 rồi retry ngay liên tục có thể tạo retry storm, làm phép đo khác hoàn toàn nhu cầu ban đầu.

Nếu response cung cấp thời gian chờ, kiểm tra thông tin đó theo hợp đồng và dùng chính sách retry phù hợp. Không kỳ vọng mọi request retry đúng lúc đều được nhận nếu nhiều caller vẫn tranh cùng ngân sách.

## 7. Oracle cho quyết định admission

### 7.1. Không lấy HTTP 2xx làm số admission

Theo hợp đồng mẫu, attempt có thể:

1. Được limiter nhận và tạo job.
2. Được limiter nhận nhưng bị business validation từ chối.
3. Được limiter nhận nhưng gặp lỗi sau đó.
4. Bị limiter từ chối.
5. Chưa tới limiter vì bị một lớp khác chặn.

Nhóm 1, 2 và 3 đều đã dùng ngân sách ở ranh giới đang xét. Replay cũng dùng ngân sách nếu đi qua limiter theo chính sách này.

Cần dữ liệu quyết định hoặc tín hiệu tương đương từ chính lớp limiter. Metric lấy mẫu hay log có thể rơi bản ghi không đủ làm sổ cái chính xác nếu không có cơ chế đối soát.

### 7.2. Dùng mốc thời gian ở đúng ranh giới

Để kiểm tra envelope token bucket, cần tổng cost admission cùng khoảng thời gian chứa các quyết định đó, trên cùng key.

Nếu chỉ có thời gian client, có thể dùng khoảng bảo thủ từ trước lần gửi đầu tới sau lần nhận kết quả cuối cho tập request đã hoàn tất. Khoảng này thường dài hơn khoảng quyết định thực, nên giới hạn trên lỏng hơn.

Nếu tập admission đã biết vẫn vượt giới hạn bảo thủ đó, có bằng chứng vi phạm với các giả định phù hợp. Nếu không vượt, chưa chứng minh mọi quyết định đều chính xác, nhất là khi còn request chưa rõ.

Không dựng một thứ tự chính xác bằng timestamp từ nhiều máy chưa được đồng bộ. Với kiểm tra nhỏ có điều phối, dùng clock điều khiển được và thứ tự quyết định của authority phù hợp.

### 7.3. Kiểm tra nhiều đoạn, không chỉ tổng cuối

Một lượt dài có thể vượt burst ở đầu rồi từ chối quá lâu phía sau, khiến tổng toàn lượt vẫn dưới `B + r * T`.

Trên trace có mốc đáng tin cậy, kiểm tra các đoạn liên quan:

- Burst đầu.
- Đoạn quanh lúc token cạn.
- Đoạn sau khi refill.
- Đoạn khi replica hoặc kho trạng thái thay đổi.

Với trace nhỏ, có thể kiểm tra các khoảng giữa những quyết định admission. Với test thuật toán tuần tự, chạy model trên cả admission lẫn denial để phát hiện cả cấp dư và từ chối sai.

Giới hạn envelope là điều kiện cần; một mình nó không chứng minh đúng toàn bộ quyết định hoặc quyền theo scope.

### 7.4. Cost phải do oracle xác định được

Nếu export lớn có cost 10 và export nhỏ cost 1, 10 request không thể được coi là 10 đơn vị mà không xem payload và chính sách server.

Kiểm tra caller không thể gửi `cost = 0`, quantity âm hoặc chia đổi tên route để giảm cost ngoài chính sách. Dữ liệu client có thể là đầu vào cho tính cost, nhưng kết quả phải được server xác định và kiểm tra miền giá trị.

Một request có cost lớn hơn B sẽ không đủ token dù chờ bao lâu trong token bucket cơ sở. API cần xử lý theo hợp đồng, không báo một thời gian chờ hữu hạn như thể refill có thể vượt capacity.

## 8. Ví dụ Java: model token bucket dùng số chính xác

Đoạn Java 17 sau là oracle tuần tự cho B và r nguyên, cost nguyên. Model không xử lý đồng thời và không phải limiter production phân tán.

Để giữ phần token lẻ, một token được biểu diễn bằng 1.000.000.000 credit. Với r token/giây và d nanosecond, số credit được cấp lại là r × d. Dùng số nguyên lớn tránh overflow và tránh làm tròn lặp khiến token bị tạo thêm hoặc mất đi.

```java
import java.math.BigInteger;

record AdmissionDecision(boolean admitted, BigInteger creditsAfter) {}

final class TokenBucketModel {
    private static final BigInteger SCALE =
            BigInteger.valueOf(1_000_000_000L);

    private final BigInteger maxCredits;
    private final BigInteger refillPerSecond;
    private BigInteger credits;
    private long lastNanos;

    TokenBucketModel(long capacity, long refillPerSecond, long initialNanos) {
        if (capacity <= 0 || refillPerSecond < 0 || initialNanos < 0) {
            throw new IllegalArgumentException("Invalid model configuration");
        }
        this.maxCredits = BigInteger.valueOf(capacity).multiply(SCALE);
        this.refillPerSecond = BigInteger.valueOf(refillPerSecond);
        this.credits = maxCredits;
        this.lastNanos = initialNanos;
    }

    AdmissionDecision decide(long nowNanos, long costUnits) {
        if (nowNanos < lastNanos || costUnits <= 0) {
            throw new IllegalArgumentException("Invalid time or cost");
        }

        long elapsedNanos = nowNanos - lastNanos;
        BigInteger refill = refillPerSecond.multiply(
                BigInteger.valueOf(elapsedNanos));
        credits = credits.add(refill).min(maxCredits);
        lastNanos = nowNanos;

        BigInteger required =
                BigInteger.valueOf(costUnits).multiply(SCALE);
        if (credits.compareTo(required) < 0) {
            return new AdmissionDecision(false, credits);
        }

        credits = credits.subtract(required);
        return new AdmissionDecision(true, credits);
    }
}
```

`nowNanos` trong model là thời gian logic không âm và không giảm, không phải giá trị thô tùy ý từ mọi máy. Khi dùng clock thực, adapter phải xác định gốc và miền biểu diễn phù hợp.

Một chuỗi kiểm tra nhỏ:

```text
B = 2, r = 1, initial time = 0

time 0:             cost 1 -> ADMITTED
time 0:             cost 1 -> ADMITTED
time 0:             cost 1 -> DENIED
time 500.000.000:   cost 1 -> DENIED, giữ 0,5 token
time 1.000.000.000: cost 1 -> ADMITTED
time 1.000.000.000: cost 1 -> DENIED
```

Chuỗi này phát hiện cách làm tròn mỗi lần refill gây mất phần lẻ hoặc cấp dư. Với rate dạng phân số, lịch refill rời rạc hoặc thuật toán xấp xỉ, cần model đúng hợp đồng thay vì ép implementation giống đoạn mã.

Giữ model độc lập với hàm tính token của production. Nếu cả oracle lẫn limiter gọi cùng hàm sai, test có thể xác nhận lại cùng lỗi.

## 9. Nhiều replica, clock và vòng đời trạng thái

### 9.1. Ngân sách chung không được tự nhân theo replica

Với scope toàn service, B = 20 không có nghĩa mỗi replica được tự cấp 20 rồi cộng kết quả. Nếu ba instance đều giữ bucket đầy riêng, một principal có thể nhận nhiều hơn ngân sách chung.

Kiểm tra:

- Cùng một key thực sự được routing tới nhiều instance.
- Cơ chế cập nhật state phối hợp đúng khi có cạnh tranh.
- Đọc token, xét điều kiện và trừ cost không bị tách thành các bước có thể ghi đè lẫn nhau.
- Retry sau lỗi cập nhật không tự làm mới bucket.

Một kiến trúc chia trước ngân sách cho replica có thể hợp lệ nếu tổng phần được cấp và phần cấp lại giữ đúng cam kết. Khi đó test theo mô hình phân bổ đó, không mặc định mọi limiter đều phải có một counter vật lý duy nhất.

Sticky session có thể làm test đi mãi vào một instance. Số replica cấu hình không chứng minh load đã kiểm tra coordination giữa chúng.

### 9.2. Restart, eviction và TTL

Những sự kiện cần tạo áp lực:

- Restart instance sau khi bucket gần cạn.
- Key bị hết hạn.
- Kho cache đẩy key ra do áp lực bộ nhớ.
- Chuyển shard hoặc đổi node lưu state.

Nếu quên state rồi khởi tạo lại bucket đầy quá sớm, caller nhận thêm token ngoài chính sách. TTL phải phù hợp với ngữ nghĩa; trong token bucket cơ sở, việc quên state chỉ tương đương bucket đầy khi đã đủ thời gian hồi đầy theo mô hình.

Nếu thiết kế chấp nhận mất state và cho thêm burst trong một số tình huống, đó là nới cam kết cần được mô tả, đo và đánh giá riêng. Không gọi một đợt như vậy là tuân thủ giới hạn nghiêm ngặt ban đầu.

### 9.3. Clock không đồng nhất

Nếu các node tự dùng clock khác nhau để refill cùng bucket, bước nhảy tiến có thể cấp dư còn bước nhảy lùi có thể chặn quá lâu.

Test cần biết authority thời gian nằm ở đâu và hành vi khi timestamp không tăng. Với hệ phân tán, không trộn timestamp từ các nguồn khác nhau rồi chạy model như một clock đơn.

Đối với fixed window, thử trước, đúng và sau ranh giới cửa sổ. Đối với token bucket, thử khoảng refill nhỏ liên tiếp, idle dài và refill chạm capacity. Các phép thử này thuộc tính đúng của thuật toán; load test kiểm tra chúng khi có contention và biến động môi trường.

### 9.4. Đổi cấu hình khi đang chạy

Nếu B hoặc r thay đổi, mô hình phải nói rõ:

- Token hiện có được giữ, cắt xuống hay quy đổi thế nào?
- Cấu hình mới có hiệu lực từ mốc nào?
- Các replica có cùng một phiên bản chính sách không?
- Hạ hạn mức có vô tình làm đầy bucket không?

Không dùng cấu hình cuối lượt thử để giải thích mọi quyết định trước đó. Lưu phiên bản chính sách và mốc thay đổi trong trace.

## 10. Lỗi kho trạng thái và cơ chế fallback

### 10.1. Phân biệt hết ngân sách với không quyết định được

Kho state timeout không đồng nghĩa principal đã hết token. API có thể trả lỗi tạm thời khác với 429 theo hợp đồng. Nếu mọi lỗi store đều biến thành RATE_LIMITED, caller và báo cáo khó biết hệ thống thực sự đã ra quyết định gì.

Mô phỏng riêng:

- Timeout trước khi cập nhật state.
- Cập nhật đã thành công nhưng response từ store bị mất.
- Một phần node không truy cập được state.
- Store phục hồi sau một giai đoạn lỗi.

Không mặc định retry lại phép trừ là vô hại. Theo thiết kế, một attempt có thể cần định danh quyết định hoặc cách giải quyết kết quả chưa rõ; oracle phải biết việc đó được xử lý thế nào.

### 10.2. Fallback là một phần hợp đồng

Các khả năng gồm:

- Từ chối khi không thể quyết định admission.
- Chờ trong một deadline có giới hạn.
- Dùng ngân sách dự phòng được cấp rõ.
- Cho qua trong phạm vi đã được sản phẩm chấp nhận.

Mỗi lựa chọn tạo kỳ vọng khác nhau. Nếu cho qua khi lỗi, tách số quyết định bypass/fallback khỏi admission bình thường và ghi rõ ngân sách hoặc giới hạn được áp dụng. Không áp công thức token bucket bình thường rồi bỏ qua phần vượt vì “đang fallback”.

Giới hạn vẫn cần quan sát được trong các chế độ dự phòng mà thiết kế cam kết. Một local fallback trên mỗi replica có thể tiếp tục nhân burst nếu không có chính sách tổng.

### 10.3. Không bỏ qua quy tắc nghiệp vụ khi limiter lỗi

Dù fallback cho request đi tiếp, các kiểm tra sau vẫn phải hoạt động:

- Quyền xuất report của caller.
- Điều kiện dữ liệu đã được duyệt nếu nghiệp vụ yêu cầu.
- Giới hạn quota theo kỳ.
- State machine của operation.
- Idempotency và tính nguyên tử khi tạo job/outbox.

Cho phép qua rate limiter không phải cấp vai trò mới hoặc cho xuất dữ liệu của tenant khác. Kịch bản lỗi store nên có cả caller hợp lệ và request nhắm object không được phép.

### 10.4. Phục hồi không được gây burst ngoài hợp đồng

Khi store trở lại, kiểm tra state không bị thay thế bằng nhiều bucket đầy hoặc cộng hai lần ngân sách dự phòng. Đối soát operation đã được nhận trong fallback, worker còn chạy và số job thực tế.

Nếu kiến trúc không hỗ trợ hợp nhất chính xác state dự phòng, báo giới hạn bảo đảm thực tế. Đừng báo PASS cho một cam kết nghiêm ngặt hơn khả năng thiết kế.

## 11. Ví dụ đối soát một lượt tải

Giả sử bucket ban đầu đầy, B = 20, r = 5 token/giây, cost = 1. Các quyết định trong ví dụ thuộc cùng key, trong khoảng thời gian authority dài 10 giây. Mọi operation key đều mới; không có replay trong lượt này.

Giới hạn trên cho tổng cost admission:

```text
20 + 5 * 10 = 70 đơn vị
```

### 11.1. Số liệu generator

| Quan sát | Số lượng |
|---|---:|
| Attempt đến hạn theo lịch | 500 |
| Attempt thực sự bắt đầu | 480 |
| Attempt không phát được theo chính sách | 20 |
| HTTP 202 | 65 |
| HTTP 400 do điều kiện nghiệp vụ sau limiter | 1 |
| HTTP 500 | 1 |
| HTTP 429 | 411 |
| Lỗi truyền tải, chưa rõ hiệu lực ban đầu | 2 |

Response quan sát được là 478; cộng hai lỗi truyền tải bằng 480 attempt bắt đầu. Không được gọi 500 là tải đã tới service, cũng không được tính 65 response 202 thành toàn bộ số admission.

### 11.2. Quyết định limiter và hiệu lực

Dữ liệu có thẩm quyền cho thấy:

```text
ADMITTED = 68 attempt, tổng cost = 68
DENIED = 412 attempt
Job mới durable = 66
```

Đối soát:

- 65 attempt nhận 202 được admission và tạo 65 job.
- Một attempt được admission nhưng thất bại điều kiện nghiệp vụ, không tạo job.
- Một attempt được admission rồi gặp lỗi; đối soát xác nhận không commit job.
- Một lỗi truyền tải xảy ra sau admission và commit, tạo job thứ 66.
- Lỗi truyền tải còn lại thuộc attempt đã bị limiter từ chối.
- 411 response 429 còn lại khớp các quyết định DENIED.

Tổng admission là 68, không phải 65 hoặc 66. Số job nhỏ hơn admission phù hợp hợp đồng tính phí trước validation nghiệp vụ.

### 11.3. Điều có thể và chưa thể kết luận

`68 <= 70` thỏa giới hạn trên cho cả đoạn. Vẫn cần kiểm tra burst và các đoạn ngắn, scope, cost cùng trạng thái tạo job. Tổng cuối đúng không loại trừ việc limiter đã cấp dư lúc đầu rồi chặn quá lâu sau đó.

Hai lỗi truyền tải đã được đối soát hết nên không còn operation chưa rõ trong ví dụ. Nếu còn, phải giữ kết luận chưa đầy đủ cho phần tương ứng.

Đến mốc pipeline hoàn tất, kiểm tra 66 job và hiệu lực xuất tương ứng theo hợp đồng. Request bị từ chối không tạo job mới; request lỗi 500 chỉ được coi không có hiệu lực vì đã có bằng chứng, không phải vì bản thân status đó bảo đảm rollback.

### 11.4. Một số kết quả phải phát hiện

| Quan sát | Vấn đề |
|---|---|
| Tổng admission cost = 75 trong cùng đoạn 10 giây | Vượt envelope 70 của mô hình |
| 21 admission cost 1 trong đoạn 0,1 giây | Vượt 20,5 đơn vị cho đoạn đó |
| Đổi idempotency key làm bucket đầy trở lại | Scope limiter bị caller điều khiển sai |
| Mỗi replica nhận 20 burst nhưng cam kết B chung là 20 | Ngân sách bị nhân theo instance |
| Response 429 nhưng có job mới từ attempt đó | Admission và hiệu lực bị tách sai |
| Chỉ 2xx được tính vào cost dù hợp đồng tính trước business validation | Oracle hoặc accounting sai ranh giới |
| Không có trace cho hai timeout nhưng báo không tạo job | Kết luận vượt quá bằng chứng |

## 12. Oracle cho dữ liệu và tác dụng phụ nghiệp vụ

### 12.1. Request bị limiter từ chối

Với operation mới, kiểm tra không có:

- Job export mới.
- Outbox yêu cầu xuất mới.
- Thay đổi quota, trạng thái phê duyệt hoặc object nghiệp vụ.
- Lệnh xuất dữ liệu tới worker/hệ thống ngoài do attempt đó.

Audit và trạng thái limiter có thể thay đổi theo thời gian/chính sách. Chỉ so projection nghiệp vụ liên quan, không yêu cầu toàn database bất biến.

Nếu một replay bị 429 sau lần đầu đã thành công, job cũ vẫn tồn tại. Oracle phải kiểm tra **không tạo thêm hiệu lực**, không assert operation chưa từng có job.

### 12.2. Request được admission

Admission chỉ cho phép request đi tới bước sau; nó không chứng minh request được phép tạo hiệu lực.

Trên request trái quyền hoặc sai state, kiểm tra từ chối đúng quy tắc và không có job trái phép, kể cả khi token đã bị trừ theo hợp đồng.

Trên request hợp lệ, kiểm tra job đúng report, tenant và principal, cùng dữ liệu đã được duyệt. Nếu có retry hoặc giao lại event, kiểm tra một hiệu lực nghiệp vụ theo operation thay vì đòi đúng một lần gọi mạng trong mọi kiến trúc.

### 12.3. Chọn mốc đọc và hoàn tất

Đọc nguồn có thẩm quyền sau commit; tránh cache hoặc replica trễ. Với worker nền, theo dõi operation/correlation ID và chờ điều kiện cuối trong deadline.

Không chỉ sleep một khoảng cố định rồi chụp dữ liệu. Nếu chưa rõ request server có còn chạy hay không, snapshot chưa đủ để kết luận không có tác dụng phụ đến muộn.

Các bảng job, outbox và kết quả xuất có thể quan hệ một-nhiều. Đối chiếu từng tập trước khi tổng hợp; join trực tiếp rồi COUNT có thể tự nhân số dòng và tạo lỗi oracle.

## 13. Chỉ số, trace và cách đọc kết quả

### 13.1. Nhóm chỉ số cần tách

| Nhóm | Chỉ số ví dụ | Ý nghĩa |
|---|---|---|
| Generator | Scheduled, started, not started, scheduler lag | Tải thực có theo kế hoạch không |
| Admission | Allowed cost, denied, bypass, thời gian quyết định | Chính sách limiter thực sự làm gì |
| HTTP | Latency theo status/business code, lỗi truyền tải | Caller quan sát gì |
| Scope | Nhóm principal/tenant của fixture, phiên bản policy | Có nhầm phạm vi hoặc cấu hình không |
| State store | Latency, timeout, conflict, eviction | Nút nghẽn và sự cố ở đâu |
| Nghiệp vụ | Job mới, replay, từ chối quyền, quota | Admission tạo những hiệu lực nào |
| Pipeline | Queue depth, lag, thời gian hoàn tất | Hệ thống có xử lý kịp việc đã nhận không |
| Tính đúng | Vượt envelope, job từ denial, unknown còn lại | Cam kết nào bị phá hoặc chưa kiểm chứng được |

Không gộp latency 429 rất nhanh với đường tạo job rồi kết luận p95 chung tốt. Tách ít nhất admission thành công, denial, lỗi store và request được nhận nhưng thất bại phía sau.

### 13.2. Thông lượng có nhiều mẫu số

```text
request throughput: attempt có kết quả trong một khoảng đo
admission throughput: tổng cost được nhận trong một khoảng đo
business throughput: job hợp lệ mới đã commit trong một khoảng đo
completion throughput: công việc hợp lệ hoàn tất trong một khoảng đo
```

Ghi rõ khoảng đo và đơn vị. Cost/giây khác request/giây; job hoàn tất/giây khác request đã được nhận.

Nếu workload dùng nhiều replay, request throughput cao và job mới ít có thể đúng. Nếu workload gồm operation mới hợp lệ nhưng phần lớn bị throttled, phải xem admission throughput và mục tiêu phục vụ, không tự coi ít job là khả năng chống trùng tốt.

### 13.3. Đừng để observability làm sai phép đo

Trace đủ để đối soát attempt, key scope, cost, policy version, quyết định và operation. Tuy nhiên việc ghi đồng bộ toàn bộ payload cho mọi request có thể làm đổi tải đáng kể.

Một thiết kế quan sát phục vụ kiểm thử cần biết:

- Sự kiện quyết định có đầy đủ hay chỉ lấy mẫu.
- Log có thể rơi bản ghi khi quá tải không.
- Có đối chiếu được tổng event với counter nguồn không.
- Timestamp và thứ tự sự kiện đến từ authority nào.

Giữ token xác thực và bí mật ra khỏi log. Dùng alias trong fixture; không gắn mọi idempotency key hoặc attemptId thành nhãn metric không giới hạn. Những ID cần điều tra có thể nằm trong trace phù hợp.

### 13.4. Tách đạt giới hạn khỏi phục vụ đúng chức năng

Ba câu sau không tương đương:

- Không có bằng chứng cấp quá token.
- Mọi quyết định đúng với thuật toán và cấu hình.
- Hệ thống phục vụ workload theo yêu cầu hiệu năng.

Một limiter từ chối quá mức có thể đạt câu đầu nhưng không đạt câu hai. Một limiter đúng có thể vẫn tạo latency lớn hoặc queue không thoát được, làm câu ba không đạt.

Các ngưỡng độ trễ, tỷ lệ lỗi kỹ thuật, thời gian phục hồi và lượng phục vụ tối thiểu cần được chốt từ yêu cầu thực tế. Không dùng số B = 20, r = 5 của bài để suy ra SLO chung.

## 14. Quy trình thực hiện một lượt kiểm thử

### Bước 1: Mô tả hợp đồng và điều đang kiểm tra

Ghi thuật toán, scope, cost, trạng thái đầu, vị trí limiter, policy lỗi store và các lớp giới hạn khác. Chốt oracle nào kiểm tra chính xác thuật toán, oracle nào chỉ kiểm tra envelope và hiệu lực.

Với giới hạn xấp xỉ hoặc ngân sách chia replica, mô tả sai số và điều kiện trước khi chạy. Không thêm ngoại lệ chỉ để biến số liệu thực thành PASS.

### Bước 2: Chuẩn bị fixture cô lập và baseline

Tạo principal, report và operation key rõ nguồn gốc. Xác nhận các request đối chứng ở tải thấp. Kiểm tra bucket thực sự ở trạng thái dự kiến và trace phản ánh đúng cost/scope.

### Bước 3: Chạy test thuật toán có clock kiểm soát

Kiểm tra burst đầu, phần token lẻ, idle dài, cost sát capacity, cost vượt capacity, ranh giới window hoặc các thuộc tính tương ứng.

Các test nhỏ này giúp phân biệt lỗi công thức với lỗi chỉ xuất hiện khi phân tán hoặc quá tải.

### Bước 4: Chạy workload theo ma trận

Chạy từng nhóm có mục tiêu riêng: một key nóng, nhiều principal, nhiều tenant, cùng key idempotency, đổi key và nhiều replica.

Giữ cấu hình generator, workload, seed nếu có và tải thực tế của mỗi lượt. Seed tái tạo kế hoạch dữ liệu không tự tái tạo scheduler hoặc distributed race.

### Bước 5: Gây lỗi theo kịch bản riêng

Tạo chậm/timeout kho state, restart hoặc expiration theo khả năng fixture. Xác minh fallback cùng các quy tắc nghiệp vụ còn lại. Đừng trộn nhiều thay đổi không kiểm soát rồi không biết cơ chế nào đã quyết định admission.

### Bước 6: Dừng phát, đối soát và chờ phục hồi

Thu tác vụ client, tra cứu operation chưa rõ, xác định tác vụ server còn chạy và chờ pipeline theo deadline. Chụp dữ liệu có thẩm quyền ở mức nhất quán phù hợp.

Sau overload, probe một workload còn đủ điều kiện để xác nhận limiter refill và service vẫn tạo được công việc. Chỉ thấy 429 giảm không đủ nếu mọi request sau đó lại lỗi quyền hoặc hết quota.

### Bước 7: Báo cáo các kết luận riêng

```text
Scenario và environment:
Algorithm / capacity hoặc window / refill / cost:
Key scope / policy version / số replica:
Initial state / clock authority:
Failure policy và fallback đã kích hoạt:

Scheduled / started / not started:
HTTP outcomes / transport failures:
Admission count và tổng cost:
Denied / bypass / unknown:
Latency theo nhóm:
Job mới / replay / hiệu lực cuối:

Algorithm correctness: PASS / FAIL / INCONCLUSIVE
Business invariants: PASS / FAIL / INCONCLUSIVE
Performance: PASS / FAIL / NOT_EVALUATED
Recovery: PASS / FAIL / INCONCLUSIVE
Trace, snapshot và giới hạn bằng chứng:
```

Nếu tải thực tế thấp hơn mục tiêu, có thể đánh giá tính đúng trong phạm vi đã quan sát nhưng chưa đủ kết luận hiệu năng ở mục tiêu đó. Nếu còn operation chưa rõ, không báo đã chứng minh không có tác dụng phụ.

### Bước 8: Thu nhỏ lỗi và tạo hồi quy

Ví dụ, lỗi nhiều replica nhận dư có thể thu về B = 1, r = 0 và hai instance cùng xử lý một key trong fixture được kiểm soát. Sau đó bổ sung test race có điều phối phù hợp.

Giữ phản ví dụ nghiệp vụ và trạng thái đầu. Không chỉ lưu đồ thị RPS rồi chạy lại toàn bộ tải đến khi có một lần xanh.

## 15. Bài thực hành

Xây fixture cho endpoint xuất báo cáo:

- Hai principal A, B trong T1 và một principal C trong T2.
- Một report mỗi người có quyền, một report A không có quyền.
- Token bucket theo principal/operation, B = 2, r = 1.
- Adapter job/outbox có thể truy vấn theo operation.

Thực hiện theo thứ tự:

1. Với clock kiểm soát, gửi ba attempt cost 1 tại cùng thời điểm; kỳ vọng hai admission và một denial.
2. Tiến 0,5 giây, thử thêm một attempt; chưa đủ một token nên bị từ chối.
3. Tiến đến 1 giây tính từ đầu, thử tiếp; được nhận đúng một attempt.
4. Cho A gửi dồn, xác minh bucket của B và C vẫn hoạt động theo scope đã định nghĩa.
5. Đổi idempotency key liên tục dưới cùng principal; không làm mới bucket.
6. Gửi lại cùng operation sau khi có token; số attempt tính đúng nhưng không tạo job thứ hai.
7. Dùng report A không được quyền; admission nếu có không tạo quyền xuất dữ liệu.
8. Chạy cùng key qua hai instance, đối chiếu tổng cost với ngân sách chung.
9. Gây timeout kho trạng thái, kiểm tra fallback và phân loại kết quả chưa rõ.
10. Dừng đỉnh tải, chờ refill/phục hồi và kiểm tra request mới hợp lệ.

Sau các test nhỏ, tăng workload bằng thời gian thực với mô hình phát tải được ghi rõ. Bổ sung cost khác nhau nếu endpoint có ngữ nghĩa đó.

Mỗi lượt cần nộp:

- Hợp đồng và trạng thái bucket đầu.
- Kế hoạch cùng tải thực tế.
- Trace admission/denial và nhóm kết quả HTTP.
- Đối soát operation/job/outbox/hiệu lực.
- Oracle áp dụng và những kết luận chưa đủ bằng chứng.

Phần mở rộng: trong bản lỗi cô lập, để mỗi replica tự tạo bucket đầy. Chứng minh test phát hiện cấp vượt ngân sách chung, thu nhỏ phản ví dụ rồi khôi phục cơ chế đúng.

## 16. Checklist hoàn thành

- [ ] Thuật toán, scope, cost và ranh giới admission được định nghĩa.
- [ ] Trạng thái bucket đầu được biết, không chia sẻ vô tình với lượt khác.
- [ ] Oracle phù hợp thuật toán; không dùng envelope token bucket cho fixed window.
- [ ] Có test cấp dư và từ chối sai, không chỉ giới hạn trên.
- [ ] Clock và phần refill được tính chính xác; tránh overflow/làm tròn sai trong oracle.
- [ ] Burst thời gian thực tính cả refill, không giả định diễn ra tức thời.
- [ ] Tải dự kiến, tải đã phát và tải tới limiter được tách.
- [ ] Quyết định admission và tổng cost không suy đơn thuần từ HTTP 2xx.
- [ ] Caller không thể đổi tenant, header hoặc idempotency key để lấy bucket mới trái phép.
- [ ] Có kiểm tra nhiều principal, nhiều tenant và nhiều replica theo cam kết.
- [ ] Restart, TTL, eviction và lỗi state store có oracle/policy rõ.
- [ ] Fallback không bỏ qua quyền, phê duyệt, quota, state machine hoặc idempotency.
- [ ] Request bị limiter từ chối không tạo hiệu lực mới.
- [ ] Request được admission vẫn được kiểm tra nghiệp vụ đầy đủ.
- [ ] Retry có ngân sách; timeout được đối soát thay vì tính như denial.
- [ ] Báo cáo tách tính đúng thuật toán, nghiệp vụ, hiệu năng và phục hồi.

Rate limiter load có giá trị khi chứng minh được ngân sách được cấp cho đúng chủ thể, đúng thời gian và đúng chi phí, đồng thời phần việc đi qua vẫn tuân thủ quy tắc nghiệp vụ. Một hệ thống có thể từ chối thêm tải theo hợp đồng, nhưng không được dùng việc giới hạn request để che cấp vượt ngân sách, tạo tác dụng phụ từ request bị chặn hoặc bỏ qua quyền trên đối tượng.
