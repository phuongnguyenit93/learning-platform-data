# Giảm dữ liệu nhạy cảm trong scope, snapshot và log

*Chương: Bảo vệ flow · Module: SPRING_WEB_FLOW*

Một flow nhiều bước có thể giữ dữ liệu qua nhiều request để người dùng tiếp tục nhập liệu, quay lại bước trước hoặc xác nhận giao dịch. Dữ liệu đó có thể nằm trong viewScope, flowScope, conversationScope, HTTP session hoặc trạng thái execution do repository quản lý. Nếu đưa quá nhiều thông tin nhạy cảm vào các vùng này, dữ liệu có thể tồn tại lâu hơn mục đích ban đầu và xuất hiện trong snapshot, bản sao session, log, hệ thống giám sát hoặc bản sao lưu.

Bảo vệ flow vì vậy bắt đầu từ việc quyết định dữ liệu nào thực sự cần được giữ. Một flow thường chỉ cần ID bản ghi, lựa chọn của người dùng, một DTO nhỏ và tham chiếu tới dữ liệu được lưu ở nơi có kiểm soát. Mật khẩu, mã xác thực, thông tin thanh toán đầy đủ, access token và nội dung bí mật không nên trở thành thuộc tính của model chỉ để thuận tiện cho bước tiếp theo.

Module SPRING_WEB_FLOW hướng tới mô hình hóa hành trình web bằng state, event, transition và subflow, đồng thời thực hành form binding, validation, quản lý scope và phiên, tích hợp Spring MVC, kiểm thử và phục hồi lỗi. Bài học này tập trung vào cách giảm dữ liệu nhạy cảm trong scope, snapshot và log để flow vẫn tiếp tục được qua nhiều bước mà không mở rộng bề mặt rò rỉ dữ liệu.

Sau bài học, bạn có thể:

- Nhận diện dữ liệu nhạy cảm có thể đi vào model, scope, snapshot và log.
- Chọn dữ liệu tối thiểu cần giữ theo từng bước của flow.
- Lưu ID hoặc tham chiếu có thời hạn thay cho bí mật và object chứa dữ liệu đầy đủ.
- Hiểu vì sao execution snapshot và session replication cần được xem như nơi lưu dữ liệu.
- Ghi log theo danh sách trường cho phép, tránh dump request hoặc flow scope.
- Áp dụng mã hóa, phân quyền, thời hạn lưu giữ và kiểm thử để giảm nguy cơ lộ dữ liệu.

## 1. Dữ liệu nhạy cảm trong một flow nhiều bước

Một quy trình đăng ký, thanh toán, phê duyệt hoặc cập nhật hồ sơ có thể xử lý nhiều loại dữ liệu khác nhau. Không phải mọi dữ liệu đều có mức độ rủi ro giống nhau.

| Nhóm dữ liệu | Ví dụ | Cách xử lý nên ưu tiên |
|---|---|---|
| Bí mật xác thực | Mật khẩu, mã OTP, recovery code, access token, refresh token | Không giữ trong flow scope hoặc log; chuyển trực tiếp tới thành phần xác thực chuyên trách |
| Dữ liệu thanh toán | Số thẻ đầy đủ, CVV, thông tin tài khoản ngân hàng | Dùng nhà cung cấp thanh toán hoặc vault; flow chỉ giữ tham chiếu nghiệp vụ cần thiết |
| Định danh cá nhân | Số giấy tờ, ngày sinh, địa chỉ nhà, dữ liệu hồ sơ | Chỉ giữ trường cần thiết, giới hạn quyền truy cập và thời hạn |
| Dữ liệu nghiệp vụ | Mã đơn, trạng thái, lựa chọn vận chuyển, số lượng | Giữ trong DTO nhỏ nếu flow cần qua nhiều bước |
| Tham chiếu kỹ thuật | Flow ID, state ID, correlation ID, execution key | Chỉ ghi trường cần thiết; execution key và token tiếp tục phiên phải được xem là dữ liệu có khả năng cấp quyền |
| Dữ liệu công khai hoặc ít nhạy cảm | Tên loại sản phẩm, nhãn giao diện | Có thể hiển thị và log theo chính sách thông thường |

