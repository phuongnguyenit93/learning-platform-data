# Authentication success

## 1. Vì sao cần ghi nhận xác thực thành công?

Một hệ thống ghi rất kỹ những lần đăng nhập sai nhưng không ghi lần đăng nhập thành công. Khi một tài khoản bị sử dụng ngoài ý muốn, nhóm điều tra biết đã có nhiều lần thử nhưng không xác định được lúc nào hệ thống chấp nhận danh tính, luồng xác thực nào đã hoàn tất và phiên nào được tạo sau đó.

**Authentication success** là sự kiện cho biết hệ thống đã chấp nhận một danh tính theo một hợp đồng xác thực xác định. Đây là một sự kiện bảo mật cần có ngữ nghĩa rõ, không chỉ một dòng log “login OK”.

Ghi nhận thành công giúp liên kết hoạt động xác thực với việc thiết lập phiên, thay đổi trạng thái tài khoản và các hành động tiếp theo. Nó cũng hỗ trợ phát hiện những lần thành công bất thường, đối soát đường xử lý và kiểm tra việc thực thi chính sách xác thực.

Trong chương Logging và audit, mục tiêu là biến nhu cầu đó thành yêu cầu đo được: ghi đúng thời điểm, đúng chủ thể, đủ thông tin đối chiếu, không mang secret và có cơ chế phát hiện khi sự kiện không tới nơi lưu trữ.

Sau bài học, người học có thể:

- Xác định chính xác điều kiện để phát sinh một sự kiện xác thực thành công.
- Phân biệt xác thực, cấp quyền, thiết lập phiên và phát hành token.
- Thiết kế schema sự kiện và ranh giới tin cậy của từng field.
- Đặc tả độ bền vững, retry, chống đếm trùng và bảo vệ audit.
- Viết ca kiểm thử liên kết trạng thái nghiệp vụ với bằng chứng audit.

## 2. Định nghĩa “thành công” tại một ranh giới cụ thể

### 2.1. Không lấy một bước trung gian làm kết quả cuối

Trong luồng đăng nhập yêu cầu password và OTP, password đúng mới chỉ hoàn tất một bước. Nếu OTP chưa được xác minh hoặc tài khoản không còn được phép xác thực, không được ghi sự kiện thành công cuối cùng của toàn bộ luồng.

Một hợp đồng minh họa cho ứng dụng đa tenant:

> Sự kiện `AUTHENTICATION_SUCCEEDED` phát sinh khi ứng dụng đã hoàn tất các bước xác minh bắt buộc, chấp nhận principal từ nguồn tin cậy, áp dụng các điều kiện xác thực liên quan và hoàn tất chuyển trạng thái xác thực sang ACCEPTED cho một authentication ID cụ thể.

Các bước bắt buộc phụ thuộc luồng và chính sách được chọn. Không mặc định mọi luồng đều cần OTP, hoặc bất kỳ lần dùng hai cơ chế nào cũng có cùng mức bảo đảm.

Nếu hệ thống cần quan sát từng bước, hãy dùng loại sự kiện riêng, chẳng hạn `AUTHENTICATION_STEP_VERIFIED`. Loại đó không được tính là một lần hoàn tất xác thực.

### 2.2. Chọn điểm chốt trạng thái để sự kiện có nghĩa nhất quán

Một mô hình tham chiếu có thể là:

```text
Bắt đầu một attempt do server quản lý
  -> xác minh thông tin và các yếu tố bắt buộc
  -> tạo kết quả đủ điều kiện để chấp nhận danh tính
  -> hoàn tất chuyển trạng thái ACCEPTED
     và ghi nhận sự kiện theo cơ chế bền vững đã chốt
  -> tạo phiên hoặc phát hành token theo luồng riêng
  -> gửi phản hồi cho client
```

Trong mô hình này, việc so khớp password chưa phải điểm phát sinh sự kiện cuối. Sự kiện đại diện cho chuyển trạng thái ACCEPTED tại ứng dụng.

Một hệ thống khác có thể chọn ghi nhận một sự thật hẹp hơn, như bộ xác minh đã xác nhận một bằng chứng cụ thể. Khi đó, tên và mô tả sự kiện phải thể hiện phạm vi hẹp đó. Không dùng cùng một tên cho cả “password đúng” và “toàn bộ luồng đã được chấp nhận”.

### 2.3. Những kết quả cần phân biệt

| Kết quả | Có thể chứng minh điều gì? | Không tự chứng minh điều gì? |
|---|---|---|
| Một yếu tố được xác minh | Một bước trong ceremony đã đạt | Toàn bộ luồng đã hoàn tất |
| Authentication accepted | Ứng dụng chấp nhận danh tính theo hợp đồng | Chủ thể có mọi quyền nghiệp vụ |
| Session established | Trạng thái phiên đã được tạo theo hợp đồng | Client chắc chắn đã nhận và sử dụng phiên |
| Token issued | Token đã được phát hành theo định nghĩa của dịch vụ | Người dùng đang hiện diện hoặc đã nhận token |
| Authorization allowed | Một hành động được cho phép trong phạm vi cụ thể | Một lần xác thực mới vừa diễn ra |
| HTTP 200 | Một response có status thành công theo giao thức | Danh tính đã được xác thực thành công |

Một người có thể xác thực thành công nhưng bị từ chối xuất báo cáo vì thiếu quyền. Audit phải cho phép thấy hai sự thật đó thay vì gộp thành một kết quả “đăng nhập thất bại”.

