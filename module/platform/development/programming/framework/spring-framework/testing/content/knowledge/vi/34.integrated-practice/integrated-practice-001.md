# Xây dựng ma trận rủi ro cho một luồng tạo tài nguyên

## Mục tiêu: kiểm thử theo rủi ro của luồng tạo tài nguyên

Một luồng tạo tài nguyên trong ứng dụng Spring thường đi qua nhiều lớp: HTTP controller, validation, authorization, service nghiệp vụ, database, dịch vụ bên ngoài, message broker và một worker xử lý bất đồng bộ. Một request có thể trả về thành công nhưng tài nguyên chưa được tạo đầy đủ; ngược lại, tài nguyên bên ngoài có thể đã được tạo dù transaction database thất bại.

Nếu chỉ viết một test cho trường hợp tạo thành công, nhiều lỗi quan trọng vẫn có thể lọt qua: hai request đồng thời tạo trùng tài nguyên, người dùng tạo tài nguyên vượt quota, provider timeout sau khi đã tạo resource, event bị mất, message được xử lý hai lần hoặc dữ liệu của test này bị test khác xóa.

Ma trận rủi ro giúp nhóm kiểm thử trả lời ba câu hỏi:

1. Những điều gì có thể sai trong từng bước của luồng?
2. Nếu xảy ra, hậu quả đối với dữ liệu, bảo mật hoặc người dùng nghiêm trọng đến đâu?
3. Test nào và cơ chế kiểm soát nào cung cấp bằng chứng rằng rủi ro đã được xử lý?

Ma trận không thay thế test case. Nó là cách nối yêu cầu nghiệp vụ, failure mode, mức ưu tiên và chiến lược kiểm thử thành một kế hoạch có thể xem xét được.

## Chọn một luồng mẫu làm cơ sở

Để minh họa, giả sử hệ thống cung cấp API tạo Workspace. Workspace là tài nguyên của một người dùng hoặc tổ chức; sau khi lưu metadata, hệ thống cần tạo vùng lưu trữ ở một provider bên ngoài. Việc provisioning có thể mất thời gian nên được xử lý bất đồng bộ.

Request mẫu:

~~~http
POST /api/workspaces
Authorization: Bearer <access-token>
Idempotency-Key: 9a4f...
Content-Type: application/json

{
  "name": "finance-reports",
  "region": "ap-southeast-1",
  "plan": "STANDARD"
}
~~~

Một luồng điển hình:

~~~text
HTTP request
    |
    v
Authentication và authorization
    |
    v
Validate payload, region, plan và quota
    |
    v
Kiểm tra idempotency key và tên duy nhất
    |
    v
Tạo Workspace ở trạng thái PENDING
    |
    v
Ghi outbox event trong cùng transaction
    |
    v
Trả HTTP 202 + resource id
    |
    v
Outbox publisher / message broker
    |
    v
Provisioning worker gọi provider bên ngoài
    |
    +------ thành công ------> cập nhật READY
    |
    +------ thất bại --------> retry hoặc FAILED
~~~

Ví dụ này giả định API trả 202 Accepted khi đã nhận yêu cầu tạo tài nguyên nhưng provisioning chưa hoàn tất. Nếu ứng dụng tạo tài nguyên đồng bộ và trả 201 Created, có thể giữ nguyên cách lập ma trận nhưng điều chỉnh trạng thái trung gian, điểm xác nhận và kỳ vọng HTTP cho phù hợp.

Ranh giới trách nhiệm cần rõ:

- Controller xử lý giao thức HTTP, request validation và response.
- Service quyết định quyền tạo, quota, uniqueness, idempotency và chuyển trạng thái nghiệp vụ.
- Repository lưu metadata và outbox.
- Adapter giao tiếp với provider hoặc broker.
- Worker điều phối provisioning, retry và cập nhật trạng thái.

Không nhất thiết mỗi lớp phải có một test class riêng. Ranh giới test nên theo hành vi cần xác nhận và mức rủi ro, không theo số lượng class trong code.

## Xác định thang điểm rủi ro

Một cách đơn giản là chấm mỗi rủi ro theo hai trục:

- **Probability (P):** khả năng lỗi xảy ra trong điều kiện vận hành hoặc thay đổi code dự kiến.
- **Impact (I):** mức hậu quả nếu lỗi xảy ra.

Chấm mỗi trục từ 1 đến 5:

