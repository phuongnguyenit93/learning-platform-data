# Kiểm thử tải nhận quyền lợi đồng thời (Concurrent claim load)

Một chương trình chỉ có 100 suất nhận ưu đãi nhưng có hàng nghìn người bấm nhận cùng lúc. API có thể trả lời nhanh và tỷ lệ HTTP 5xx thấp, trong khi thực tế đã cấp 103 suất, cho một tài khoản nhận hai lần hoặc trừ quota dù người dùng không có quyền. Những kết quả đó vi phạm quy tắc nghiệp vụ, dù biểu đồ hiệu năng có vẻ tốt.

Trong chương **Load Testing** của module Business Logic Security, concurrent claim load là kiểm thử tải cho thao tác nhiều caller cùng tranh một quyền lợi hữu hạn. Đích kiểm tra có hai phần: hệ thống giữ được **business invariants dưới tải**, và kết quả xử lý có thể được quan sát, đối soát, phục hồi trong giới hạn đã định nghĩa.

## 1. Mục tiêu và cách hiểu claim

Trong bài này, claim là thao tác một chủ thể yêu cầu nhận một quyền lợi, ví dụ mã ưu đãi, suất tham dự, lượt dùng thử hoặc phần thưởng. Không nhầm claim nghiệp vụ với thuộc tính danh tính trong token.

Sau bài học, bạn có thể:

- Thiết kế tải tập trung vào một tài nguyên nóng có số suất hữu hạn.
- Phân biệt request, ý định nhận, bản ghi cấp suất và quyền lợi được phát hành.
- Kiểm tra không vượt quota, không nhận trùng và không cấp sai đối tượng.
- Thiết kế riêng các nhóm cùng key, khác key và nhiều danh tính hợp lệ.
- Đo throughput nghiệp vụ cùng độ trễ, phản hồi giới hạn tải và kết quả chưa xác định.
- Đối soát database, outbox và hệ thống phát quyền lợi sau khi kết thúc tải.
- Đọc báo cáo mà không coi 429, timeout hay response thành công là toàn bộ sự thật.

Một load test thường không tái hiện xác định mọi lịch xen kẽ. Nó bổ sung cho test invariant, test tích hợp có điều phối và test quyền theo đối tượng; không thay thế các lớp đó.

## 2. Mô hình nghiệp vụ và invariant

### 2.1. Hợp đồng của chương trình mẫu

Fixture có một chương trình CAMPAIGN-A thuộc tenant T1:

- Đang OPEN trong suốt kịch bản cơ sở.
- Capacity C được cấp cố định trước khi chạy.
- Mỗi participant đủ điều kiện được nhận tối đa một suất trong chương trình.
- Không hủy, chuyển nhượng hoặc hoàn trả suất trong kịch bản cơ sở.
- Việc chấp nhận claim tạo bản ghi ALLOCATED đã commit; worker sau đó phát hành quyền lợi và chuyển thành ISSUED.
- Nếu phát hành gặp lỗi tạm thời, claim vẫn giữ suất ALLOCATED để retry theo chính sách, không tự biến thành suất mới.

Nếu sản phẩm có trạng thái hủy, hết hạn hoặc hoàn trả, cần mô hình riêng cho những chuyển trạng thái đó. Không loại chúng tùy tiện khỏi phép đếm để làm báo cáo đúng quota.

### 2.2. Bảo toàn số suất

Gọi:

```text
C = capacity cố định của chương trình
R = số suất còn khả dụng
G = số claim ALLOCATED hoặc ISSUED đã commit
```

Invariant:

```text
R >= 0
0 <= G <= C
R + G = C
```

Một suất ở ALLOCATED đã chiếm capacity, dù quyền lợi chưa được worker phát hành. Chỉ đếm ISSUED có thể bỏ sót việc nhiều request đã cùng được hứa cấp quá số suất.

Đồng thời:

```text
với mỗi (tenant, campaign, participant):
    có tối đa một claim được cấp trong mô hình cơ sở

mọi claim được cấp:
    thuộc đúng tenant và campaign
    gắn với participant được phép và đủ điều kiện tại ranh giới đã quy định
```

Nếu chương trình chỉ định nhóm được nhận trước, kiểm tra eligibility theo nguồn server. Một trường `eligible = true` hoặc `participantId` do client gửi không chứng minh quyền nhận.

### 2.3. Không chỉ kiểm tra counter

Counter remaining không âm chưa đủ. Hai request có thể cùng đọc 1, cùng tạo claim rồi lần lượt ghi remaining = 0. Khi đó G = 2 cho capacity bằng 1 nhưng counter vẫn không âm.

Oracle phải đối chiếu counter với bản ghi claim có thẩm quyền. Capacity kỳ vọng phải đến từ fixture hoặc ledger cấp suất được cho phép, không chỉ đọc lại một trường mà ứng dụng có thể vô tình tăng để cân số.

### 2.4. Quyền lợi phát hành không được nhân đôi

Phân biệt các đơn vị:

| Đơn vị | Ý nghĩa |
|---|---|
| Request attempt | Một lần gửi mạng, bao gồm retry |
| Ý định claim | Participant muốn nhận một suất trong campaign |
| Claim được cấp | Một bản ghi ALLOCATED/ISSUED chiếm một suất |
| Event logic | Sự kiện cấp suất, có định danh ổn định |
| Lần giao thông điệp | Có thể nhiều lần trong cơ chế at-least-once |
| Hiệu lực phát hành | Quyền lợi thực sự được tạo ở hệ thống nhận |

Một event có thể được giao lại mà không tạo quyền lợi lần hai. Vì vậy không dùng số lần gọi mạng làm đại diện duy nhất cho số hiệu lực phát hành.