Nếu tạo phiên thất bại sau khi authentication đã ACCEPTED, không sửa lịch sử thành “chưa từng xác thực thành công”. Ghi sự kiện tạo phiên thất bại theo hợp đồng và liên kết bằng authentication ID. Client có thể chỉ nhận thông báo chưa hoàn tất đăng nhập, nhưng sự thật nội bộ vẫn cần được mô tả chính xác.

## 3. Phạm vi với các luồng xác thực khác nhau

### 3.1. Đăng nhập, step-up và xác thực lại

Một người có thể đăng nhập, sau đó xác thực tăng cường để thay đổi thông tin nhạy cảm. Hai ceremony có mục đích khác nhau và nên có authentication ID riêng, cùng liên kết tới ngữ cảnh liên quan nếu cần.

Không đếm step-up như một phiên đăng nhập mới nếu nó chỉ nâng mức bảo đảm của phiên hiện hữu. Schema cần có `flow` hoặc trường tương đương để phân biệt.

Thành công của một ceremony cũng không có nghĩa mọi hành động tiếp theo đều được phép. Phân quyền và điều kiện hết hiệu lực vẫn cần được thi hành riêng.

### 3.2. Đăng nhập liên kết

Nhà cung cấp danh tính báo thành công chưa đồng nghĩa ứng dụng đã chấp nhận người dùng. Ứng dụng còn phải xác minh thông điệp theo giao thức, ràng buộc với luồng đã bắt đầu, ánh xạ đúng chủ thể và kiểm tra điều kiện tài khoản theo chính sách.

Chỉ khi hoàn tất ranh giới chấp nhận của ứng dụng mới ghi sự kiện thành công của ứng dụng. Nếu cần ghi việc nhận một callback hoặc bằng chứng bên ngoài, đó là loại quan sát khác.

Định danh từ bên ngoài cần có namespace hoặc quan hệ ánh xạ phù hợp. Không mặc định cùng một chuỗi subject từ hai issuer khác nhau là cùng một tài khoản. Trường chủ thể trong audit nên lấy từ kết quả ánh xạ đã được tin cậy, không lấy trực tiếp từ tham số callback.

### 3.3. Token refresh và kiểm tra token trên mỗi request

Refresh token thành công không tự chứng minh người dùng vừa nhập credential hoặc xác thực lại. Tương tự, xác minh một token trên request đã đăng nhập không nhất thiết là một lần hoàn tất ceremony đăng nhập mới.

Nếu ghi những hoạt động này, đặt loại sự kiện và mục đích riêng. Không làm số lần đăng nhập tăng theo số request API chỉ vì middleware kiểm tra token trên mọi request.

Ngược lại, nếu một service xác thực workload tại một ranh giới riêng, cần mô tả rõ chủ thể là workload, cơ chế nào được kiểm tra và sự kiện thành công đại diện cho lần thiết lập ngữ cảnh nào. Không gắn nhãn mọi chủ thể máy là người dùng.

## 4. Rủi ro mà sự kiện cần hỗ trợ kiểm soát

| ID | Tình huống | Hậu quả đối với audit và an toàn thông tin |
|---|---|---|
| R-AUTH-01 | Ghi thành công ngay khi password đúng, trước MFA | Hồ sơ khẳng định sai rằng luồng đã hoàn tất |
| R-AUTH-02 | Lấy subject hoặc tenant từ input chưa xác minh | Gán sự kiện cho sai người hoặc tenant |
| R-AUTH-03 | Mất sự kiện sau khi chấp nhận authentication | Không đối soát được hoạt động đã thực sự được chấp nhận |
| R-AUTH-04 | Retry tạo event ID mới cho cùng một sự kiện | Đếm trùng và làm sai chuỗi điều tra |
| R-AUTH-05 | Log toàn bộ credential, token hoặc assertion | Kho audit trở thành nguồn lộ thông tin xác thực |
| R-AUTH-06 | Mọi thành phần đều ghi cùng loại “login success” | Không biết đâu là sự kiện có thẩm quyền, đâu là quan sát lặp |
| R-AUTH-07 | Người dùng đọc được sự kiện của tenant khác | Lộ lịch sử truy cập và quan hệ hoạt động |
| R-AUTH-08 | Dùng thời điểm ingest làm thời điểm xác thực | Sai thứ tự phân tích khi pipeline bị trễ hoặc replay |

Một sự kiện thành công không tự chứng minh hoạt động là hợp lệ theo ý định của chủ tài khoản. Người khác có thể đang sử dụng credential bị lộ. Giá trị của audit nằm ở việc ghi nhận chính xác hệ thống đã chấp nhận điều gì và hỗ trợ điều tra bằng những ngữ cảnh được phép thu thập.

## 5. Schema sự kiện: đủ đối chiếu, ít dữ liệu nhạy cảm

### 5.1. Nhóm trường cốt lõi

| Nhóm | Trường minh họa | Ý nghĩa |
|---|---|---|
| Hợp đồng | `schemaVersion`, `eventType` | Xác định cấu trúc và ngữ nghĩa sự kiện |
| Định danh sự kiện | `eventId` | Nhận diện một sự kiện logic, giữ nguyên khi gửi lại |
| Định danh xác thực | `authenticationId` | Liên kết một lần hoàn tất chấp nhận danh tính |
| Ngữ cảnh thử | `attemptId`, `requestId` | Phân biệt ceremony với từng request trong luồng |
| Chủ thể | `subjectRef`, loại chủ thể nếu cần | Trỏ tới principal đã được xác minh |
| Phạm vi | `tenantRef` nếu luồng có tenant | Cho phép phân tách và kiểm soát truy cập đúng phạm vi |
| Cơ chế | `flow`, `methods` | Mô tả luồng và những phương thức thực sự đã dùng |
| Chính sách | `policyRevision`, hồ sơ bảo đảm nếu cần | Cho biết điều kiện chấp nhận nào được áp dụng |
| Thời gian | `acceptedAt` hoặc thời điểm sự kiện theo hợp đồng | Mốc do producer ghi cho chuyển trạng thái ACCEPTED |
| Nguồn | `sourceService`, `deploymentRevision` | Đối chiếu thành phần phát sinh và cấu hình triển khai |