| Điểm | Probability | Impact |
| --- | --- | --- |
| 1 | Hiếm, khó xảy ra | Ảnh hưởng nhỏ, dễ phục hồi |
| 2 | Ít có khả năng | Ảnh hưởng giới hạn, có workaround |
| 3 | Có thể xảy ra | Làm hỏng một phần luồng hoặc cần can thiệp |
| 4 | Dễ xảy ra trong một số điều kiện | Gây mất dữ liệu, gián đoạn đáng kể hoặc ảnh hưởng nhiều người dùng |
| 5 | Thường xuyên hoặc có điều kiện kích hoạt phổ biến | Rất nghiêm trọng: vi phạm bảo mật, mất dữ liệu lớn hoặc tạo side effect không thể chấp nhận |

Điểm rủi ro cơ bản:

\[
R = P \times I
\]

Ví dụ ngưỡng ưu tiên để lập kế hoạch:

| Điểm R | Mức ưu tiên gợi ý | Cách xử lý |
| --- | --- | --- |
| 15–25 | Critical | Cần kiểm soát và bằng chứng kiểm thử trước khi phát hành |
| 8–14 | High | Cần test rõ ràng; xem xét đưa vào CI bắt buộc |
| 4–7 | Medium | Kiểm thử theo phạm vi thay đổi và mức độ phơi nhiễm |
| 1–3 | Low | Có thể kiểm tra ở mức phù hợp hoặc theo dõi |

Đây là thang minh họa, không phải chuẩn chung cho mọi tổ chức. Nhóm cần hiệu chỉnh theo mức chịu rủi ro, loại dữ liệu, quy mô hệ thống và yêu cầu tuân thủ.

Có thể ghi thêm khả năng phát hiện (Detectability) hoặc mức độ khó phát hiện để hỗ trợ thảo luận. Tuy nhiên, không nên nhân thêm một điểm D rồi gọi kết quả là RPN nếu nhóm chưa định nghĩa thang đo và cách dùng nhất quán. Bảng này dùng P × I để giữ cách ưu tiên đơn giản, dễ giải thích.

## Ma trận rủi ro cho luồng tạo Workspace

Bảng dưới đây là risk register mẫu. Điểm số phản ánh giả định một API tạo tài nguyên có quota, database, provider ngoài và xử lý bất đồng bộ. Khi áp dụng vào hệ thống thật, hãy điều chỉnh P/I dựa trên incident, lưu lượng, kiến trúc và dữ liệu thực tế.

| ID | Failure mode / rủi ro | P | I | R | Bằng chứng kiểm thử và kiểm soát |
| --- | --- | ---: | ---: | ---: | --- |
| R01 | Payload sai hoặc thiếu trường nhưng vẫn tạo tài nguyên | 3 | 3 | 9 | MVC test cho body không hợp lệ, validation error và không gọi service |
| R02 | Người dùng không có quyền tạo Workspace cho tenant khác | 3 | 5 | 15 | Security integration test cho 401/403; kiểm tra tenant/owner được lấy từ principal đã xác thực |
| R03 | Tạo tài nguyên vượt quota hoặc dùng plan không hợp lệ | 3 | 4 | 12 | Unit/service test cho biên quota; repository integration test cho số lượng đang tồn tại |
| R04 | Hai request cùng tên tạo hai Workspace ngoài ý muốn | 4 | 4 | 16 | Unique constraint trong DB; integration test gửi request cạnh tranh và xác nhận chỉ một tài nguyên hợp lệ |
| R05 | Retry cùng request tạo nhiều tài nguyên do thiếu idempotency | 4 | 5 | 20 | Test lặp cùng Idempotency-Key; xác nhận cùng resource id và không lặp side effect |
| R06 | Database lưu Workspace nhưng outbox event không được ghi | 3 | 5 | 15 | Transaction integration test xác nhận metadata và outbox cùng commit hoặc cùng rollback |
| R07 | Provider tạo resource nhưng response timeout khiến ứng dụng ghi nhận thất bại | 3 | 5 | 15 | Adapter contract test cho timeout/ambiguous result; worker retry phải idempotent hoặc reconcile theo provider key |
| R08 | Provider từ chối hoặc lỗi tạm thời nhưng Workspace bị kẹt PENDING mãi | 3 | 4 | 12 | Worker test cho retry/backoff, giới hạn retry và chuyển FAILED hoặc trạng thái cần can thiệp |
| R09 | Message được giao ít nhất một lần và worker xử lý trùng | 4 | 4 | 16 | Test duplicate delivery; kiểm tra xử lý idempotent theo event/resource id |
| R10 | Worker cập nhật READY trước khi provider xác nhận resource usable | 2 | 5 | 10 | Test state transition; chỉ chuyển READY sau tín hiệu thành công hoặc readiness probe phù hợp |
| R11 | Test song song dùng chung tên, key hoặc queue gây nhiễm dữ liệu | 4 | 3 | 12 | Namespace riêng theo suite/test; chạy song song và xác nhận cleanup có phạm vi |
| R12 | Cleanup xóa nhầm resource ngoài suite hoặc để lại resource tính phí | 3 | 4 | 12 | Test cleanup theo namespace; kiểm tra không xóa prefix/schema/resource của suite khác |
| R13 | Request hoặc provider chậm khiến test timeout ngẫu nhiên | 4 | 3 | 12 | Wait có deadline, test timeout có căn cứ; không dùng sleep cố định |
| R14 | Lỗi provider làm lộ credential hoặc payload nhạy cảm trong log | 2 | 5 | 10 | Test/log assertion cho dữ liệu nhạy cảm; cấu hình redaction và không log secret |