Mức độ nhạy cảm phải được xác định theo bối cảnh. Một mã khách hàng có thể không phải bí mật khi đứng riêng, nhưng khi ghép với địa chỉ, đơn hàng hoặc thông tin sức khỏe thì có thể nhận diện một cá nhân. Dữ liệu đã che một phần cũng có thể nhạy cảm nếu còn kết hợp được với nguồn khác.

Không nên chỉ tìm những trường có tên password hoặc token. Hãy kiểm tra cả object graph: một DTO có thể tham chiếu tới entity, entity lại có quan hệ tới hồ sơ cá nhân hoặc đối tượng chứa credential. Nếu đưa object graph đó vào scope, toàn bộ phần dữ liệu được tham chiếu có thể trở thành một phần của trạng thái flow.

## 2. Vì sao scope và snapshot là bề mặt lưu trữ?

Scope là nơi flow giữ dữ liệu theo vòng đời. Một số scope thường gặp:

| Scope | Vòng đời điển hình | Câu hỏi bảo mật |
|---|---|---|
| requestScope | Request hiện tại | Có thể xử lý xong rồi bỏ dữ liệu ngay không? |
| flashScope | Qua lần chuyển tiếp/render kế tiếp | Thông báo có vô tình chứa dữ liệu cá nhân hoặc bí mật không? |
| viewScope | Khi view state còn hoạt động | View có thật sự cần toàn bộ object này không? |
| flowScope | Suốt flow execution | Dữ liệu có cần tồn tại qua tất cả bước không? |
| conversationScope | Conversation gốc và các subflow liên quan | Những flow con nào có thể nhìn thấy dữ liệu này? |
| applicationScope | Dùng chung trong ứng dụng | Dữ liệu có thực sự công khai, bất biến và an toàn khi chia sẻ không? |

Đặt một giá trị trong scope có nghĩa là giá trị đó có thể sống lâu hơn request tạo ra nó. Đặt trong flowScope không tự động làm dữ liệu được mã hóa hoặc giới hạn quyền truy cập. Scope chỉ giải quyết vòng đời và khả năng truy cập trong mô hình flow; nó không thay thế cơ chế bảo mật.

Flow execution repository quản lý việc lưu và khôi phục execution. Tùy repository, cấu hình và phiên bản, trạng thái có thể được giữ trong HTTP session phía server, được tạo thành snapshot/continuation hoặc đi qua một cơ chế lưu trữ khác. Khi có session replication, persistence hoặc snapshot, object trong execution có thể được sao chép hoặc lưu lâu hơn request ban đầu.

Vì vậy, hãy coi mọi object trong scope là dữ liệu có khả năng được lưu, sao chép hoặc quan sát bởi thành phần hạ tầng có quyền truy cập tương ứng. Đừng giả định rằng dữ liệu trong flowScope chỉ nằm trong RAM của một request. Cần xác định repository thực tế đang dùng và nơi snapshot/session được lưu, nhưng nguyên tắc an toàn vẫn là không đưa bí mật không cần thiết vào execution.

Một snapshot không phải bản sao chỉ chứa những trường mà view đang hiển thị. Nếu snapshot serialize trạng thái execution, object graph trong scope có thể được đưa vào đó. Việc xóa một trường khỏi giao diện không đồng nghĩa trường đó đã bị loại khỏi snapshot hoặc log.

## 3. Tối thiểu hóa dữ liệu theo từng bước