Danh mục này là mẫu, không phải yêu cầu thu mọi field ở mọi hệ thống. Mỗi field cần có mục đích, nguồn tin cậy và điều kiện lưu giữ.

### 5.2. Ví dụ một sự kiện tổng hợp

```json
{
  "schemaVersion": 1,
  "eventType": "AUTHENTICATION_SUCCEEDED",
  "eventId": "15c6bc53-c1b5-4be1-b874-94cd7e064b8a",
  "sourceService": "identity-service",
  "deploymentRevision": "candidate-build-18",
  "authentication": {
    "authenticationId": "a411263d-bbf2-4b11-a31d-b94553fc9930",
    "attemptId": "86b2f1ee-140b-47ee-9ad5-bc39dd3124e2",
    "requestId": "e605c9f0-f2f4-49f7-b0e2-d9c0c1f93eef",
    "subjectRef": "40fe7514-01a2-4fc5-9834-47ccca70347b",
    "tenantRef": "7a0821ae-100e-46d4-8d75-d1f9293607bd",
    "flow": "LOGIN",
    "methods": ["PASSWORD", "OTP"],
    "policyRevision": "authn-policy-r7",
    "acceptedAt": "2026-11-27T03:15:00Z"
  }
}
```

Tất cả giá trị là dữ liệu minh họa. Không có password, OTP, token hay session cookie trong sự kiện.

Danh sách phương thức không tự tạo ra một mức bảo đảm chung cho mọi sản phẩm. Nếu cần ghi mức bảo đảm, phải lấy kết quả đánh giá theo policy của hệ thống, bao gồm nguồn credential và điều kiện áp dụng. Không dùng một cờ do client gửi để khẳng định người dùng đã thực hiện MFA.

### 5.3. Không dùng định danh cấp quyền làm correlation ID

`eventId`, `authenticationId` và `attemptId` nên là định danh không chứa secret, do thành phần tin cậy quản lý. Biết các ID đó không được tự cấp quyền truy cập audit hoặc phiên.

Nếu cần liên kết một phiên, dùng `sessionRef` phục vụ audit không có khả năng xác thực, thay vì cookie hoặc token thật. Không mặc định băm raw session token là đã có một định danh an toàn; còn phải xem độ nhạy, khả năng liên kết và mục đích lưu.

Attempt ID là định danh của một luồng do server quản lý, không phải session credential. Request ID của một request khác với attempt ID của ceremony gồm nhiều request. Một lần gửi lại cũng chưa chắc là cùng một authentication; quy tắc xác định sự kiện logic phải dựa vào trạng thái của luồng, không chỉ một header do client cung cấp.

## 6. Ranh giới tin cậy của chủ thể và ngữ cảnh

### 6.1. Chủ thể lấy từ kết quả xác thực

Không lấy username nhập ban đầu làm bằng chứng cho principal đã được chấp nhận. Username có thể khác về dạng chuẩn hóa, alias hoặc tài khoản liên kết; thậm chí người dùng có thể cố đưa chuỗi gây nhiễu vào input.

Trường chủ thể nên lấy từ kết quả xác thực hoặc bản ghi ACCEPTED đáng tin cậy. Tenant cũng phải là phạm vi đã xác minh theo luồng, không phải giá trị header bất kỳ.

Nếu một luồng không có tenant, schema cần mô tả rõ điều đó. Không dùng tenant mặc định toàn cục chỉ để điền đầy một field, vì nó có thể làm sai cả truy vết và quyền đọc audit.

### 6.2. Địa chỉ nguồn và thiết bị là ngữ cảnh, không phải danh tính

Địa chỉ mạng, user agent hoặc thông tin thiết bị có thể hữu ích cho điều tra, nhưng cần mục đích và mức chi tiết phù hợp. Không phải mọi hệ thống đều cần giữ IP đầy đủ hoặc toàn bộ chuỗi user agent.

Nếu dùng thông tin từ reverse proxy, phải có cấu hình tin cậy để phân biệt header do proxy quản lý với header người gọi tự gửi. Đừng mặc định lấy phần tử đầu tiên của một chuỗi header là địa chỉ thật.

IP dùng chung, NAT, VPN hoặc thay đổi thiết bị có thể ảnh hưởng diễn giải. Một địa chỉ mới không tự chứng minh tài khoản bị chiếm; địa chỉ quen thuộc cũng không chứng minh người thao tác là chủ tài khoản.

Nếu ghi ngữ cảnh suy luận như vùng mạng hoặc loại client, cần lưu được ý nghĩa và nguồn tạo giá trị. Không nâng một suy đoán thành sự thật xác thực.

### 6.3. Đăng nhập hộ, hỗ trợ và impersonation

Một nhân sự hỗ trợ truy cập dưới danh nghĩa người dùng không nên tạo bản ghi khiến lịch sử trông như chính người dùng vừa nhập credential.

Cần phân biệt chủ thể khởi tạo, chủ thể hiệu lực và căn cứ ủy quyền theo chức năng. Những hoạt động này có thể cần loại sự kiện riêng cùng liên kết tới xác thực của người khởi tạo. Không dùng trường `subjectRef` duy nhất để che khuất sự khác biệt.