Theo giả định trên, R05, R04, R09 và R02 là các rủi ro ưu tiên cao nhất. Điều đó không có nghĩa bỏ qua những rủi ro điểm thấp hơn: một lỗi có impact rất cao vẫn cần được xem xét dù xác suất thấp.

## Chuyển rủi ro thành test case có thể thực thi

Mỗi dòng trong risk register nên dẫn tới một hoặc nhiều test case. Test case phải xác định điều kiện ban đầu, hành động và bằng chứng quan sát được. Cụm từ “đã test tạo Workspace” quá chung để chứng minh rủi ro cụ thể đã được kiểm soát.

Ví dụ ánh xạ:

| ID | Điều kiện | Hành động | Assertion quan trọng |
| --- | --- | --- | --- |
| R01 | Payload thiếu name | POST request | 400; lỗi validation; service không được gọi |
| R02 | Principal thuộc tenant A | Tạo resource cho tenant B | 403; không ghi DB; không publish event |
| R04 | Workspace cùng tenant/name đã tồn tại | Gửi request tạo lần nữa | Conflict theo hợp đồng; chỉ có một row |
| R05 | Idempotency key K đã tạo resource | Gửi lại cùng request và K | Cùng resource id; provider chỉ nhận một logical operation |
| R06 | Transaction đang tạo metadata | Gây lỗi khi ghi outbox | Không tồn tại metadata commit một mình |
| R07 | Provider tạo resource nhưng client timeout | Worker retry cùng provider operation key | Không tạo resource provider thứ hai; trạng thái được reconcile |
| R09 | Cùng event được giao hai lần | Xử lý event lặp | Một logical resource; không lặp side effect |
| R12 | Có resource của suite A và B | Cleanup suite A | A bị xóa; B còn nguyên |

Một rủi ro có thể cần test ở nhiều tầng. Ví dụ R05 cần unit test cho quy tắc idempotency, database integration test cho unique constraint và worker/adapter test cho side effect provider. Không nên ép một end-to-end test phải chứng minh tất cả chi tiết này.

## Phân tầng kiểm thử trong Spring

### Unit test cho quy tắc nghiệp vụ

Unit test phù hợp với logic thuần như:

- Tính quota còn lại.
- Kiểm tra plan có cho phép region được yêu cầu không.
- Xác định trạng thái hợp lệ trong state machine.
- Tạo hoặc kiểm tra idempotency fingerprint.
- Quyết định retry hay chuyển FAILED.

Các dependency như repository, clock và provider client có thể được thay bằng fake hoặc mock. Assertion cần xác nhận quyết định nghiệp vụ và các tương tác quan trọng, không chỉ kiểm tra method đã được gọi.

Ví dụ kiểm tra quota:

~~~java
@Test
void rejectsCreationWhenQuotaIsReached() {
    WorkspaceQuota quota = new WorkspaceQuota(3);

    assertThat(quota.canCreate(2)).isTrue();
    assertThat(quota.canCreate(3)).isFalse();
}
~~~

Ví dụ này kiểm tra quy tắc thuần. Nó không chứng minh hai request đồng thời không thể vượt quota; việc đó cần test tích hợp với cơ chế đồng bộ hoặc constraint mà hệ thống sử dụng.

### MVC slice cho hợp đồng HTTP

@WebMvcTest phù hợp để kiểm tra:

- Method/path và content type.
- Bean validation trên request body.
- Status code, Location hoặc response DTO.
- Authentication/authorization ở web security chain nếu cấu hình slice được nạp.
- Lỗi được chuyển thành error response.

Ví dụ:

~~~java
@WebMvcTest(WorkspaceController.class)
class WorkspaceControllerTests {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    WorkspaceService workspaceService;

    @Test
    void rejectsBlankWorkspaceName() throws Exception {
        mockMvc.perform(post("/api/workspaces")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "name": " ",
                                  "region": "ap-southeast-1",
                                  "plan": "STANDARD"
                                }
                                """))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(workspaceService);
    }
}
~~~

Annotation @MockitoBean thuộc Spring Framework 6.2 trở lên. Với dự án dùng phiên bản Spring Boot/Spring Framework cũ hơn, dùng cơ chế mock bean tương thích của dự án, chẳng hạn @MockBean ở các phiên bản Spring Boot trước khi chuyển sang API mới.

Test này chứng minh payload sai bị từ chối trước khi gọi service. Nó chưa kiểm tra quota, uniqueness hoặc database constraint.

### Service integration test với database thật

Rủi ro liên quan unique constraint, transaction, locking và outbox cần kiểm tra với database engine tương ứng. H2 hoặc mock repository có thể không tái hiện đầy đủ hành vi SQL, isolation level và constraint của PostgreSQL/MySQL mà production sử dụng.

Testcontainers có thể cung cấp database dùng trong test:

~~~java
@Testcontainers
@SpringBootTest
class WorkspaceCreationDatabaseTests {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    // DynamicPropertySource hoặc ServiceConnection cung cấp
    // URL, username và password cho Spring datasource.
}
~~~

Sau khi context và migration sẵn sàng, test có thể xác nhận:

- Unique constraint ngăn hai Workspace cùng tenant/name.
- Outbox row được ghi cùng transaction với Workspace.
- Transaction rollback không để lại metadata dở dang.
- Lock hoặc optimistic version xử lý cập nhật cạnh tranh đúng cách.

Với Testcontainers, chờ database readiness theo wait strategy và chờ migration hoàn tất trước khi truy vấn. Container running hoặc port mở chưa chứng minh schema đã sẵn sàng.

### Adapter test cho provider bên ngoài

Không nên gọi cloud provider thật trong mọi test. Adapter có thể kiểm tra bằng mock HTTP server hoặc stub server để xác nhận:

- URL, method, header và request body đúng.
- Authentication được gửi đúng nhưng secret không xuất hiện trong log.
- Response thành công được decode đúng.
- 4xx, 5xx, timeout và response không hợp lệ được ánh xạ đúng.
- Retry không tạo side effect lặp ngoài ý muốn.

Nếu dùng RestClient hoặc RestTemplate, MockRestServiceServer phù hợp để kiểm tra request ở client boundary. Với WebClient, dùng mock web server hoặc một HTTP test server tương ứng để kiểm tra request/response reactive.

### Worker và message integration test

Worker nên được kiểm tra với các trường hợp:

- Event hợp lệ tạo provider resource và cập nhật trạng thái.
- Event lặp không tạo thêm resource.
- Provider lỗi tạm thời được retry theo policy.
- Lỗi vĩnh viễn chuyển resource sang FAILED hoặc trạng thái nghiệp vụ quy định.
- Message được ack/nack đúng thời điểm.
- Worker không chuyển READY khi provisioning chưa hoàn tất.

Nếu dùng broker thật trong integration test, tạo queue/topic hoặc consumer group riêng cho suite. Dùng namespace để tránh test khác nhận message của test này.

## Ma trận rủi ro phải bao gồm dữ liệu và side effect

Một luồng tạo tài nguyên không chỉ ghi một row trong database. Có thể có nhiều side effect ngoài transaction:

| Thành phần | Side effect | Cách cô lập trong test |
| --- | --- | --- |
| Database | Workspace, quota counter, outbox row | Schema/tenant riêng hoặc record id duy nhất |
| Provider | Bucket, namespace, VM, external project | Fake provider hoặc resource prefix riêng trong sandbox |
| Redis | Lock, cache, idempotency record | Key prefix riêng theo suite |
| Broker | Queue, topic, message | Queue/topic hoặc consumer group riêng |
| Filesystem/object storage | File, object, multipart upload | Thư mục/prefix riêng |
| Scheduler/worker | Task đang chạy hoặc retry | Scheduler kiểm soát được, correlation id và tín hiệu hoàn tất |

Rollback database không tự hoàn tác các side effect ở Redis, broker, provider hoặc object storage. Nếu test gọi hệ thống thật, cần cleanup theo namespace hoặc dùng sandbox riêng.

Với provider có tính phí, ưu tiên fake/stub cho phần lớn test. Chỉ dùng sandbox integration test có giới hạn tài nguyên, timeout và cleanup rõ ràng cho những rủi ro cần xác nhận giao thức thật.

## Thiết kế idempotency và concurrency thành rủi ro riêng

Hai request giống nhau có thể đến do người dùng nhấn nút hai lần, client retry sau timeout hoặc broker giao message lại. Không thể chỉ dựa vào việc request body giống nhau để kết luận chúng là cùng một thao tác; hệ thống cần quy tắc idempotency rõ ràng.

Một thiết kế thường dùng:

- Client gửi Idempotency-Key cho một logical create operation.
- Server lưu key, owner/tenant, request fingerprint và resource id.
- Request lặp cùng key và cùng payload trả lại kết quả đã tạo hoặc trạng thái hiện tại.
- Cùng key nhưng payload khác bị từ chối theo hợp đồng.
- Unique constraint bảo vệ tính duy nhất ở database, kể cả khi hai request đến đồng thời.

Các test cần bao phủ:

1. Cùng key, cùng payload: chỉ một logical resource.
2. Cùng key, payload khác: trả lỗi conflict hoặc lỗi idempotency đã quy định.
3. Hai key khác nhau, cùng tên resource: uniqueness rule được áp dụng.
4. Hai request đồng thời cùng key: chỉ một operation được tạo; request còn lại nhận kết quả phù hợp.
5. Client timeout sau khi server đã commit: retry không lặp provider operation.

Test concurrency nên tạo tranh chấp thật ở ranh giới cần kiểm tra, ví dụ dùng hai thread hoặc hai transaction độc lập trên database test. Gọi hai method tuần tự trong một test không chứng minh race condition đã được xử lý.

## Transaction, outbox và trạng thái provisioning

Nếu Workspace và outbox event phải được ghi nguyên tử, cả hai nên nằm trong cùng database transaction. Test cần xác nhận:

- Khi ghi Workspace thành công và ghi outbox thành công, cả hai cùng commit.
- Nếu một bước trong transaction thất bại, không có Workspace đã commit mà thiếu outbox event.
- Publisher chỉ gửi event đã commit.
- Nếu publisher gửi message rồi chết trước khi đánh dấu outbox đã xử lý, message có thể được gửi lại; consumer phải idempotent.

Không nên giả định transaction database bao phủ một HTTP request tới provider. Nếu provider đã tạo resource rồi database rollback, hệ thống cần một chiến lược reconcile hoặc compensation. Test phải mô phỏng trường hợp timeout/ambiguous response và xác nhận retry không tạo thêm resource.

Một state machine đơn giản có thể là:

~~~text
PENDING
  | \
  |  \ permanent failure
  |   v
  |  FAILED
  |
  | provider confirms usable
  v
READY
~~~

Các chuyển trạng thái không hợp lệ cần bị từ chối. Ví dụ FAILED không tự chuyển READY nếu chưa có thao tác retry/reconcile rõ ràng. Test nên kiểm tra cả trạng thái hợp lệ và transition bị cấm.

## Ưu tiên test theo điểm rủi ro

Với risk register mẫu, một kế hoạch thực thi có thể được chia thành các nhóm:

| Nhóm ưu tiên | Rủi ro | Test bắt buộc nên có |
| --- | --- | --- |
| Critical | R02, R04, R05, R06, R07, R09 | Authorization, unique constraint, idempotency, transaction/outbox, provider ambiguity, duplicate delivery |
| High | R01, R03, R08, R11, R12, R13 | Validation, quota, retry/failure, namespace, cleanup, timeout |
| Theo điều kiện | R10, R14 | Readiness/state transition và log redaction khi có provisioning provider hoặc dữ liệu nhạy cảm |

Đừng ưu tiên chỉ theo điểm tổng. R02 có impact bảo mật rất cao; ngay cả khi xác suất đánh giá thấp, test authorization vẫn cần thiết. Tương tự, một lỗi có thể hiếm nhưng tạo tài nguyên tính phí hoặc rò dữ liệu tenant khác vẫn xứng đáng có kiểm soát mạnh.

## Dùng ma trận để xác định bằng chứng phát hành

Một dòng risk register chỉ hữu ích khi có thể truy từ rủi ro tới bằng chứng:

| Trường nên lưu | Nội dung |
| --- | --- |
| Risk ID | Mã ổn định như R05 |
| Failure mode | Điều có thể sai |
| P / I / score | Cơ sở ưu tiên |
| Preventive control | Constraint, authorization rule, idempotency, timeout hoặc design control |
| Test case | Tên test hoặc đường dẫn test cụ thể |
| Expected evidence | Status, row count, event count, provider request count, state transition |
| Owner | Người chịu trách nhiệm kiểm soát |
| Residual risk | Rủi ro còn lại sau kiểm soát |
| Status | Chưa có test, đang triển khai, đạt, hoặc cần chấp nhận rủi ro |

Ví dụ với R05:

~~~text
Risk ID: R05
Failure mode: Retry cùng request tạo nhiều Workspace
Control: Idempotency-Key + unique constraint + provider operation key
Test: sameKey_samePayload_returnsSameResource
Evidence:
  - cùng resource id ở hai response
  - một row Workspace
  - một logical outbox operation
  - một provider resource
Residual risk: provider không hỗ trợ idempotency cần reconcile theo external reference
~~~

Tên test trong ví dụ là tên gợi ý; hãy liên kết với test thực tế trong repository khi áp dụng. Nếu chưa có test, ghi rõ gap thay vì đánh dấu risk đã được xử lý chỉ vì có một tài liệu mô tả.

## Điều kiện hoàn tất cho một luồng tạo tài nguyên

Một bộ test cho luồng này nên cung cấp bằng chứng ở các ranh giới sau:

1. **HTTP contract:** request sai bị từ chối; request hợp lệ trả status, header và body đúng.
2. **Security:** chỉ principal/tenant được phép mới tạo được tài nguyên.
3. **Business rules:** quota, uniqueness, plan và region được áp dụng đúng.
4. **Persistence:** transaction, constraint và outbox giữ dữ liệu nhất quán.
5. **Idempotency/concurrency:** retry và request đồng thời không tạo logical resource hoặc side effect trùng.
6. **External integration:** request tới provider đúng; lỗi, timeout và response mơ hồ được xử lý.
7. **Async processing:** duplicate delivery, retry, readiness và state transition hoạt động đúng.
8. **Isolation/cleanup:** test song song không nhiễm dữ liệu; resource test được dọn đúng phạm vi.
9. **Observability:** log và error response không làm lộ secret; correlation id giúp truy vết một operation.

Không nhất thiết mọi mục đều cần một end-to-end test. Dùng unit test cho quy tắc thuần, slice test cho HTTP, database integration test cho constraint/transaction, adapter test cho giao thức ngoài và một số ít end-to-end test cho đường đi xuyên hệ thống.

## Quy trình xây dựng ma trận rủi ro

1. Vẽ luồng tạo tài nguyên từ request đến khi tài nguyên đạt trạng thái cuối cùng.
2. Chia luồng thành các bước và xác định dữ liệu, quyền, transaction, dependency cùng side effect ở từng bước.
3. Viết failure mode cụ thể cho mỗi bước; tránh các mô tả chung như “service có thể lỗi”.
4. Chấm Probability và Impact theo thang thống nhất; ghi rõ giả định và ngưỡng ưu tiên.
5. Chọn preventive control và test evidence cho từng rủi ro ưu tiên.
6. Ánh xạ mỗi test tới đúng tầng Spring phù hợp: unit, MVC slice, database integration, adapter, worker hoặc end-to-end.
7. Bổ sung kiểm soát dữ liệu test: namespace, idempotency key, cleanup và giới hạn side effect.
8. Chạy test trong CI theo thứ tự ưu tiên và ghi lại gap hoặc residual risk còn tồn tại.
9. Cập nhật ma trận khi luồng thay đổi, xuất hiện incident mới hoặc một dependency bên ngoài thay đổi hợp đồng.

Ma trận rủi ro tốt không chỉ liệt kê những gì có thể hỏng. Nó cho thấy vì sao một failure mode quan trọng, test nào chứng minh hành vi được bảo vệ và rủi ro nào vẫn còn. Với luồng tạo tài nguyên, cần chú ý đặc biệt đến quyền sở hữu dữ liệu, idempotency, transaction/outbox, provider ngoài, xử lý bất đồng bộ và cleanup; đây là những điểm mà một test happy path đơn lẻ khó phát hiện được vấn đề.