## 3. API và dữ liệu khởi đầu

Ví dụ request:

```http
POST /v1/campaigns/CAMPAIGN-A/claims HTTP/1.1
Host: rewards.test
Authorization: Bearer <token-cua-participant-A>
Content-Type: application/json
Idempotency-Key: claim-A-operation-1

{}
```

Server lấy participant và scope được phép từ danh tính cùng quan hệ quyền. Ví dụ không cho client tự chọn người nhận trong body. Một API quản trị nhận hộ cần quyền và ca kiểm thử riêng.

Hợp đồng phản hồi minh họa:

| Kết quả | HTTP minh họa | Ý nghĩa |
|---|---:|---|
| GRANTED | 201 | Claim đã được cấp suất và commit |
| REPLAYED | 200 | Cùng operation đã áp dụng, trả claim cũ |
| ALREADY_CLAIMED | 409 | Key mới nhưng participant đã có claim |
| SOLD_OUT | 409 | Không còn suất có thể cấp |
| CAMPAIGN_CLOSED | 409 | Không được nhận ở trạng thái hiện tại |
| FORBIDDEN | 403 | Caller không được phép nhận |
| REQUEST_THROTTLED | 429 | Bị giới hạn request tại lớp áp dụng |

Mã cụ thể phải theo API của dự án. Nếu API trả 202 PROCESSING, chưa được tính là G chỉ từ response đó; cần truy vấn trạng thái cuối hoặc ledger để xác định có được cấp hay không.

Trong hợp đồng mẫu, một operation đã được cấp phải replay về cùng claim ID. Key mới không cho participant vượt quy tắc một suất. Khi participant đã nhận và campaign cũng hết suất, thứ tự ưu tiên giữa ALREADY_CLAIMED và SOLD_OUT phải được định nghĩa; không để oracle giả định điều chưa có trong hợp đồng.

### 3.1. Fixture tối thiểu

- Campaign mới với capacity biết trước.
- Danh sách participant đủ điều kiện, có credential hợp lệ.
- Một nhóm không đủ điều kiện và một nhóm thuộc tenant khác.
- Idempotency key có quan hệ rõ với từng participant và operation.
- Namespace dữ liệu riêng cho mỗi lần chạy.
- Adapter phát hành quyền lợi trong môi trường kiểm thử.
- Quyền quan sát claim, counter, outbox và hiệu lực phát hành.

Chạy request đối chứng ở tải thấp trước. Nếu campaign sai trạng thái hoặc token không hợp lệ, hàng nghìn phản hồi lỗi không chứng minh được tính an toàn dưới tải.

## 4. Phân biệt tải dự kiến, tải thực và hiệu lực nghiệp vụ

### 4.1. Ba mức tải cần ghi riêng

**Tải được lên lịch:** số request mà kế hoạch muốn phát ra theo thời gian.

**Tải thực sự bắt đầu:** request mà bộ phát tải đã khởi tạo và đưa vào đường gửi.

**Tải đến lớp xử lý nghiệp vụ:** request đi qua gateway, xác thực và giới hạn tải để tới thao tác claim.

Bộ phát tải có thể không theo kịp lịch. Gateway có thể trả 429 trước khi request vào service. Cả hai đều làm giảm mức cạnh tranh thực sự trên counter, dù con số cấu hình có vẻ lớn.

Khi lịch phát đã đóng và không còn phần việc chờ trong bộ lập lịch:

```text
scheduledAttempts = startedAttempts + notStartedAttempts
```

Sau khi mọi lần gọi phía client đã kết thúc:

```text
startedAttempts = httpResponsesObserved + transportFailures
```

Đây là phép đối soát của generator, không phải phương trình số claim. Một response 5xx hoặc lỗi truyền tải vẫn có thể xảy ra sau khi server commit.

### 4.2. Không suy hiệu lực từ kết quả mạng

Một request timeout không tự đồng nghĩa bị từ chối. Nó có thể chưa vào server, đang chờ khóa hoặc đã được cấp nhưng mất phản hồi.

Tương tự:

- 201 theo hợp đồng phải khớp một claim durable.
- 200 replay có thể nhiều lần cùng trỏ về một claim.
- 429 thường cho biết lớp áp dụng đã từ chối nhận thêm request, nhưng test vẫn cần hiểu vị trí áp dụng trong hệ thống.
- 5xx không được tự coi là SOLD_OUT.
- 202 chỉ phản ánh đang xử lý nếu hợp đồng nói như vậy.

Oracle cuối cùng phải dùng dữ liệu có thẩm quyền và đối soát các operation chưa rõ kết quả. Đếm `201 + 200` để ra số người được cấp sẽ tính trùng.

### 4.3. Một người dùng ảo không tự là một participant

Nếu mọi virtual user dùng cùng token, load test chủ yếu đo nhánh một participant gửi lại hoặc bị chặn trùng. Nó không đại diện hàng nghìn người đủ điều kiện cùng tranh suất.

Ngược lại, nếu mỗi request dùng participant mới, test gần như không kiểm tra idempotency hoặc uniqueness theo người nhận. Cần các nhóm tải có mục tiêu khác nhau.

## 5. Ma trận kịch bản tải

Các giá trị dưới là tham số bài tập, không phải SLO hay cấu hình khuyến nghị cho mọi hệ thống.