## 7. Dữ liệu không được đưa vào sự kiện thành công

Các nhóm cần loại khỏi audit thông thường gồm:

- Password, mã OTP và bí mật khôi phục tài khoản.
- Access token, refresh token, session cookie hoặc raw session ID có khả năng xác thực.
- Toàn bộ assertion, bằng chứng xác thực hoặc response từ nhà cung cấp danh tính khi chưa có mục đích và kiểm soát dữ liệu phù hợp.
- Authorization header, cookie header, connection string và object cấu hình có secret.
- Toàn bộ request hoặc object principal chỉ vì serializer có thể chuyển chúng thành JSON.
- Claims, profile hoặc thông tin cá nhân không cần thiết cho mục đích audit đã chốt.

Một đoạn mã như sau không đủ an toàn:

```java
logger.info("Authentication success: {}", authenticationObject);
```

`toString()` hoặc serializer của object có thể thay đổi theo thư viện, cấu hình hoặc field mới được bổ sung. Cần schema allowlist riêng cho sự kiện, không dựa vào việc object hiện tại tình cờ không in credential.

Log có cấu trúc cũng không tự loại bỏ dữ liệu nhạy cảm. Nó chỉ giúp việc kiểm soát field rõ hơn nếu nguồn tạo giá trị và serializer thực sự được quản lý.

Với field có nguồn không tin cậy, cần giới hạn kích thước, chuẩn hóa theo hợp đồng và escape đúng định dạng. Chuỗi xuống dòng hoặc ký tự điều khiển không được biến một giá trị thành sự kiện giả. Giao diện tìm kiếm và export cũng phải hiển thị dữ liệu như dữ liệu, không thực thi nội dung được ghi.

## 8. Ví dụ Java: tạo sự kiện từ trạng thái được chấp nhận

Ví dụ dùng cú pháp Java 17 trở lên cho một luồng đa tenant. Nó chỉ tạo DTO theo allowlist; việc xác minh danh tính, transaction và truyền sự kiện là phần kiến trúc riêng.

```java
import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

public final class AuthenticationAudit {
    private AuthenticationAudit() {}

    public enum Flow {
        LOGIN,
        STEP_UP,
        SERVICE_AUTH
    }

    public enum Method {
        PASSWORD,
        OTP,
        PASSKEY,
        FEDERATED_ASSERTION,
        CLIENT_CERTIFICATE
    }

    public enum EventType {
        AUTHENTICATION_SUCCEEDED
    }

    public record AcceptedAuthentication(
        UUID authenticationId,
        UUID attemptId,
        UUID requestId,
        UUID subjectRef,
        UUID tenantRef,
        Flow flow,
        List<Method> methods,
        String policyRevision,
        Instant acceptedAt
    ) {
        public AcceptedAuthentication {
            Objects.requireNonNull(authenticationId);
            Objects.requireNonNull(attemptId);
            Objects.requireNonNull(requestId);
            Objects.requireNonNull(subjectRef);
            Objects.requireNonNull(tenantRef);
            Objects.requireNonNull(flow);
            methods = List.copyOf(methods);
            if (methods.isEmpty()) {
                throw new IllegalArgumentException("METHODS_REQUIRED");
            }
            Objects.requireNonNull(policyRevision);
            if (policyRevision.isBlank()) {
                throw new IllegalArgumentException("POLICY_REQUIRED");
            }
            Objects.requireNonNull(acceptedAt);
        }
    }

    public record SuccessEvent(
        int schemaVersion,
        EventType eventType,
        UUID eventId,
        AcceptedAuthentication authentication
    ) {}

    public static SuccessEvent create(
        UUID eventId,
        AcceptedAuthentication accepted
    ) {
        return new SuccessEvent(
            1,
            EventType.AUTHENTICATION_SUCCEEDED,
            Objects.requireNonNull(eventId),
            Objects.requireNonNull(accepted)
        );
    }
}
```

Những quyết định có ý nghĩa trong ví dụ:

- Field sự kiện không nhận password, token, request thô hoặc exception.
- Subject và tenant có định danh riêng, không lấy từ chuỗi login để hiển thị.
- Danh sách phương thức được sao chép thành danh sách không sửa được qua tham chiếu đầu vào.
- `eventId` được truyền vào từ bản ghi sự kiện, không tạo mới mỗi lần exporter gửi lại.
- `acceptedAt` được giữ từ chuyển trạng thái gốc, không dùng thời điểm retry làm thời điểm xác thực.

Tên record không tự chứng minh dữ liệu đã được xác minh. `AcceptedAuthentication` phải được tạo từ thành phần tin cậy và được dùng trong mô hình chuyển trạng thái đã chốt, không deserialize trực tiếp từ JSON của client.

Khi dùng transaction, có thể dựng DTO trong bước chuẩn bị nhưng chỉ coi sự kiện đã phát sinh khi chuyển trạng thái và ghi nhận bền vững liên quan hoàn tất. Không gửi sự kiện ra ngoài trước commit rồi để consumer hiểu một trạng thái đã rollback là thành công.

Ví dụ bắt buộc tenant cho tình huống minh họa. Luồng không có tenant cần hợp đồng riêng phù hợp, không tự điền tenant giả để vượt qua constructor.

Thông tin nguồn như service và revision triển khai có thể được thêm bởi producer hoặc envelope tin cậy. Không để client tự khai nguồn, phiên bản hay mức bảo đảm của sự kiện.

## 9. Ghi bền vững, outbox và hành vi khi pipeline lỗi

### 9.1. “Đã gọi logger” không có nghĩa “audit đã được lưu”