Trước khi thêm một thuộc tính vào flow model, hãy xác định bước nào cần nó và trong bao lâu. Nếu chỉ cần để xác minh ở một thao tác, hãy chuyển giá trị cho service trong request đó rồi bỏ đi. Nếu cần qua nhiều bước, cân nhắc giữ một bản nháp đã loại bỏ trường nhạy cảm. Nếu cần dữ liệu đầy đủ, lưu ở hệ thống chuyên trách và giữ một tham chiếu có kiểm soát.

Ví dụ, một flow thanh toán có thể cần:

- Mã đơn hàng để tải lại dữ liệu nghiệp vụ.
- Lựa chọn phương thức thanh toán.
- Nhãn phương thức đã che để người dùng xác nhận.
- Một tham chiếu thanh toán do nhà cung cấp cấp, nếu quy trình cần tiếp tục trạng thái thanh toán.

Flow không cần giữ số thẻ đầy đủ, CVV, mật khẩu ngân hàng, OTP hoặc access token của nhà cung cấp. Những giá trị này nên được xử lý trực tiếp tại thành phần được phép nhận chúng và không đi qua các bước flow không cần thiết.

Một DTO gọn có thể như sau:

~~~java
public class CheckoutDraft {
    private String orderId;
    private String paymentMethod;
    private String paymentReferenceId;
    private String maskedPaymentLabel;
    private boolean termsAccepted;

    // getters và setters
}
~~~

Đối tượng này giữ mã đơn và thông tin lựa chọn cần thiết cho flow. paymentReferenceId chỉ là tham chiếu tới một giao dịch được quản lý ở hệ thống thanh toán; nó không nên là credential có thể tự do dùng để thực hiện thanh toán. Nếu nhà cung cấp trả về một token có quyền thực hiện giao dịch, hãy coi token đó là bí mật: chỉ giữ trong thời gian ngắn, giới hạn quyền, không ghi log và ưu tiên giữ ở backend vault/service thay vì scope.

Flow có thể khởi tạo draft và giữ trong flowScope:

~~~xml
<on-start>
    <evaluate expression="checkoutService.createDraft()"
              result="flowScope.checkoutDraft"/>
</on-start>

<view-state id="paymentChoice" view="checkout/payment-choice">
    <binder>
        <binding property="paymentMethod"/>
        <binding property="termsAccepted"/>
    </binder>
    <transition on="continue" to="review">
        <evaluate expression="checkoutService.preparePayment(
            flowScope.checkoutDraft)"/>
    </transition>
</view-state>
~~~

Binder chỉ cho phép nhận các trường người dùng được phép thay đổi. Không bind paymentReferenceId, orderId hoặc trạng thái thanh toán đã được server xác định chỉ vì các thuộc tính đó có mặt trong DTO. Service phải tự kiểm tra quyền, trạng thái đơn hàng và tham chiếu thanh toán trước khi thực hiện thao tác.

## 4. Giữ tham chiếu thay cho dữ liệu đầy đủ

Khi một bước cần dữ liệu nhạy cảm mà các bước sau vẫn phải tiếp tục, hãy cân nhắc lưu dữ liệu đó trong một hệ thống phía server có kiểm soát. Flow chỉ giữ một ID hoặc handle ngẫu nhiên để tìm lại dữ liệu khi cần.

Ví dụ, thay vì đưa toàn bộ hồ sơ xác minh vào flowScope, service có thể tạo một verificationRecordId. Khi flow tới bước cần kiểm tra, service tải hồ sơ theo ID, xác minh người dùng hiện tại có quyền truy cập và chỉ trả về những trường view cần hiển thị.

Một tham chiếu an toàn cần có các thuộc tính:

- Không thể đoán dễ dàng; dùng giá trị ngẫu nhiên đủ mạnh hoặc ID nội bộ không tuần tự.
- Gắn với người dùng, tenant hoặc chủ thể nghiệp vụ phù hợp.
- Có thời hạn sử dụng và trạng thái thu hồi.
- Chỉ cấp quyền cho đúng thao tác cần thiết.
- Được kiểm tra quyền ở service mỗi lần sử dụng.
- Không xuất hiện trong log, URL công khai hoặc thông báo lỗi.