| Kịch bản | Dữ liệu và tải | Điều cần chứng minh |
|---|---|---|
| Một campaign, nhiều người | C = 100, 500 participant, mỗi người một key | Không cấp quá 100; không sai participant |
| Gửi lại cùng operation | 50 participant, mỗi người lặp một key 10 lần | Mỗi participant tối đa một claim, replay đúng ID |
| Đổi key để nhận thêm | 50 participant, mỗi người dùng 10 key khác nhau | Uniqueness nghiệp vụ không phụ thuộc key |
| Nhóm hỗn hợp | Caller hợp lệ, không đủ điều kiện, khác tenant | Không cấp sai quyền, không rò kết quả |
| Nhiều replica | Một campaign đi qua các instance | Không dựa vào khóa trong bộ nhớ một process |
| Nhiều campaign độc lập | Nhiều bucket capacity tách biệt | Không trộn quota hoặc khóa toàn hệ thống quá rộng |
| Mất phản hồi và retry | Một số request commit nhưng mất response | Không cấp hai lần, đối soát được kết quả |
| Tăng tải vượt khả năng | Giữ campaign và pool quan sát được | Hệ thống suy giảm có kiểm soát, invariant vẫn đúng |

### 5.1. Tách kịch bản có đủ quota và tranh quota

Với C lớn hơn hoặc bằng số participant, có thể kiểm tra đường cấp thành công dài hơn và tốc độ phát hành quyền lợi.

Với C nhỏ hơn số participant, phần lớn nửa sau lần chạy có thể chỉ gọi nhánh SOLD_OUT. Đây là hành vi cần đo nhưng không phản ánh throughput cấp suất khi còn tài nguyên.

Ghi thời điểm đạt hết suất và phân tích riêng giai đoạn trước/sau. Nếu muốn lặp nhiều đợt tranh suất, tạo campaign mới cho mỗi đợt; không reset counter đang có claim cũ mà không mô hình hóa dữ liệu đó.

### 5.2. Không tự áp kỳ vọng công bằng chưa có

Concurrent claim không mặc định đảm bảo first-come-first-served theo thời điểm bấm ở client. Mạng, gateway và scheduler có thể đổi thứ tự.

Chỉ kiểm tra FIFO, chia đều theo tenant hoặc ưu tiên một nhóm nếu sản phẩm có cam kết và mốc sắp thứ tự cụ thể. Không gọi việc một participant tới sau ở phía client thắng là lỗi nghiệp vụ chỉ vì thứ tự log máy phát tải.

## 6. Thiết kế bộ phát tải

### 6.1. Tải theo số tác vụ đang chạy và tải theo lịch đến

**Mô hình đóng:** giữ tối đa W request đang chạy. Khi một request kết thúc, phát request kế tiếp. Khi hệ thống chậm, tốc độ bắt đầu request giảm theo.

**Mô hình mở:** phát request theo lịch đến đã chọn, ví dụ một tốc độ mục tiêu hoặc một đợt tăng đột ngột. Khi server chậm, nhu cầu request vẫn tiếp tục theo lịch, trong giới hạn tài nguyên của generator.

Hai mô hình trả lời câu hỏi khác nhau:

- Mô hình đóng giúp tạo một mức cạnh tranh có giới hạn và dễ thu hết tác vụ.
- Mô hình mở giúp quan sát phản ứng với nhu cầu đến độc lập, nhưng phải ghi cả lần không phát được và chính sách backlog.

Không gọi một vòng lặp có W worker là “đã giữ đúng X request/giây” nếu không đo tốc độ thực tế. Không cho mô hình mở tích lũy hàng đợi vô hạn rồi phát dồn mà không ghi nhận độ trễ lập lịch.

Ở trạng thái ổn định, quan hệ gần đúng giữa số request đang xử lý, tốc độ được nhận và thời gian trung bình có thể giúp kiểm tra tính hợp lý:

```text
inFlight trung bình ≈ throughput thực tế × thời gian trung bình
```

Quan hệ này cần cùng một ranh giới đo và điều kiện ổn định; không thay thời gian trung bình bằng p95 rồi coi là đẳng thức, cũng không dùng nó để dự đoán chính xác một đợt burst ngắn.

### 6.2. Giới hạn tài nguyên phía generator

Đặt rõ:

- Số request tối đa đang chạy.
- Thời lượng hoặc số attempt tối đa.
- Timeout cho kết nối, request và bước đối soát.
- Cách xử lý lịch đến muộn: bỏ lượt, đưa vào backlog có giới hạn hoặc ghi trễ.
- Số lần retry và ngân sách retry.
- Giới hạn lượng trace để không làm generator nghẽn vì ghi log.

Theo dõi CPU, bộ nhớ, connection pool và lỗi của generator. Nếu generator chỉ phát được một phần kế hoạch, kết quả vẫn hữu ích nhưng phải báo tải thực tế.

### 6.3. Pseudocode cho một đợt cạnh tranh có cửa sổ giới hạn

```text
plan = danh sách attempt, đã gắn participant và key
inFlight = tập tác vụ đang chạy
observations = nơi lưu kết quả từng attempt

phát tối đa W attempt đầu

khi còn attempt chưa phát hoặc còn tác vụ:
    chờ một tác vụ hoàn tất trong deadline
    lưu response hoặc exception với attemptId
    bỏ tác vụ khỏi inFlight
    nếu còn attempt và chưa hết ngân sách:
        phát attempt kế tiếp

ngừng tạo attempt mới
thu tất cả tác vụ còn lại hoặc đánh dấu chưa rõ kết quả
đối soát operation với server
chờ pipeline liên quan kết thúc hoặc báo chưa hội tụ
đọc snapshot nghiệp vụ cuối
```

Không bỏ qua exception trong future. Một timeout của harness không phải SOLD_OUT, và hủy future không đảm bảo request phía server đã bị hủy.

### 6.4. Tạo burst có chủ đích

Có thể dùng start gate để đợt đầu xuất phát gần nhau hoặc điều khiển arrival schedule. Điều đó gây áp lực cạnh tranh nhưng không bảo đảm request cùng đi tới câu cập nhật quota ở một thời điểm.