Một lời gọi logging có thể chỉ đưa dữ liệu vào buffer trong bộ nhớ. Tiến trình bị dừng trước khi flush, exporter timeout hoặc collector từ chối schema đều có thể làm mất sự kiện.

Yêu cầu cần định nghĩa mức xác nhận: được enqueue trong tiến trình, được ghi vào nơi lưu bền vững cục bộ, được collector chấp nhận hay đã có trong kho audit có thể đối soát. Những mốc đó không đồng nhất.

Nếu dự án yêu cầu audit bền vững trước khi cấp khả năng sử dụng phiên, một cơ chế chỉ lưu vào bộ nhớ không đủ để đáp ứng. Nếu audit của một luồng là best effort, điều đó cũng phải được ghi rõ cùng rủi ro và cơ chế phát hiện mất dữ liệu.

### 9.2. Một phương án với transaction và outbox

Trong mô hình có trạng thái xác thực lưu bền vững, có thể ghi bản ghi ACCEPTED và outbox event trong cùng transaction cục bộ:

```text
Hoàn tất xác minh bắt buộc
  -> transaction:
       ghi AuthenticationRecord = ACCEPTED
       ghi OutboxEvent với eventId cố định
     commit
  -> worker đọc outbox và gửi tới pipeline audit
  -> consumer ghi nhận và xử lý trùng theo hợp đồng
```

Điều này giúp gắn chuyển trạng thái đã commit với một sự kiện chờ gửi. Nó không tự tạo ra một transaction bao trùm mọi IdP, mọi kho phiên và collector từ xa.

Nếu không có một nơi lưu trạng thái phù hợp cho transaction này, dự án cần chọn cơ chế khác và mô tả rõ khoảng trống có thể mất sự kiện. Không chỉ thêm từ “outbox” vào thiết kế rồi bỏ qua phạm vi nguyên tử thực tế.

### 9.3. Khi nơi ghi bền vững không hoạt động

Nếu audit bền vững là điều kiện bắt buộc của chuyển trạng thái hoặc của việc cấp phiên, không được âm thầm bỏ sự kiện rồi tiếp tục như đã đạt điều kiện. Hành động phụ thuộc phải tuân theo chính sách fail closed của luồng.

Nếu collector không hoạt động nhưng outbox bền vững đã đáp ứng điều kiện được chấp nhận, luồng có thể tiếp tục trong giới hạn backlog và policy đã xác định. Khi dung lượng, thời hạn hoặc khả năng ghi bền vững không còn bảo đảm, phải có hành vi rõ thay vì dùng bộ nhớ vô hạn hoặc rơi về ghi dữ liệu thô ra console.

Không dùng raw token hay toàn bộ request làm dữ liệu fallback khi schema hoặc exporter lỗi. Sự kiện lỗi của chính pipeline cũng phải được giảm dữ liệu và tránh vòng lặp tự ghi lỗi không giới hạn.

## 10. Retry, trùng lặp, thứ tự và thời gian

### 10.1. Phân biệt một sự kiện logic với nhiều lần giao nhận

Một lần xác thực được chấp nhận có thể dẫn tới nhiều lần gửi cùng event do retry. Cần giữ nguyên `eventId` cho các lần giao nhận của cùng sự kiện logic.

Consumer phải có quy tắc chống đếm trùng phù hợp, chẳng hạn theo cặp nguồn sự kiện và event ID trong phạm vi định danh đã chốt. Thời gian giữ thông tin dedup cần phù hợp cửa sổ retry và replay, không chỉ vài giây tùy ý.

Không tạo event ID mới ở mỗi lần gửi hoặc dùng timestamp làm khóa duy nhất. Cũng không gộp mọi lần xác thực của cùng một người trong một khoảng thời gian thành một sự kiện; có thể đó là các ceremony độc lập.

Retry không bảo đảm tự có “exactly once” trên toàn hệ thống. Cần nêu riêng số lần giao nhận, số sự kiện logic và kết quả xử lý cuối cùng của consumer.

### 10.2. Không để nhiều tầng cùng đóng vai nguồn có thẩm quyền

Gateway, identity service và application có thể cùng quan sát một luồng. Phải chỉ định nguồn có thẩm quyền cho mỗi ranh giới authentication mà schema đại diện.

Những quan sát khác có thể được ghi với loại riêng và liên kết cùng authentication ID theo mô hình tin cậy. Không cho ba service cùng tạo ba sự kiện “login success” không thể phân biệt rồi dựa vào truy vấn để đoán chúng là một lần hay ba lần.

### 10.3. Giữ thời điểm gốc và thời điểm thu nhận riêng

`acceptedAt` hoặc trường thời gian sự kiện được giữ từ nguồn. Collector có thể thêm `ingestedAt` để biểu diễn thời điểm nhận. Replay sau nhiều giờ không làm thời điểm xác thực dịch sang lúc replay.

Clock giữa các producer có thể lệch và pipeline có thể giao nhận khác thứ tự. Cần theo dõi chất lượng thời gian, nguồn tạo timestamp và dùng định danh cùng quan hệ trạng thái để phân tích nhân quả. Không chỉ sắp xếp timestamp rồi kết luận chắc chắn sự kiện nào gây ra sự kiện nào.

Nếu cần thứ tự chặt trong phạm vi một luồng, có thể đặc tả sequence hoặc version do nguồn trạng thái quản lý. Đó là thuộc tính riêng cần được thi hành; không tự có nhờ định dạng thời gian UTC.

## 11. Bảo vệ tính toàn vẹn và quyền riêng tư của audit