Một ID khó đoán không thay thế authorization. Người dùng có thể sửa request, gửi ID từ một flow khác hoặc dùng lại ID đã hết hạn. Service cần kiểm tra chủ sở hữu, trạng thái và quyền tại thời điểm thao tác.

Ví dụ service chỉ trả dữ liệu đã được rút gọn:

~~~java
public VerificationSummary loadSummary(
        String verificationRecordId,
        UserPrincipal currentUser) {

    VerificationRecord record =
            verificationRepository.findById(verificationRecordId)
                    .orElseThrow(VerificationNotFoundException::new);

    authorizationService.checkCanView(record, currentUser);

    return new VerificationSummary(
            record.getPublicReference(),
            record.getMaskedDocumentLabel(),
            record.getStatus());
}
~~~

Flow giữ VerificationSummary hoặc verificationRecordId. Service không trả toàn bộ entity chứa số giấy tờ và tài liệu đính kèm nếu view chỉ cần nhãn đã che cùng trạng thái.

## 5. Giảm dữ liệu trong snapshot và session

Snapshot có thể chứa trạng thái flow tại một thời điểm để hỗ trợ tiếp tục, quay lại hoặc khôi phục execution. Nếu object trong flowScope chứa bí mật, snapshot có thể trở thành một bản sao khác của bí mật đó. Tương tự, session replication, cache, persistence store và backup có thể kéo dài thời gian tồn tại của dữ liệu.

Các nguyên tắc thiết kế:

1. Không đặt password, OTP, CVV, private key, refresh token hoặc access token dài hạn vào scope.
2. Không đưa entity graph có dữ liệu nhạy cảm vào flow chỉ để view đọc vài thuộc tính.
3. Chỉ giữ DTO nhỏ với trường đã được chọn lọc.
4. Với dữ liệu cần giữ lâu, dùng kho dữ liệu chuyên trách, có mã hóa, quyền truy cập và TTL.
5. Không serialize request, response, security context hoặc tài nguyên đang mở cùng execution.
6. Kiểm tra cấu hình repository và nơi snapshot thực sự được lưu trước khi quyết định biện pháp bảo vệ.

Mã hóa snapshot hoặc session storage có thể giảm nguy cơ khi dữ liệu lưu trữ bị truy cập trái phép, nhưng không thay thế data minimization. Ứng dụng vẫn phải giải mã dữ liệu để xử lý; tài khoản ứng dụng hoặc người có quyền truy cập runtime có thể nhìn thấy nội dung. Giữ ít dữ liệu vẫn là biện pháp giảm tác động hiệu quả nhất.

Nếu snapshot được lưu ở database hoặc cache, hãy áp dụng quyền truy cập tối thiểu, mã hóa at rest, quản lý khóa riêng với dữ liệu và chính sách backup/retention. Nếu trạng thái được truyền qua client theo một cơ chế triển khai cụ thể, phải kiểm tra tính toàn vẹn, xác thực và khả năng đọc nội dung; không đưa bí mật vào client-carried state chỉ vì payload được ký hoặc mã hóa.

## 6. Bảo vệ flashScope và thông báo chuyển bước

flashScope thường được dùng để truyền thông báo qua một lần chuyển tiếp. Vì tồn tại ngắn hạn, nó dễ bị xem là nơi an toàn để đặt dữ liệu tạm. Tuy nhiên, thông báo vẫn có thể được render vào HTML, lưu trong session hoặc xuất hiện trong log nếu ứng dụng ghi model.

Thông báo phù hợp:

- Đã lưu thay đổi.
- Không thể tiếp tục vì phiên đã hết hạn.
- Thao tác đang được xử lý; vui lòng kiểm tra trạng thái sau.
- Dữ liệu đã thay đổi; hãy tải lại trước khi xác nhận.