Nếu cần chứng minh một lỗi đọc–ghi cụ thể, bổ sung test tích hợp có điều phối tại ranh giới phù hợp. Không tăng W mãi để thay thế việc hiểu cửa sổ race.

## 7. Ví dụ Java: tạo kế hoạch claim với quan hệ key rõ ràng

Đoạn mã Java 17 chỉ tạo dữ liệu cho generator. Nó không gửi HTTP và không tự là một load runner. Alias participant là danh tính giả lập trong fixture, được adapter ánh xạ sang credential hợp lệ; không lấy alias làm trường người nhận tùy ý trong body.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Random;

enum ClaimPattern {
    UNIQUE_PARTICIPANTS,
    REPEAT_SAME_KEY,
    REPEAT_DIFFERENT_KEYS
}

record ClaimAttempt(
        String attemptId,
        String participantAlias,
        String campaignId,
        String idempotencyKey) {}

final class ClaimPlans {
    static List<ClaimAttempt> build(
            String runId,
            String campaignId,
            List<String> participants,
            int copies,
            ClaimPattern pattern,
            long shuffleSeed) {

        if (copies <= 0) {
            throw new IllegalArgumentException("copies must be positive");
        }
        if (new HashSet<>(participants).size() != participants.size()) {
            throw new IllegalArgumentException("participant aliases must be unique");
        }
        if (pattern == ClaimPattern.UNIQUE_PARTICIPANTS && copies != 1) {
            throw new IllegalArgumentException("unique pattern requires one attempt");
        }

        List<ClaimAttempt> attempts = new ArrayList<>();
        int sequence = 0;

        for (int actorIndex = 0; actorIndex < participants.size(); actorIndex++) {
            String participant = participants.get(actorIndex);
            String operationKey = runId + "-actor-" + actorIndex + "-claim";

            for (int copy = 0; copy < copies; copy++) {
                String key = pattern == ClaimPattern.REPEAT_DIFFERENT_KEYS
                        ? operationKey + "-copy-" + copy
                        : operationKey;

                attempts.add(new ClaimAttempt(
                        runId + "-attempt-" + sequence++,
                        participant,
                        campaignId,
                        key));
            }
        }

        Collections.shuffle(attempts, new Random(shuffleSeed));
        return List.copyOf(attempts);
    }
}
```

Trong fixture, runId phải mới cho lần chạy mới và phù hợp định dạng header mà API nhận. Giữ nguyên key giữa các lần gửi lại của cùng operation. attemptId thì khác nhau để đối soát từng lần gọi.

Một shuffle seed giúp tái tạo thứ tự của kế hoạch cùng đầu vào. Nó không tự tái tạo lịch thread, thứ tự khóa hoặc routing qua replica. Trace cần giữ cả cấu hình, kế hoạch và kết quả quan sát.

Không tạo key ngẫu nhiên mới bên trong mỗi lần retry nếu mục tiêu là thử cùng operation. Cũng không dùng cùng key cho mọi participant nếu điều đó không tương ứng kịch bản scope đang kiểm tra.

## 8. Oracle dữ liệu sau tải

### 8.1. Chọn mốc đọc nhất quán

Trước khi chụp dữ liệu cuối:

1. Dừng phát attempt mới.
2. Thu kết quả client và ghi danh sách còn chưa rõ.
3. Xác định các request phía server có thể còn chạy, theo correlation/operation của lần thử.
4. Đối soát qua API tra cứu hoặc nguồn có thẩm quyền.
5. Chờ worker phát hành thuộc fixture đến trạng thái được định nghĩa, trong deadline.
6. Đọc counter, claim và ledger bằng snapshot nhất quán thích hợp.

Nếu chưa xác định được request hoặc worker đã kết thúc, không cleanup rồi báo pass. Tác vụ cũ có thể commit sau snapshot hoặc sau khi campaign đã được tái dùng.

Một transaction đọc mới không tự bảo đảm mọi truy vấn trong nó thấy cùng snapshot trên mọi database. Chọn mức nhất quán hoặc cách trích xuất theo mốc phù hợp với hệ quản trị và kiến trúc đang kiểm thử.

### 8.2. Đối chiếu capacity và claim

Ví dụ truy vấn minh họa, dùng schema giả lập:

```sql
SELECT
    p.tenant_id,
    p.campaign_id,
    p.capacity,
    p.remaining,
    COUNT(c.claim_id) AS granted_count
FROM campaign p
LEFT JOIN campaign_claim c
    ON c.tenant_id = p.tenant_id
   AND c.campaign_id = p.campaign_id
   AND c.status IN ('ALLOCATED', 'ISSUED')
WHERE p.tenant_id = :tenant_id
  AND p.campaign_id = :campaign_id
GROUP BY
    p.tenant_id, p.campaign_id, p.capacity, p.remaining;
```

Oracle kiểm tra capacity bằng giá trị fixture đã cấp, remaining không âm và `remaining + granted_count == expectedCapacity`. Dùng `COUNT(c.claim_id)` thay vì `COUNT(*)` để campaign chưa có claim không bị đếm thành một do LEFT JOIN.

Phạm vi phải bao gồm đúng dữ liệu của lần chạy. Không lọc chỉ theo request nhận được 201, vì như vậy sẽ bỏ sót claim đã commit nhưng client timeout.

### 8.3. Tìm participant nhận trùng

```sql
SELECT
    tenant_id,
    campaign_id,
    participant_id,
    COUNT(*) AS granted_per_participant
FROM campaign_claim
WHERE tenant_id = :tenant_id
  AND campaign_id = :campaign_id
  AND status IN ('ALLOCATED', 'ISSUED')