### 11.1. Ai được phát hành và ai được sửa?

Collector cần xác thực nguồn phát hành và giới hạn quyền theo service hoặc loại sự kiện. Người dùng không được gửi JSON trực tiếp vào collector rồi tạo lịch sử xác thực giả cho tài khoản khác.

Producer nên có quyền ghi theo phạm vi cần thiết, không mặc định có quyền sửa hoặc xóa lịch sử đã lưu. Quyền quản trị collector, tìm kiếm, export và quản lý thời hạn lưu cần được phân tách phù hợp tổ chức.

Nếu yêu cầu khả năng phát hiện sửa đổi, hãy đặc tả cơ chế và mô hình đe dọa: bên nào có thể thay đổi dữ liệu, bằng chứng nào phát hiện được và ai giữ khả năng kiểm chứng. Append-only hoặc kỹ thuật bảo vệ toàn vẹn hỗ trợ một số thuộc tính, không tự chứng minh producer đã ghi sự thật đúng.

### 11.2. Audit chứa dữ liệu về hành vi con người

Lịch sử đăng nhập có thể tiết lộ giờ hoạt động, mối liên hệ tenant, thiết bị và vị trí suy luận. Định danh giả danh vẫn có thể liên kết về một người trong hệ thống.

Phải chốt mục đích, người được xem, thời hạn giữ và mức chi tiết. Nếu chỉ cần một nhóm client hoặc vùng mạng cho mục đích đã xác nhận, không tự thu thêm toàn bộ profile hoặc lịch sử thiết bị.

API tra cứu audit cũng cần kiểm soát tenant và vai trò. Biết một event ID không đủ để đọc sự kiện; có quyền quản trị một tenant không tự cho phép xem lịch sử của tenant khác.

### 11.3. Export, backup và phục hồi

File xuất, index, kho phân tích và backup là những nơi nhận dữ liệu thực sự. Chính sách lưu giữ và quyền truy cập cần đi cùng các bản sao phù hợp phạm vi.

Khi restore hoặc replay, giữ nguyên định danh và thời điểm gốc; không biến bản ghi lịch sử thành một authentication mới. Cũng cần tránh phục hồi dữ liệu đã hết thời hạn trở lại một index có thể tìm kiếm rộng mà không áp dụng lại chính sách liên quan.

## 12. Bộ yêu cầu bảo mật có thể nghiệm thu

Các mã sau là mẫu đặc tả cho dự án, chưa phải kết quả kiểm chứng của một bản triển khai.

| ID | Yêu cầu | Bằng chứng |
|---|---|---|
| AS-01 | Định nghĩa sự kiện chỉ phát sinh tại điểm chấp nhận authentication đã chốt cho từng flow | Sơ đồ trạng thái và ca bước trung gian |
| AS-02 | Subject, tenant, phương thức và policy lấy từ kết quả tin cậy, không từ khai báo tùy ý của client | Mapping nguồn field và thử giả mạo context |
| AS-03 | Mỗi authentication được chấp nhận trong phạm vi có một sự kiện logic có thể đối soát | Đối chiếu bản ghi ACCEPTED với event và outbox |
| AS-04 | Sự kiện có schema được quản lý, định danh ổn định và thời điểm gốc không đổi khi retry | Kiểm tra schema, retry và replay |
| AS-05 | Không ghi credential, token, cookie, proof thô hoặc dữ liệu cá nhân ngoài mục đích | Fixture canary và kiểm tra từng sink |
| AS-06 | Ghi nhận authentication tách biệt với session, token issuance và authorization | Ca tạo phiên lỗi, từ chối quyền và refresh |
| AS-07 | Mức bền vững bắt buộc và hành vi khi không đạt được xác định cho từng flow | Fault injection vào outbox, collector và dung lượng |
| AS-08 | Consumer xử lý giao nhận lặp theo hợp đồng và không đếm mỗi retry thành một lần đăng nhập | Thử gửi lại cùng event ID và ceremony độc lập |
| AS-09 | Nguồn phát hành được xác thực; quyền ghi, đọc và export đúng phạm vi | Ca nguồn giả, sai tenant và vai trò không phù hợp |
| AS-10 | Backlog, sự kiện bị từ chối và khoảng trống đối soát có tín hiệu quan sát không mang secret | Fault injection và cảnh báo tổng hợp |
| AS-11 | Chính sách lưu giữ, bản sao và phục hồi giữ ngữ nghĩa cùng quyền truy cập của dữ liệu audit | Diễn tập export, restore và replay |
| AS-12 | Bằng chứng nghiệm thu gắn với build, schema, cấu hình và danh mục flow cụ thể | Hồ sơ kết quả và giới hạn bao phủ |

### 12.1. Đặc tả chi tiết cho một luồng password và OTP

```text
Phạm vi:
  Luồng LOGIN của ứng dụng đa tenant trên candidate build.

Điểm phát sinh:
  Chuyển trạng thái ACCEPTED sau toàn bộ kiểm tra bắt buộc.

Nội dung bắt buộc:
  Event ID, authentication ID, chủ thể và tenant đã xác minh,
  flow, phương thức thực tế, policy revision, thời điểm gốc và nguồn.

Nội dung bị cấm:
  Password, OTP, token, cookie và request/response xác thực thô.

Độ bền vững:
  Trạng thái ACCEPTED và outbox event được commit cùng transaction
  trong mô hình lưu trữ đã chọn.

Giao nhận:
  Retry giữ nguyên event ID và thời điểm gốc.
  Consumer xử lý lặp theo hợp đồng đã chốt.

Điều kiện đạt:
  Có đối soát trạng thái với sự kiện logic.
  Các ca lỗi bắt buộc được kích hoạt thật.
  Không có canary secret tại những sink bị cấm đã liệt kê.
```