Thông báo không phù hợp:

- In lại mã OTP hoặc access token.
- Hiển thị số giấy tờ đầy đủ hoặc số tài khoản.
- Chứa toàn bộ nội dung exception hoặc request.
- Đính kèm URL có token tiếp tục phiên hoặc token reset mật khẩu.

Hãy đưa message code hoặc một câu ngắn đã được kiểm soát vào flashScope. Không đưa đối tượng exception vào scope rồi để view tự gọi getMessage(). Chi tiết kỹ thuật nên ở log bảo vệ, còn người dùng chỉ nhận nội dung cần thiết để tiếp tục.

## 7. Ghi log theo allowlist

Log giúp điều tra sự cố và theo dõi flow, nhưng ghi toàn bộ request, model hoặc scope có thể biến log thành kho dữ liệu nhạy cảm. Các câu lệnh debug như in toàn bộ flowScope, request parameters, headers, cookies hoặc DTO bằng toString() đặc biệt nguy hiểm.

Thay vì ghi mọi thứ rồi cố che một vài trường, hãy chọn trước những trường an toàn được phép ghi:

| Trường có thể ghi theo chính sách | Trường cần tránh hoặc kiểm soát nghiêm ngặt |
|---|---|
| Tên flow đã được phê duyệt, state ID, event name từ danh sách cố định | Toàn bộ request body hoặc model |
| Kết quả xử lý, loại exception đã chuẩn hóa | Exception message có thể chứa dữ liệu người dùng |
| Thời gian xử lý, mã correlation nội bộ | Password, OTP, CVV, access/refresh token |
| ID nghiệp vụ đã pseudonymize hoặc mã tham chiếu không cấp quyền | Số giấy tờ, số tài khoản hoặc dữ liệu thanh toán đầy đủ |
| Mã lỗi và phiên bản ứng dụng | Cookie, Authorization header, session ID và execution key |

Flow ID và state ID thường hữu ích cho chẩn đoán, nhưng không nên chứa tên người dùng, email, số đơn có thể nhận diện cá nhân hoặc bí mật. Event name nên lấy từ tập giá trị do ứng dụng định nghĩa, không ghi nội dung tùy ý do client gửi lên.

Ví dụ log theo allowlist:

~~~java
logger.info(
        "flow_transition flow={} state={} event={} outcome={} correlationId={}",
        safeFlowId,
        safeStateId,
        knownEventName,
        outcome,
        correlationId);
~~~

Các giá trị safeFlowId, safeStateId và knownEventName phải được lấy từ metadata đã kiểm soát, không lấy trực tiếp từ chuỗi request tùy ý. correlationId là mã truy vết nội bộ không mang quyền tiếp tục flow. Không thêm toàn bộ DTO hoặc scope vào tham số logger.

Nếu cần log lỗi:

~~~java
logger.error(
        "flow_action_failed flow={} state={} errorType={} correlationId={}",
        safeFlowId,
        safeStateId,
        exception.getClass().getSimpleName(),
        correlationId);
~~~

Đoạn mã chỉ ghi loại exception. Với sự cố cần stack trace đầy đủ, hãy gửi chi tiết tới hệ thống chẩn đoán có quyền truy cập giới hạn, redaction, retention và audit phù hợp. Exception message hoặc stack trace có thể chứa SQL, đường dẫn, giá trị đầu vào hoặc dữ liệu nhạy cảm; không tự động đưa chúng vào log có phạm vi truy cập rộng.

## 8. Redaction, masking và pseudonymization

Ba kỹ thuật này có mục đích khác nhau:

- **Masking** che một phần giá trị để hiển thị, ví dụ chỉ hiện bốn ký tự cuối của một mã tham chiếu. Masking không làm dữ liệu gốc biến mất khỏi object.
- **Redaction** loại bỏ trường hoặc thay nội dung bằng ký hiệu trước khi ghi log hay xuất dữ liệu.
- **Pseudonymization** thay định danh trực tiếp bằng mã thay thế; có thể liên kết lại nếu còn bảng ánh xạ hoặc khóa tương ứng.