GROUP BY tenant_id, campaign_id, participant_id
HAVING COUNT(*) > 1;
```

Kết quả phải rỗng trong mô hình cơ sở. Unique constraint phù hợp có thể ngăn lỗi, nhưng test vẫn cần kiểm tra ứng dụng xử lý xung đột mà không trả thành công sai hoặc để lại outbox mồ côi.

### 8.4. Đối chiếu danh tính và quyền

So tập participant được cấp với tập đủ điều kiện của fixture, kiểm tra tenant/campaign của từng claim. Tổng đúng 100 vẫn có thể sai nếu một caller không có quyền nhận thay một người hợp lệ.

Thêm các kiểm tra:

- Response của A không tham chiếu claim thuộc B.
- Cùng chuỗi key ở tenant khác không lấy lại kết quả T1.
- Caller không có quyền không tạo claim hoặc quyền lợi, kể cả lúc campaign còn suất.
- Một claim không trỏ sang campaign không tồn tại hoặc sai tenant.

Ở tải cao, caller trái quyền có thể bị rate limit trước khi tới nhánh xét quyền. Nhóm đó kiểm tra được admission tại ranh giới đã quan sát nhưng chưa chứng minh toàn bộ authorization. Giữ test quyền riêng ở mức tải đủ để đi tới nhánh nghiệp vụ.

### 8.5. Đối chiếu outbox và hiệu lực phát hành

Với thiết kế một event cấp suất cho mỗi claim:

```text
mỗi claim được cấp có đúng một event logic ClaimAllocated
event gắn đúng claim, tenant và participant
không có event cấp suất cho thao tác bị rollback
mỗi claim có tối đa một quyền lợi thực sự được phát hành
```

Đến mốc hoàn tất phát hành theo hợp đồng, các claim cần hội tụ tới ISSUED hoặc trạng thái cần xử lý đã được báo rõ. Không đòi tất cả ISSUED ngay sau response nếu pipeline là bất đồng bộ.

Đếm claim, event và quyền lợi bằng các tập hoặc truy vấn riêng trước khi đối chiếu. Join nhiều bảng một-nhiều rồi COUNT có thể nhân số dòng, làm oracle tự báo trùng sai.

## 9. Đo hiệu năng mà vẫn nhìn thấy đúng nghiệp vụ

### 9.1. Các nhóm chỉ số cần tách

| Nhóm | Chỉ số ví dụ | Câu hỏi trả lời |
|---|---|---|
| Generator | Scheduled, started, not started, scheduler lag | Có thực sự tạo được tải dự kiến không? |
| HTTP | RPS, latency theo kết quả, transport error | Người gọi quan sát điều gì? |
| Admission | Request bị giới hạn, vào service, queue wait | Bao nhiêu tải tới phần tranh quota? |
| Nghiệp vụ | Claim mới/giây, replay, sold out, nhận trùng | Bao nhiêu quyền lợi được cấp hợp lệ? |
| Database | Lock wait, transaction retry, deadlock, pool wait | Tắc nghẽn và xung đột ở đâu? |
| Pipeline | Outbox lag, thời gian cấp đến phát hành, dedupe hit | Hiệu lực cuối có theo kịp không? |
| Tính đúng | Oversubscription, sai scope, unknown còn lại | Quy tắc có được giữ và đối soát được không? |

Độ trễ nên chia ít nhất theo GRANTED, REPLAYED, SOLD_OUT, throttled và lỗi hạ tầng. Khi đã hết suất, phản hồi SOLD_OUT nhanh có thể kéo p95 tổng xuống, che việc đường cấp suất rất chậm.

### 9.2. Throughput request và throughput quyền lợi

```text
requestThroughput = số attempt có kết quả / khoảng đo tương ứng
grantThroughput = số claim mới durable / khoảng đo tương ứng
```

Ghi rõ mẫu số thời gian: cả đợt chạy, giai đoạn còn suất hay cửa sổ ổn định. Khi campaign hết suất, grantThroughput có thể về 0 dù requestThroughput vẫn cao. Đây không tự là lỗi hiệu năng.

Đo riêng thời gian từ chấp nhận đến phát hành. Ưu tiên timestamp có quan hệ đáng tin cậy hoặc phép đo cùng một clock; không trừ tùy tiện đồng hồ trên hai máy chưa được đồng bộ để kết luận độ trễ.

### 9.3. Ngưỡng chấp nhận

Các invariant an toàn như không cấp quá capacity hoặc không cấp sai tenant không nên được thay bằng tỷ lệ lỗi cho phép. Một trường hợp vượt quota vẫn là lỗi quy tắc trong mô hình này.

Các ngưỡng p95, thời gian đối soát, tỷ lệ lỗi kỹ thuật và lag pipeline phải do yêu cầu hệ thống xác định. Những con số trong bài tập không phải ngưỡng áp dụng sẵn.

Nếu tất cả request đều bị 429 thì quota có thể không bị phá, nhưng chưa đủ bằng chứng năng lực xử lý claim. Cần báo đồng thời tính đúng, tải đã vào service và mục tiêu hiệu năng có đạt không.

## 10. Quá tải, retry và giảm tải có kiểm soát

### 10.1. Giới hạn tải không thay thế tính nguyên tử

Rate limit có thể giảm số request tới service, nhưng vẫn có thể cho hai request cùng tranh suất cuối. Backend cần cơ chế bảo vệ quota, uniqueness và transaction phù hợp.

Một hướng triển khai là cập nhật remaining có điều kiện, tạo claim và outbox trong cùng transaction, kèm ràng buộc duy nhất theo participant. Load test không mặc định cách này đã được cài đúng; oracle phải kiểm chứng kết quả sau cả xung đột và rollback.

Nếu INSERT claim thất bại vì participant đã nhận, phần trừ remaining phải được rollback hoặc không xảy ra. Không được mất suất chỉ vì người dùng đổi key rồi bị phát hiện trùng muộn.

### 10.2. Kiểm soát retry storm

Retry phải phân biệt:

- SOLD_OUT hoặc FORBIDDEN là kết quả nghiệp vụ, không retry liên tục để hy vọng vượt quy tắc.
- Lỗi tạm thời có thể retry theo chính sách và ngân sách đã định nghĩa.
- Kết quả chưa rõ sau mất phản hồi phải giữ key của operation cũ khi giao thức yêu cầu.
- Gợi ý chờ hoặc trạng thái đang xử lý cần được tôn trọng theo hợp đồng.

Tách lượt chạy không retry và lượt chạy có chính sách retry. Ghi request gốc cùng request phát sinh để không gọi một đợt có retry storm là cùng mức tải đầu vào.

### 10.3. Kiểm tra sau khi tải giảm

Sau đỉnh tải, quan sát:

- Queue và lock wait có giảm về trạng thái bình thường không?
- Outbox có tiếp tục được xử lý không?
- Operation chưa rõ có được giải quyết trong deadline không?
- Request mới hợp lệ trên campaign khác có được xử lý không?
- Có worker rò rỉ hoặc transaction giữ khóa bất thường không?

Một campaign đã hết suất chỉ trả SOLD_OUT không đủ để đánh giá phục hồi đường cấp mới. Dùng một fixture campaign khác còn suất cho phần kiểm tra đó.

## 11. Ví dụ đối soát một lượt chạy

Giả sử kịch bản có capacity 100, 500 participant đủ điều kiện, mỗi người gửi một attempt, không tự retry.

### 11.1. Số liệu client

| Quan sát | Số lượng |
|---|---:|
| Attempt được lên lịch | 500 |
| Attempt thực sự bắt đầu | 500 |
| HTTP 201 GRANTED | 98 |
| HTTP 409 SOLD_OUT | 397 |
| HTTP 429 REQUEST_THROTTLED | 3 |
| Lỗi truyền tải, chưa biết hiệu lực | 2 |

Số response quan sát được là 498; cộng 2 lỗi truyền tải bằng 500 attempt đã bắt đầu. Đây mới là đối soát generator.

Không thể kết luận chỉ có 98 suất được cấp. Cũng không thể lấy 2 timeout làm hai trường hợp SOLD_OUT.

### 11.2. Dữ liệu server

Sau khi xác định các request liên quan đã kết thúc:

```text
capacity = 100
remaining = 0
claim ALLOCATED hoặc ISSUED = 100
participant được cấp khác nhau = 100
claim sai tenant/eligibility = 0
```

Hai participant gặp lỗi truyền tải được tra cứu bằng danh tính đúng và đều có claim đã commit. Chúng là hai kết quả được cấp nhưng mất phản hồi; không tạo lại operation để “bù” vì nghĩ request thất bại.

Khi đối chiếu:

- 98 response GRANTED trỏ tới 98 claim đúng.
- Hai lỗi truyền tải trỏ tới hai claim còn lại.
- 397 participant nhận SOLD_OUT và 3 participant bị throttled không có claim trong lượt chạy này.
- Không có claim thừa, thiếu hoặc sai người.

Như vậy phần cấp suất thỏa invariant. Hiệu năng chỉ được kết luận theo tải thực tế, latency và mức tải đã vào service, không chỉ từ việc cấp đủ 100.

### 11.3. Dữ liệu phát hành

Ngay sau phần claim có thể có 98 ISSUED và 2 ALLOCATED. Nếu worker vẫn đang xử lý trong thời gian hợp đồng cho phép, chưa thể kết luận lỗi phát hành hoặc báo đã hoàn tất toàn bộ.

Tới deadline đối soát, giả sử:

```text
claim ISSUED = 100
event logic ClaimAllocated = 100
quyền lợi thực sự khác nhau = 100
lần giao tới adapter = 104
operation chưa rõ = 0
```

Bốn lần giao thêm là retry của cùng event và không tạo quyền lợi mới. Với mô hình at-least-once có dedupe đúng, số 104 không tự là lỗi nhân đôi.

Nếu tới deadline vẫn còn hai claim ALLOCATED, cần báo phần phát hành chưa đạt yêu cầu hoặc chưa hội tụ. Việc quota đúng không làm mất vấn đề đó.

### 11.4. Những số liệu trông gần đúng nhưng vẫn fail

| Kết quả | Vì sao không đạt |
|---|---|
| remaining = 0, G = 101, C = 100 | Vượt capacity và phá bảo toàn |
| G = 100 nhưng chỉ 99 participant khác nhau | Có người nhận hai suất |
| G = 100, trong đó một người không đủ điều kiện | Phân quyền/eligibility sai |
| G = 99, remaining = 0, không có trạng thái giữ nào khác | Một suất bị mất khỏi mô hình |
| G = 100, quyền lợi thực tế = 101 | Pipeline tạo hiệu lực trùng |
| Tất cả response đã thu nhưng một request server còn chạy | Snapshot cuối chưa đủ điều kiện kết luận |

## 12. Nhiều replica, nhiều tenant và tài nguyên nóng

### 12.1. Không để một process che lỗi

Một lock trong bộ nhớ có thể giữ đúng quota khi mọi request vào một instance nhưng mất tác dụng khi replica khác cùng xử lý.

Lượt chạy nhiều instance cần:

- Xác nhận request thực sự được phân bố tới các instance.
- Các instance dùng chung nguồn quota và cơ chế nhất quán theo thiết kế.
- Scope idempotency và uniqueness có hiệu lực qua các instance.
- Trace đủ để biết retry có thể đã đổi instance.

Sticky session có thể làm phân bố khác dự kiến. Việc cấu hình nhiều replica không chứng minh request đã tạo cạnh tranh giữa chúng.

### 12.2. Một campaign nóng và nhiều campaign độc lập

Hai kịch bản này cần đo riêng:

- Một campaign nóng cho thấy tranh khóa, tranh counter và suất cuối.
- Nhiều campaign độc lập cho thấy khả năng xử lý đồng thời trên các bucket khác nhau.

Tổng throughput cao trên nhiều campaign không chứng minh một campaign nóng giữ được invariant. Ngược lại, khóa toàn bộ tenant hoặc service có thể giữ đúng một campaign nhưng làm những campaign độc lập chờ không cần thiết.

Đối chiếu correctness theo từng bucket trước rồi mới tổng hợp. Nếu campaign X bị cấp thừa một suất còn Y bị mất một suất, tổng toàn hệ thống vẫn có thể bằng tổng capacity.

### 12.3. Cùng key ở scope khác

Cho participant thuộc hai tenant/campaign hợp lệ sử dụng cùng chuỗi key trong các scope độc lập theo hợp đồng. Mỗi scope phải giữ quota và kết quả của mình.

Nếu sản phẩm quy định key có phạm vi rộng hơn, generator phải tuân thủ định nghĩa đó. Điều cần kiểm tra là không có việc vô tình trả dữ liệu chéo hoặc dùng dedupe sai phạm vi.

### 12.4. Eligibility thay đổi trong lúc tải

Đây là kịch bản mở rộng: một participant bị loại khỏi danh sách hoặc campaign chuyển CLOSED trong khi request đang xử lý.

Cần xác định mốc hiệu lực. Ví dụ, claim chỉ hợp lệ nếu trạng thái OPEN và eligibility còn hiệu lực tại ranh giới cập nhật được bảo vệ. Khi đó những request dựa trên dữ liệu cũ không được tự commit sau thay đổi mà không kiểm tra lại.

Một chính sách khác có thể cho phép operation đã được chấp nhận hoàn tất. Không dùng thời điểm response phía client làm mốc thay thế nếu hệ thống không cam kết như vậy.

Giữ kịch bản đóng campaign/đổi eligibility riêng với đợt capacity cơ sở để oracle không bị trộn nhiều quy tắc chưa mô tả.

## 13. Quan sát và thu thập bằng chứng

### 13.1. Liên kết attempt với operation và claim

Một trace hữu ích lưu:

```text
runId
scenarioId
attemptId
participantAlias
campaignAlias
idempotencyKey hoặc fingerprint an toàn để đối soát
thời điểm bắt đầu/kết thúc theo clock của generator
HTTP status và business code hoặc exception
operationId/claimId trả về
instance xử lý nếu có
kết quả tra cứu cuối
```

Không log credential hay token. Dùng alias của fixture khi có thể. Các ID nhiều giá trị nên đi vào trace/log phù hợp; không biến mọi attemptId hoặc participantId thành nhãn metric không giới hạn.

### 13.2. Bằng chứng ở server

Thu các chỉ dấu liên quan, tùy khả năng hệ thống:

- Số request qua admission và tới handler.
- Số dòng cập nhật quota, kết quả unique conflict và số lần retry transaction.
- Lock wait, thời gian chờ connection và lỗi transaction.
- Claim/event được commit và operation kết thúc.
- Trạng thái publisher, consumer, dedupe và hiệu lực phát hành.

Không suy thứ tự toàn cục chỉ bằng timestamp từ các máy khác nhau. Một quan hệ như “operation đã commit trước khi client retry” cần tín hiệu hoặc dữ liệu có thể xác minh, không chỉ hai dòng log có đồng hồ gần nhau.

### 13.3. Khi có lỗi, giữ phản ví dụ đủ nhỏ

Nếu phát hiện cấp 101 suất, giữ campaign và ledger của lần chạy, cùng các attempt tranh các suất cuối. Sau đó thu nhỏ số participant hoặc dùng fixture capacity 1 để tái hiện cửa sổ lỗi có chủ đích.

Không chỉ lưu ảnh đồ thị latency. Một lỗi logic cần bằng chứng về quota, danh tính, trạng thái và operation đã tạo hiệu lực. Kết quả load test có thể dẫn tới một test hồi quy nhỏ, xác định hơn cho nguyên nhân đã tìm thấy.

## 14. Quy trình thực hiện và báo cáo

### Bước 1: Chốt hợp đồng

Ghi scope, capacity, eligibility, giới hạn mỗi participant, trạng thái chiếm suất, chính sách replay và mốc phát hành. Định nghĩa kết quả nào cần tra cứu thêm.

### Bước 2: Kiểm tra fixture ở tải thấp

Chạy một claim hợp lệ, một replay, một key mới cùng participant và một caller trái quyền trên các dữ liệu phù hợp. Kiểm tra generator gửi đúng danh tính và key.

### Bước 3: Chạy các kịch bản riêng

Bắt đầu với dữ liệu đủ quota, sau đó tranh quota, cùng key, khác key và các phạm vi độc lập. Ghi cấu hình cùng tải thực tế mỗi lượt.

Không gộp mọi kịch bản thành một tỷ lệ “thành công” duy nhất. Chẳng hạn SOLD_OUT đúng nghiệp vụ khác với 5xx, và replay đúng khác với cấp claim mới.

### Bước 4: Dừng phát tải và đối soát

Thu tác vụ, giải quyết kết quả chưa rõ, chờ pipeline theo deadline rồi chụp snapshot nhất quán. Chỉ cleanup khi dữ liệu và worker của lượt chạy đã được kết toán hoặc cô lập.

Nếu chưa thể xác định hiệu lực, giữ trạng thái chưa xác định trong báo cáo. Không tạo campaign mới với cùng namespace để che dữ liệu cũ.

### Bước 5: Báo cáo theo ba kết luận

**Tính đúng nghiệp vụ:** quota, uniqueness, quyền, state machine, idempotency và hiệu lực bên ngoài có đạt không?

**Hiệu năng ở tải thực tế:** mức tải, latency theo kết quả, số request tới service và thời gian phát hành có đạt yêu cầu đã chốt không?

**Khả năng phục hồi và đối soát:** sau overload hoặc mất phản hồi, hệ thống có giải quyết hết operation, drain pipeline và trở lại trạng thái sử dụng được không?

Ví dụ khung báo cáo:

```text
Scenario:
Environment và số replica:
Capacity / participant / pattern key:
Mô hình phát tải / in-flight cap / duration / retry policy:
Scheduled / started / not started:
HTTP outcomes / transport failures:
Request thực tới service:
Latency theo nhóm kết quả:

Expected capacity / remaining / granted / distinct participants:
Claim sai quyền hoặc sai scope:
Logical events / issued effects / duplicate effects:
Unknown operations trước và sau đối soát:
Thời gian pipeline hội tụ:

Correctness: PASS / FAIL / INCONCLUSIVE
Performance: PASS / FAIL / NOT_EVALUATED
Recovery: PASS / FAIL / INCONCLUSIVE
Trace và snapshot liên quan:
```

Một lượt có quota đúng nhưng generator không đạt tải mục tiêu có thể PASS phần correctness trong phạm vi quan sát và chưa đủ kết luận performance. Một lượt còn operation không rõ hiệu lực chưa đủ để PASS correctness đầu cuối.

### Bước 6: Chuyển lỗi thành hồi quy

Giữ invariant và phản ví dụ. Thêm test tích hợp có điều phối cho race đã biết, test uniqueness cho khác key và test pipeline cho giao lại event nếu cần. Sau khi sửa, chạy lại kịch bản liên quan để xác minh dưới tải thực.

## 15. Bài thực hành

Tạo campaign capacity 20 và 100 participant đủ điều kiện trong môi trường kiểm thử. Dùng adapter phát hành giả lập có ghi nhận hiệu lực theo claim ID.

Thực hiện:

1. Chạy mỗi participant một attempt, giới hạn in-flight được cấu hình rõ.
2. Xác minh có tối đa 20 claim, không trùng người nhận và remaining cộng G bằng 20.
3. Dùng fixture mới, cho 10 participant mỗi người lặp cùng key 5 lần.
4. Dùng fixture mới, cho 10 participant mỗi người dùng 5 key khác nhau.
5. Thêm caller không đủ điều kiện và caller tenant khác, kiểm tra không có hiệu lực sai.
6. Phân bố request qua hai instance, xác nhận routing thực tế.
7. Mô phỏng mất phản hồi sau commit cho một số operation và đối soát bằng key/danh tính đúng.
8. Giao lại một số event phát hành, kiểm tra chỉ một quyền lợi cho mỗi claim.
9. Tăng tải tới khi có admission limit hoặc nghẽn, rồi kiểm tra phục hồi bằng campaign mới còn suất.

Với mỗi lượt, ghi tải thực tế, kết quả client, snapshot cuối, số quyền lợi được phát hành và danh sách operation chưa rõ. Không gộp các fixture vào cùng phép đếm capacity.

Phần mở rộng: sinh capacity nhỏ và số participant/attempt từ một seed. Khi tìm được lỗi, rút về kịch bản tranh suất cuối thay vì chỉ tăng số request trong những lần chạy sau.

## 16. Checklist hoàn thành

- [ ] Claim, capacity, trạng thái chiếm suất và quyền nhận được định nghĩa rõ.
- [ ] Counter được đối chiếu với claim durable, không chỉ kiểm tra không âm.
- [ ] Capacity kỳ vọng độc lập với giá trị ứng dụng có thể sửa sai.
- [ ] Participant thật sự khác nhau trong nhóm tải nhiều người.
- [ ] Cùng key và khác key được kiểm tra thành các kịch bản riêng.
- [ ] Key được giữ nguyên cho retry của cùng operation theo hợp đồng.
- [ ] Có kiểm tra caller không đủ điều kiện và khác tenant.
- [ ] Tải lên lịch, tải đã phát và tải tới service được phân biệt.
- [ ] Generator có giới hạn in-flight, deadline, retry budget và ghi nhận phần không phát được.
- [ ] Latency được chia theo kết quả và giai đoạn còn/hết suất.
- [ ] 429, 5xx và timeout không bị gộp thành từ chối nghiệp vụ.
- [ ] Mọi operation chưa rõ được đối soát hoặc báo chưa xác định.
- [ ] Snapshot cuối được đọc sau khi tác vụ liên quan kết thúc và với độ nhất quán phù hợp.
- [ ] Outbox/event logic được phân biệt với số lần giao và hiệu lực phát hành.
- [ ] Nhiều replica và nhiều bucket không che lỗi scope hoặc khóa cục bộ.
- [ ] Báo cáo tách tính đúng, hiệu năng và phục hồi; lỗi được lưu thành hồi quy.

Concurrent claim load chỉ có ý nghĩa bảo mật khi nối được tải đầu vào với quyền lợi thực sự được cấp. Hệ thống có thể chậm, từ chối thêm tải hoặc yêu cầu tra cứu lại theo hợp đồng, nhưng không được tạo thêm suất, cấp sai đối tượng hay biến một yêu cầu gửi lại thành quyền lợi mới.