Đây là lựa chọn kiến trúc cho tình huống minh họa. Không áp dụng nguyên văn yêu cầu transaction cục bộ cho một hệ thống chưa có những thành phần lưu trữ đó mà không phân tích lại.

## 13. Thiết kế kiểm thử theo trạng thái và đường dữ liệu

### 13.1. Ma trận kiểm thử minh họa

| Ca | Điều kiện kích hoạt | Điều kiện đạt |
|---|---|---|
| TC-AS-01 | Password và OTP đúng, các điều kiện khác đạt | Có một authentication ACCEPTED và một sự kiện logic đúng schema |
| TC-AS-02 | Password đúng nhưng OTP chưa hoàn tất hoặc sai | Không có sự kiện thành công cuối của ceremony |
| TC-AS-03 | Bằng chứng hợp lệ nhưng tài khoản không được chấp nhận theo policy | Không gán thành công chỉ vì credential đã được xác minh |
| TC-AS-04 | Thay subject hoặc tenant trong request/header | Sự kiện lấy chủ thể thực từ nguồn tin cậy, không theo giá trị giả |
| TC-AS-05 | IdP báo thành công nhưng ứng dụng không chấp nhận callback | Không tạo sự kiện thành công của ứng dụng |
| TC-AS-06 | Authentication ACCEPTED rồi tạo phiên thất bại | Lịch sử giữ đúng hai kết quả, không đồng nhất thành công với phiên đã dùng |
| TC-AS-07 | Consumer nhận cùng event nhiều lần | Giữ một sự kiện logic theo hợp đồng dedup, không tăng số lần đăng nhập |
| TC-AS-08 | Hai ceremony độc lập của cùng một subject | Có hai sự kiện logic khác nhau, không gộp nhầm theo username |
| TC-AS-09 | Collector không sẵn sàng, sau đó phục hồi | Hành vi theo policy bền vững; retry giữ ID và thời điểm gốc |
| TC-AS-10 | Transaction ghi ACCEPTED hoặc outbox thất bại | Không phát hành sự kiện thành công cho trạng thái đã rollback |
| TC-AS-11 | Canary nằm trong credential, token và object upstream | Không có canary ở log, exporter, collector hoặc bản export bị cấm |
| TC-AS-12 | Input chứa xuống dòng, field quá dài hoặc nội dung giống JSON | Không tạo sự kiện giả hoặc vượt schema và giới hạn đã chốt |
| TC-AS-13 | Token refresh hoặc API request dùng token đã có | Không bị tính là ceremony LOGIN mới ngoài định nghĩa |
| TC-AS-14 | Vai trò không được phép hoặc tenant khác đọc audit | Không nhận sự kiện ngoài phạm vi quyền |
| TC-AS-15 | Replay hoặc restore bản ghi cũ | Giữ ID, thời điểm, nghĩa sự kiện; không coi là xác thực mới |
| TC-AS-16 | Pipeline trễ, sai schema hoặc backlog vượt ngưỡng fixture | Có trạng thái và tín hiệu theo hợp đồng, không im lặng bỏ dữ liệu |

### 13.2. Oracle không chỉ là tìm dòng “success”

Với một ca đăng nhập hoàn tất, cần đối chiếu ít nhất:

1. Những yếu tố và điều kiện bắt buộc thực sự đã được thực hiện.
2. Chuyển trạng thái ACCEPTED thuộc đúng authentication và chủ thể.
3. Event ID cùng bản ghi bền vững hoặc mức xác nhận được yêu cầu.
4. Schema và nguồn của từng field quan trọng.
5. Kết quả giao nhận trong cửa sổ quan sát đã chốt.
6. Việc xử lý trùng, bí mật và quyền đọc ở các đầu ra liên quan.

Không dùng credential thật để chạy thử chống lộ. Canary phải không có quyền truy cập thật và được đặt theo vị trí rõ ràng trong fixture.

Nếu exporter có độ trễ hoặc sampling, cần cấu hình và bằng chứng phù hợp để biết ca thử đã đi qua điểm quan sát. Với luồng yêu cầu audit đầy đủ, không thể dùng sampling tùy ý để thay thế việc ghi nhận từng sự kiện bắt buộc.

Một lần không tìm thấy secret ngay trong kho trung tâm chưa chứng minh secret không được gửi. Phải biết đường export đã chạy, các sink thuộc phạm vi và cửa sổ quan sát đủ điều kiện theo hợp đồng.

### 13.3. Đối soát tính đầy đủ

Đếm số dòng audit đơn thuần không cho biết có bao nhiêu authentication đã thiếu sự kiện, vì số dòng có thể bao gồm retry và bản ghi trùng.

Trong mô hình có trạng thái ACCEPTED bền vững, đối soát theo authentication ID với outbox và sự kiện logic ở consumer. Tách các trạng thái đang chờ gửi, bị từ chối schema, đã giao và chưa có bằng chứng nhận.

Nếu kiến trúc không có nguồn trạng thái đối chiếu tương ứng, phải mô tả cách đánh giá tính đầy đủ và giới hạn của nó. Không tuyên bố “đủ 100%” chỉ vì exporter báo không có lỗi trong một khoảng thời gian.

## 14. Vận hành, phát hiện bất thường và truy vết yêu cầu

### 14.1. Quan sát cả sự kiện lẫn pipeline