Không nên coi masking là biện pháp bảo vệ storage. Nếu DTO vẫn chứa số tài khoản đầy đủ và chỉ view hiển thị dạng che, snapshot hoặc log object dump vẫn có thể lộ giá trị gốc. Hãy loại trường nhạy cảm khỏi DTO trước khi đưa vào scope.

Khi cần log một định danh để nối sự kiện, dùng mã tham chiếu nội bộ hoặc pseudonymous identifier. Nếu dùng hash, cân nhắc dữ liệu đầu vào có ít khả năng đoán; hash thuần của email hoặc số điện thoại có thể bị dò bằng từ điển. Có thể dùng HMAC với khóa được quản lý riêng khi cần một định danh ổn định mà không công khai giá trị gốc.

Redaction nên diễn ra trước khi dữ liệu đi vào log appender, trace exporter hoặc hệ thống phân tích. Chỉ lọc ở giao diện dashboard là quá muộn vì bản ghi gốc đã được lưu.

## 9. Mã hóa, phân quyền và thời hạn lưu giữ

Nếu một dữ liệu nhạy cảm thực sự cần được lưu ở backend, hãy bảo vệ cả khi truyền và khi lưu:

- Dùng TLS cho request và kết nối tới hệ thống lưu trữ.
- Mã hóa dữ liệu nhạy cảm at rest bằng cơ chế đã được nền tảng hỗ trợ.
- Quản lý khóa trong secret manager hoặc KMS; không đặt khóa cùng file snapshot hoặc repository.
- Giới hạn quyền đọc/ghi theo service account và vai trò vận hành.
- Ghi audit cho thao tác đọc hoặc thay đổi dữ liệu có mức nhạy cảm cao.
- Xác định TTL và quy trình xóa ở storage, cache, snapshot, log và backup.

Mã hóa không ngăn được một ứng dụng đã có quyền giải mã ghi dữ liệu ra log. Vì vậy, vẫn cần allowlist log và kiểm soát đường đi dữ liệu.

Flow execution timeout và session timeout không tự động xóa bản sao dữ liệu ở mọi nơi. Snapshot, backup, log, cache và kho dữ liệu ngoài có vòng đời riêng. Hãy xác định thời hạn ở từng nơi, cách xóa bản ghi hết hạn và cách xử lý bản backup theo chính sách retention.

Khi người dùng đăng xuất, session cần được vô hiệu hóa theo cấu hình bảo mật của ứng dụng. Cookie phiên nên dùng các thuộc tính phù hợp như Secure, HttpOnly và SameSite theo luồng xác thực. Khi xác thực thành công hoặc thay đổi mức quyền, cần áp dụng chính sách quản lý session để giảm nguy cơ session fixation. Các biện pháp này bổ sung cho việc giảm dữ liệu trong scope.

## 10. Tránh rò rỉ qua URL, exception và giao diện

Dữ liệu nhạy cảm có thể rò rỉ dù không nằm trong flowScope:

- Query string có thể được lưu trong browser history, access log, proxy log và referrer.
- Redirect URL có thể vô tình mang token hoặc dữ liệu cá nhân.
- Trang lỗi có thể render exception message, stack trace hoặc dữ liệu binding.
- Hidden field vẫn do client kiểm soát và có thể được đọc hoặc sửa.
- HTML source và JavaScript state có thể chứa giá trị mà người dùng không cần nhìn thấy.
- Debug log của framework có thể ghi request parameter hoặc model nếu bật quá rộng.

Không truyền mật khẩu, OTP, access token hoặc token reset qua URL. Không xem hidden input là vùng lưu bí mật. Dữ liệu nhạy cảm cần được gửi qua kênh phù hợp, xác thực và xử lý ngay tại server.