Các tín hiệu vận hành có thể gồm tuổi backlog, số lần retry, schema bị từ chối, độ trễ ingest và khoảng trống đối soát. Đặt ngưỡng theo yêu cầu của dự án; không lấy một giá trị trong fixture làm chuẩn cho mọi hệ thống.

Metric nên có tập nhãn được kiểm soát, như flow hoặc nhóm lỗi pipeline. Không dùng subject ID, event ID hoặc token làm label cho mỗi chuỗi thời gian.

Ở lớp phân tích có quyền phù hợp, các sự kiện thành công có thể được liên kết với thất bại trước đó, thay đổi phương thức hoặc phiên liên quan. Một kết quả bất thường là tín hiệu để xem xét theo mô hình đe dọa, không phải bằng chứng chắc chắn người dùng bị chiếm tài khoản.

Tự động phản ứng như yêu cầu xác thực lại hoặc thu hồi phiên cần chính sách riêng và kiểm chứng riêng. Sự tồn tại của một sự kiện success không tự trao quyền cho bất kỳ consumer nào khóa tài khoản.

### 14.2. Chuỗi truy vết minh họa

```text
R-AUTH-01: password đúng bị ghi nhầm là đăng nhập hoàn tất
  -> AS-01, AS-02, AS-06
  -> state machine có điểm ACCEPTED sau kiểm tra bắt buộc
  -> TC-AS-01, TC-AS-02, TC-AS-03, TC-AS-05
  -> bản ghi trạng thái, sự kiện logic và cấu hình policy
  -> kết luận trong phạm vi build, flow và fixture đã kiểm tra
```

Với rủi ro mất sự kiện, chuỗi truy vết cần bổ sung transaction, outbox, collector và đối soát. Với rủi ro lộ secret, cần theo đường dữ liệu tới từng sink và bản export.

Một hồ sơ nghiệm thu cần có phiên bản schema, build, policy revision, danh mục flow, cấu hình pipeline, ca đã chạy và phần chưa quan sát được. Chỉ báo PASS trong phạm vi có bằng chứng; không gộp khoảng trống về độ trễ, quyền truy cập hoặc nền tảng chưa thử thành kết quả đã đạt.

## 15. Những sai lầm làm sự kiện mất giá trị

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Ghi thành công trước khi đủ yếu tố | Tuyên bố sai về kết quả ceremony | Chốt một điểm ACCEPTED có ngữ nghĩa rõ |
| Dùng HTTP 200 làm bằng chứng | Lẫn trang hiển thị với kết quả xác thực | Quan sát trạng thái và sự kiện miền |
| Lấy username, tenant hoặc MFA flag từ client | Audit gán sai chủ thể hoặc mức bảo đảm | Dùng kết quả tin cậy và mapping được xác minh |
| Ghi nguyên principal hoặc authentication object | Có thể phát hành token, credential và profile | Dùng DTO allowlist riêng |
| Tạo event ID mới mỗi retry | Đếm trùng và khó đối soát | Giữ định danh sự kiện logic |
| Chỉ có log ở bộ nhớ nhưng gọi là audit bền vững | Mất dữ liệu khi tiến trình lỗi | Đặc tả mức xác nhận và đường lưu phù hợp |
| Mọi service đều ghi cùng loại success | Không xác định được nguồn có thẩm quyền | Phân biệt ranh giới và loại quan sát |
| Ghi thời điểm retry thành thời điểm đăng nhập | Sai lịch sử và tương quan | Giữ thời điểm gốc, tách ingest time |
| Dùng session token để đối chiếu | Kho audit chứa dữ liệu cấp quyền | Dùng reference độc lập không xác thực được |
| Gộp authn success với quyền nghiệp vụ | Hiểu sai rằng người dùng được làm mọi việc | Ghi và kiểm soát authorization riêng |
| Chỉ kiểm tra bản ghi có tồn tại | Bỏ sót sai chủ thể, trùng lặp và secret | Đối soát trạng thái, schema, nội dung và quyền |

## 16. Thực hành đặc tả cho hệ thống đăng nhập đa tenant

Một ứng dụng hỗ trợ password kèm OTP và đăng nhập liên kết. Một số thao tác yêu cầu step-up. Backend tạo session trong kho riêng, gửi log qua agent và cho quản trị tenant xem lịch sử đăng nhập. Hiện tại code ghi “success” sau khi password đúng, agent có thể retry, còn màn hình quản trị đếm mỗi dòng log là một lần đăng nhập.

Hãy xây dựng một đặc tả gồm:

1. Định nghĩa Authentication success cho LOGIN, STEP_UP và luồng liên kết.
2. Sơ đồ trạng thái cùng điểm không được phép phát sinh sự kiện thành công cuối.
3. Schema field, nguồn tin cậy và mục đích của từng định danh.
4. Quy tắc phân biệt authentication, session, token refresh và authorization.
5. Chính sách không ghi password, OTP, token, cookie và raw assertion.
6. Mức bền vững bắt buộc và hành vi khi kho phiên, outbox hoặc collector lỗi.
7. Quy tắc event ID, dedup, replay và thời điểm gốc.
8. Kiểm soát đọc lịch sử theo tenant và quyền export.
9. Ma trận ca đúng, ca thiếu OTP, callback không hợp lệ, retry và lộ canary.
10. Cách đối soát authentication được chấp nhận với sự kiện logic, cùng giới hạn bằng chứng.

Hồ sơ cần cho người khác xác định được hệ thống đã chấp nhận danh tính nào, theo điều kiện nào, ở ranh giới nào và bằng chứng đó đã được lưu hoặc còn đang thiếu ở đâu, trong khi dữ liệu dùng để xác thực vẫn được giữ ngoài sự kiện audit.