Nếu một giá trị được trả về view, chỉ hiển thị phần người dùng cần xác nhận. Không đưa toàn bộ object vào model khi template chỉ cần một nhãn. Với lỗi binding, hiển thị thông báo đã chuẩn hóa thay vì giá trị nhạy cảm đã nhập lại trong nội dung lỗi.

## 11. Phân quyền mỗi lần đọc lại dữ liệu

Lưu một ID trong flowScope không có nghĩa người dùng được quyền truy cập bản ghi đó mãi mãi. Quyền có thể bị thu hồi, bản ghi có thể chuyển chủ sở hữu hoặc trạng thái có thể thay đổi giữa các bước.

Khi service tải dữ liệu theo tham chiếu, cần:

1. Xác định người dùng hiện tại từ security context đáng tin cậy.
2. Tải bản ghi theo ID hoặc handle.
3. Kiểm tra quyền truy cập và phạm vi tenant.
4. Kiểm tra trạng thái nghiệp vụ hiện tại.
5. Chỉ trả DTO với trường cần thiết cho state hiện tại.
6. Kiểm tra lại trước thao tác ghi hoặc hành động có side effect.

Không dùng ownerId do form gửi lên làm căn cứ duy nhất cho authorization. Giá trị chủ sở hữu cần được lấy từ bản ghi hoặc security context phía server. Không dựa vào việc flow đã xác thực người dùng ở bước đầu để bỏ qua kiểm tra quyền ở bước sau.

## 12. Kiểm thử dữ liệu nhạy cảm trong scope, snapshot và log

Kiểm thử cần xác minh dữ liệu bí mật không đi vào những nơi không được phép, chứ không chỉ kiểm tra view đã che dữ liệu.

| Kịch bản | Cách kiểm thử | Kết quả mong muốn |
|---|---|---|
| Form nhận dữ liệu xác thực | Kiểm tra model và scope sau binding | Chỉ giữ trạng thái tối thiểu; không giữ raw secret |
| Flow tạo snapshot/continuation | Kiểm tra dữ liệu được lưu theo cấu hình repository | Không có bí mật không cần thiết trong object graph |
| Flow chuyển qua subflow | Kiểm tra input/output và conversation scope | Chỉ chia sẻ dữ liệu được phép |
| Logging transition | Thu log trong test | Không có request body, cookie, token hoặc dữ liệu nhạy cảm |
| Exception chứa dữ liệu đầu vào | Kiểm tra log và phản hồi | Người dùng nhận message an toàn; log tuân theo redaction |
| Tham chiếu bị sửa bởi client | Gọi service với ID của người khác | Authorization từ chối truy cập |
| Execution hết hạn | Tiếp tục bằng execution key cũ | Không phục hồi dữ liệu của người dùng khác |
| Dữ liệu tạm hết TTL | Chạy cleanup hoặc truy vấn storage | Bản ghi hết hạn bị xóa hoặc vô hiệu hóa theo chính sách |
| Session replication/backup | Kiểm tra cấu hình và bản ghi thử nghiệm trong môi trường kiểm soát | Snapshot và backup được bảo vệ, retention rõ ràng |

Có thể dùng một chuỗi sentinel giả lập, ví dụ SECRET-SHOULD-NOT-APPEAR, trong test để tìm xem giá trị đó có xuất hiện trong log capture hoặc snapshot test hay không. Chỉ dùng dữ liệu giả, không dùng bí mật production để kiểm thử.

Kiểm thử cũng nên xác minh rằng masking chỉ áp dụng cho phần trình bày và trường nhạy cảm đã được loại khỏi DTO/scope khi không cần. Một test giao diện cho thấy chỉ hiện bốn ký tự cuối chưa chứng minh snapshot không chứa giá trị đầy đủ.

## 13. Lỗi thiết kế thường gặp

| Cách làm | Rủi ro | Cách điều chỉnh |
|---|---|---|
| Lưu toàn bộ entity hoặc request trong flowScope | Snapshot và log có thể kéo theo nhiều trường nhạy cảm | Dùng DTO nhỏ và chỉ giữ trường cần thiết |
| Cho rằng flowScope không được lưu lâu dài | Dữ liệu có thể được giữ trong session, snapshot hoặc repository | Kiểm tra cấu hình execution storage và thiết kế theo giả định dữ liệu có thể được lưu |
| Chỉ che dữ liệu trên giao diện | Giá trị gốc vẫn còn trong model và snapshot | Loại trường nhạy cảm khỏi DTO trước khi bind hoặc lưu |
| Ghi toàn bộ flowScope để debug | Log trở thành bản sao của dữ liệu người dùng | Ghi theo allowlist và mã tham chiếu |
| Ghi execution key vào log | Có thể làm lộ khả năng tiếp tục flow | Che hoặc loại khỏi log |
| Đưa token vào flashScope để dùng ở bước sau | Token có thể xuất hiện trong session, view hoặc snapshot | Giữ ở backend service/vault và chỉ truyền tham chiếu |
| Chỉ kiểm tra quyền ở bước đầu | Quyền có thể thay đổi trước thao tác cuối | Kiểm tra quyền mỗi lần đọc hoặc ghi dữ liệu |
| Chỉ dựa vào session timeout để xóa dữ liệu | Snapshot, log và backup có thể tồn tại lâu hơn | Có retention và cleanup riêng cho từng storage |

## 14. Quy trình thiết kế an toàn cho một flow

Khi xây dựng hoặc rà soát flow có dữ liệu nhạy cảm, hãy thực hiện theo thứ tự:

1. Lập danh sách trường dữ liệu được nhận, tạo ra, đọc lại và ghi log trong từng state.
2. Phân loại dữ liệu theo mức nhạy cảm và xác định mục đích sử dụng.
3. Loại bỏ trường không cần thiết; thay dữ liệu đầy đủ bằng ID, summary hoặc tham chiếu có thời hạn.
4. Giới hạn binder để client chỉ có thể cập nhật những trường được phép.
5. Xác định scope theo vòng đời ngắn nhất có thể và chỉ chia sẻ dữ liệu qua subflow khi cần.
6. Kiểm tra execution repository, snapshot, session replication, cache và backup.
7. Thiết kế log theo allowlist; che hoặc loại các định danh có thể cấp quyền.
8. Bảo vệ storage bằng mã hóa, phân quyền, audit và retention.
9. Kiểm tra authorization và trạng thái dữ liệu mỗi lần service sử dụng tham chiếu.
10. Viết test tìm sentinel trong scope, snapshot và log, đồng thời kiểm tra flow hết hạn và cleanup.

Một flow được thiết kế tốt cho phép nhóm phát triển trả lời rõ: dữ liệu nào đang được giữ, ai có thể đọc, nó tồn tại bao lâu, được lưu ở đâu và cách xóa là gì. Nếu không trả lời được những câu hỏi này, cần giảm dữ liệu trong model và làm rõ trách nhiệm của storage trước khi mở rộng flow.

## Kết luận

Scope, execution snapshot, session và log đều có thể trở thành nơi lưu dữ liệu nhạy cảm. Biện pháp quan trọng nhất là chỉ giữ dữ liệu cần thiết cho hành trình: DTO nhỏ, ID và tham chiếu có thời hạn. Bí mật xác thực và dữ liệu thanh toán đầy đủ nên được xử lý bởi thành phần chuyên trách, không đi qua các state không cần chúng.

Kết hợp data minimization với binder giới hạn, authorization ở mỗi lần truy cập, log theo allowlist, mã hóa, retention và kiểm thử rò rỉ sẽ giúp flow tiếp tục được qua nhiều request mà vẫn giảm đáng kể nguy cơ lộ dữ liệu trong scope, snapshot và hệ thống quan sát.
