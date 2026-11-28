# Governance evidence

## 1. Governance evidence là gì?

**Governance evidence** là tập thông tin có nguồn gốc, ngữ cảnh và khả năng kiểm tra, được dùng để chứng minh một quyết định quản trị danh tính hoặc một kiểm soát quyền truy cập đã được thiết kế, thực hiện và theo dõi như thế nào.

Trong IAM, bằng chứng cần giúp trả lời những câu hỏi cụ thể:

- Ai là chủ thể được cấp hoặc bị thu hồi quyền?
- Quyền nào, trên tài nguyên và phạm vi nào?
- Nhu cầu nghiệp vụ và chính sách nào cho phép quyết định?
- Ai đã phê duyệt, người đó có thẩm quyền gì ở thời điểm phê duyệt?
- Hệ thống nào đã thực hiện thay đổi và khi nào?
- Kết quả thực tế đã được kiểm tra đến mức nào?
- Điều gì chưa được xác minh, ai chịu trách nhiệm xử lý tiếp?

Một dòng ghi “approved” trả lời được rất ít trong số đó. Tương tự, một log “job succeeded” chưa đủ chứng minh quyền truy cập có hiệu lực đúng như yêu cầu.

Bằng chứng quản trị có giá trị khi nối được **ý định có thẩm quyền, hành động đã thực hiện và trạng thái đã xác minh**, đồng thời nêu rõ phạm vi cùng giới hạn của kết luận.

## 2. Bằng chứng phải gắn với một khẳng định cụ thể

Không nên thu thập dữ liệu trước rồi mặc định mọi dữ liệu đều chứng minh được việc quản trị đúng. Cần xác định khẳng định muốn kiểm tra.

Ví dụ:

> Các yêu cầu cấp vai trò phê duyệt hoàn tiền trong ứng dụng A, thuộc phạm vi chiến dịch X, phải có phê duyệt hợp lệ trước khi cấp.

Khẳng định này khác với:

> Người đã nghỉ việc không còn đường truy cập nào vào ứng dụng A sau thời điểm hiệu lực thu hồi.

Khẳng định thứ nhất tập trung vào thẩm quyền và thứ tự xử lý. Khẳng định thứ hai còn đòi hỏi xác minh tài khoản, quyền, phiên và những đường truy cập liên quan trong kiến trúc thực tế.

Một kết luận nên đi cùng bốn yếu tố:

```text
Khẳng định cần chứng minh
    + Phạm vi đối tượng và hệ thống
    + Mốc hoặc khoảng thời gian
    + Bằng chứng và giới hạn quan sát
```

“Đã xóa quan hệ thành viên nhóm G của tài khoản T lúc 09:10” cụ thể và kiểm tra được hơn “người dùng đã hết mọi quyền”. Nếu hệ thống chỉ quan sát được nhóm G, không nên mở rộng kết luận sang đăng nhập cục bộ, quyền trực tiếp hoặc phiên đang hoạt động.

### Thiết kế kiểm soát và vận hành kiểm soát

Cần phân biệt bằng chứng về cách kiểm soát được thiết kế với bằng chứng kiểm soát đã hoạt động trên các trường hợp thực tế.

| Loại bằng chứng | Ví dụ | Chưa tự chứng minh được |
|---|---|---|
| Thiết kế và cấu hình | Chính sách yêu cầu phê duyệt trước khi cấp đặc quyền | Mọi lần cấp thực tế đã đi qua chính sách đó |
| Vận hành | Một yêu cầu có quyết định phê duyệt trước thời điểm thực thi | Toàn bộ yêu cầu trong kỳ đều đáp ứng điều kiện |
| Trạng thái | Snapshot quyền được đọc lại tại đích | Quyền chưa từng bị cấp sai ở thời điểm trước đó |
| Theo dõi và khắc phục | Phát hiện quyền sai, ticket xử lý và kết quả xác minh | Nguyên nhân đã được loại bỏ trên mọi hệ thống |

Cấu hình tốt, một trường hợp xử lý tốt và một báo cáo tổng hợp là những lớp bằng chứng khác nhau. Chúng bổ sung cho nhau nhưng không thay thế nhau.

## 3. Chuỗi bằng chứng của một thay đổi quyền

Một thay đổi quyền truy cập có thể tạo ra nhiều bản ghi ở nhiều hệ thống:

```text
Sự kiện vòng đời hoặc yêu cầu truy cập
    → Đánh giá chính sách
    → Quyết định của người có thẩm quyền
    → Job provisioning/deprovisioning
    → Thay đổi tại hệ thống đích
    → Readback và đối soát
    → Kết luận, ngoại lệ hoặc việc khắc phục còn mở
```

Mỗi mắt xích trả lời một nhóm câu hỏi riêng.

### Ý định và căn cứ

Nguồn đầu vào có thể là sự kiện tuyển dụng, chuyển bộ phận, nghỉ việc, yêu cầu dự án hoặc yêu cầu quyền tạm thời.

Bằng chứng cần xác định nguồn có thẩm quyền, chủ thể, thời điểm hiệu lực và phiên bản của thay đổi. Nếu sử dụng dữ liệu nhân sự, tên hiển thị không nên là định danh duy nhất vì tên có thể trùng hoặc thay đổi.

Một yêu cầu cũng cần mô tả nhu cầu đủ rõ. “Xin quyền để làm việc” không giúp giải thích vì sao cần quyền quản trị thay vì quyền chỉ đọc.

### Đánh giá và quyết định

Bản ghi quyết định cần cho biết:

- Đối tượng và quyền được quyết định.
- Phiên bản hoặc nội dung chính sách đã được áp dụng.
- Kết quả kiểm tra điều kiện, phê duyệt hoặc xung đột liên quan.
- Người hoặc cơ chế tự động đưa ra quyết định.
- Căn cứ thẩm quyền ở thời điểm quyết định.
- Thời điểm, giới hạn phạm vi và ngày hết hạn nếu có.

Chỉ lưu ID reviewer chưa chắc đủ để chứng minh thẩm quyền lịch sử. Người đó có thể đổi vai trò sau này. Cần giữ hoặc tham chiếu được thông tin cho biết tại sao họ có quyền phê duyệt vào thời điểm đó.

### Thực thi

Bản ghi thực thi cần liên kết quyết định với thao tác cụ thể. Một yêu cầu có thể sinh nhiều job, và một job có thể có nhiều lần thử.

Cần phân biệt:

```text
requestId: ý định hoặc yêu cầu
decisionId: quyết định có thẩm quyền
operationId: thao tác thay đổi cụ thể
attemptId: một lần thử thực hiện thao tác
```

Nếu chỉ dùng một ID chung và liên tục ghi đè kết quả, có thể mất dấu lần thử thất bại, hành động bù trừ hoặc thay đổi một phần.

### Xác minh và khắc phục

Bằng chứng xác minh cần chỉ ra trạng thái được quan sát ở đâu, lúc nào và điều kiện nào đã được kiểm tra.

Nếu thao tác thu hồi thất bại hoặc không rõ kết quả, chuỗi bằng chứng phải tiếp tục đến chủ sở hữu xử lý, quyết định giảm rủi ro và kết quả sau khắc phục. Không kết thúc chuỗi tại một ticket đã mở.

## 4. Mô hình bằng chứng theo đối tượng và quan hệ

Quyền IAM thường được hình thành qua nhiều quan hệ, không phải một cột “role” trên hồ sơ người dùng.

```text
Danh tính → tài khoản → nhóm → vai trò → quyền → tài nguyên
```

Một tài khoản còn có thể có quyền trực tiếp, nhận quyền qua nhiều nhóm hoặc chịu điều kiện theo thuộc tính. Bằng chứng cần giữ đủ thông tin để tái dựng đường cấp trong phạm vi được đánh giá.

### Những định danh cần ổn định

Nên liên kết chủ thể nguồn với tài khoản đích bằng các định danh và quan hệ đối sánh được quản lý. Không dùng email, tên đăng nhập hoặc tên nhóm hiển thị làm bằng chứng duy nhất khi những giá trị này có thể thay đổi hoặc tái sử dụng.

Đối với quyền, cần phân biệt ID quyền với mô tả mà reviewer đọc. Nếu vai trò thay đổi thành phần, bằng chứng lịch sử cần nhận diện được phiên bản hoặc snapshot định nghĩa vai trò đã được dùng.

### Dữ liệu khái niệm của một hồ sơ

```yaml
evidenceId: evidence-730
claim:
  type: entitlement-revocation
  subjectId: person-284
  targetAccountId: account-762
  entitlementId: payment-approve
  resourceScope: business-unit-south
context:
  lifecycleRevision: 52
  policyRevision: iam-policy-18
links:
  decisionId: decision-410
  operationId: operation-620
  verificationId: verification-905
provenance:
  sourceSystem: payment-app
  sourceRecordId: account-762
  collectorId: collector-payment-read
  observedAt: "2026-11-26T09:12:00Z"
result:
  status: PARTIALLY_VERIFIED
  verifiedFact: Direct assignment no longer present
  unresolvedFact: Group-based grant not yet verified
```

Đây là ví dụ mô hình dữ liệu minh họa, không phải schema bắt buộc hoặc cấu hình của một sản phẩm. Các giá trị ID và thời gian chỉ nhằm diễn giải.

Hồ sơ không cần chứa mọi dữ liệu gốc trong một bản ghi. Nó có thể tham chiếu đến các nguồn khác, nhưng những tham chiếu đó phải còn truy cập được trong thời gian cần lưu bằng chứng. Một URL dẫn đến màn hình luôn hiển thị dữ liệu mới nhất không tự bảo toàn trạng thái lịch sử.

### Danh tính workload

Với tài khoản dịch vụ hoặc workload identity, cần có thêm chủ sở hữu hoặc người bảo trợ, ứng dụng sử dụng, môi trường, mục đích và vòng đời dự kiến.

Bằng chứng không cần chứa chính bí mật mà workload sử dụng. Có thể lưu metadata về cấp phát, thay đổi phiên bản, thời hạn và kết quả kiểm soát theo phạm vi cần thiết. Lưu token hoặc khóa bí mật vào hồ sơ audit tạo thêm nơi có thể rò rỉ quyền truy cập.

## 5. Các thuộc tính chất lượng của governance evidence

### Nguồn gốc

Cần biết dữ liệu đến từ hệ thống nào, bản ghi nguồn nào, cơ chế thu thập nào và ai chịu trách nhiệm về nguồn đó.

Bản xuất CSV do một người gửi có thể hữu ích, nhưng nếu không biết phạm vi lọc, thời điểm xuất và quyền truy cập của người xuất, không nên mặc định nó là danh sách đầy đủ của toàn hệ thống.

### Tính chính xác

Định danh, phép đối sánh và diễn giải quyền phải đúng. Một bản ghi nguyên vẹn nhưng gắn nhầm hai tài khoản của hai người khác nhau vẫn là bằng chứng sai cho khẳng định đang xét.

Các bước chuẩn hóa dữ liệu nên giữ được liên hệ với dữ liệu nguồn, phiên bản quy tắc ánh xạ và các trường hợp chưa đối sánh được.

### Tính đầy đủ

Cần xác định được tập đối tượng đáng lẽ phải được đánh giá, nguồn nào đã thu thập thành công và nguồn nào còn thiếu.

Các lỗi dễ làm bằng chứng thiếu mà vẫn trông hợp lệ gồm:

- Connector mất quyền đọc một số nhóm hoặc tenant.
- Chỉ lấy trang đầu tiên của kết quả.
- Bộ lọc vô tình loại tài khoản bị vô hiệu hóa hoặc tài khoản không có owner.
- Hàng đợi sự kiện có khoảng trống chưa được xử lý.
- Chỉ thu thập quyền gán trực tiếp mà bỏ đường cấp qua nhóm.
- Loại các bản ghi lỗi đối sánh ra khỏi báo cáo mà không ghi nhận.

Một danh sách không có dòng lỗi chưa chứng minh dữ liệu đầy đủ. Cần bằng chứng riêng về quá trình thu thập và phạm vi quan sát.

### Tính kịp thời

Dữ liệu phải phù hợp với mốc thời gian của khẳng định. Snapshot từ tuần trước không đủ để khẳng định quyền đã bị thu hồi hôm nay.

Cần theo dõi thời gian xảy ra sự kiện, thời gian có hiệu lực, thời gian quan sát và thời gian nhận dữ liệu. Độ trễ giữa chúng có thể ảnh hưởng kết luận.

### Tính toàn vẹn và khả năng truy xuất

Bằng chứng cần được bảo vệ khỏi thay đổi không có dấu vết, đồng thời vẫn đọc được, giải thích được và liên kết được khi cần.

Một kho lưu trữ giữ nguyên file nhưng mất công cụ giải mã, mất khóa giải mã hoặc mất định nghĩa trường dữ liệu vẫn không đáp ứng tốt nhu cầu truy xuất bằng chứng.

### Tính liên quan và giới hạn

Dữ liệu chỉ có giá trị trong quan hệ với câu hỏi cần chứng minh. Một log đăng nhập thành công không trực tiếp chứng minh việc cấp vai trò đã được phê duyệt.

Kết luận phải giữ giới hạn của nguồn. Nếu chỉ quan sát được trạng thái cấu hình, hãy mô tả là trạng thái cấu hình; không mở rộng thành khẳng định về mọi yêu cầu truy cập thực tế.

## 6. Thời gian, phiên bản và thay đổi đồng thời

Một chuỗi bằng chứng có thể nhìn sai thứ tự nếu dùng chung một trường thời gian cho mọi sự kiện.

| Mốc thời gian | Ý nghĩa |
|---|---|
| Event time | Khi sự kiện được hệ thống nguồn ghi nhận là xảy ra |
| Effective time | Khi thay đổi được yêu cầu bắt đầu có hiệu lực |
| Decision time | Khi quyết định được đưa ra |
| Execution time | Khi thao tác được thực hiện hoặc hệ thống đích báo đã xử lý |
| Observation time | Khi trạng thái được đọc lại |
| Ingestion time | Khi dữ liệu được nhận vào hệ thống lưu bằng chứng |

Nên dùng biểu diễn thời gian có múi giờ rõ ràng. Đồng bộ đồng hồ và theo dõi sai lệch giúp giảm hiểu nhầm, nhưng thời gian gần nhau không tự tạo ra quan hệ nhân quả. ID liên kết, số phiên bản và thứ tự sự kiện tại nguồn vẫn cần thiết.

### Quyết định cũ có thể hết hiệu lực

Một yêu cầu cấp quyền được phê duyệt khi người dùng đang làm việc có thể không còn phù hợp sau sự kiện nghỉ việc. Hồ sơ phải cho biết quyết định nào bị thay thế và thao tác nào còn đang chờ.

Nếu job cũ đã có hiệu ứng tại đích, đánh dấu job là “superseded” không tự thu hồi quyền. Bằng chứng cần theo dõi cả hiệu ứng đã xảy ra và hành động đưa hệ thống về trạng thái mong muốn mới.

### Snapshot và dữ liệu biến động

Snapshot giữ lại thông tin được xem xét tại một thời điểm. Khi lập báo cáo trong một khoảng thời gian dài, cần kết hợp snapshot với thay đổi xảy ra trong kỳ hoặc nêu rõ báo cáo chỉ đánh giá tại một thời điểm.

Chỉ đọc trạng thái cuối kỳ không thể chứng minh quyền nhạy cảm chưa từng bị cấp ngoài quy trình trong kỳ. Ngược lại, sự tồn tại của một lần cấp quyền trước đó chưa chứng minh quyền vẫn còn ở thời điểm hiện tại.

## 7. Bảo vệ bằng chứng mà vẫn bảo vệ dữ liệu nhạy cảm

### Kiểm soát người đọc và người sửa

Hồ sơ governance có thể tiết lộ cơ cấu tổ chức, tài khoản quản trị, quyền đối với dữ liệu nhạy cảm và lịch sử nhân sự.

Cần phân quyền xem, tạo, xuất và quản lý bằng chứng. Nếu một chủ thể có thể tự cấp quyền, tự sửa log và tự xác nhận báo cáo mà không có kiểm soát khác, độ tin cậy của bằng chứng bị suy giảm.

Biện pháp phù hợp có thể gồm tách vai trò quản trị kho bằng chứng khỏi người vận hành quyền, ghi audit cho thao tác quản trị và chuyển log sang nguồn lưu trữ có quyền hạn riêng.

### Lưu lịch sử thay vì sửa âm thầm

Khi phát hiện dữ liệu sai, không nên xóa dấu vết rồi thay bằng một bản ghi có vẻ đúng từ đầu.

Có thể tạo bản đính chính tham chiếu bản gốc, ghi lý do, người thực hiện, thời điểm và ảnh hưởng đến kết luận. Bản báo cáo sau cần cho biết nó sử dụng phiên bản bằng chứng nào.

Lưu theo kiểu chỉ bổ sung, lưu phiên bản hoặc dùng khả năng bảo vệ sửa/xóa của kho lưu trữ có thể giúp kiểm soát thay đổi. Cần chọn theo yêu cầu và rủi ro thực tế, không mặc định một công nghệ tự bảo đảm mọi thuộc tính bằng chứng.

### Hash và chữ ký chứng minh điều gì?

Hash có thể giúp phát hiện nội dung khác với bản đối chiếu đáng tin cậy. Tuy nhiên:

- Hash không chứng minh dữ liệu ban đầu là đúng.
- Hash không tự xác định ai tạo dữ liệu.
- Nếu kẻ sửa có thể thay cả file và hash cùng chỗ, kiểm tra đối chiếu có thể không phát hiện được.
- Hash của file sau khi che dữ liệu sẽ khác hash của file gốc.

Chữ ký số có thể bổ sung thông tin về chủ thể ký và việc thay đổi nội dung đã ký, trong phạm vi bảo đảm của cơ chế ký và quản lý khóa. Nó không tự chứng minh một quyền đã được thu hồi đúng người.

Nếu dùng hash hoặc chữ ký, cần xác định chính xác dữ liệu được bảo vệ, nguồn tin cậy của thông tin đối chiếu, quyền quản lý khóa và cách xác minh về sau.

### Giảm thiểu và lưu giữ dữ liệu

Chỉ lưu dữ liệu cần cho mục đích chứng minh. Mật khẩu, token phiên, refresh token và khóa bí mật không nên xuất hiện trong payload log hoặc ảnh chụp màn hình bằng chứng.

Nếu cần che dữ liệu khi chia sẻ, giữ liên kết rõ giữa bản gốc được bảo vệ và bản đã che. Không mô tả bản đã che là nguyên byte bản gốc.

Thời hạn lưu giữ, sao lưu và xóa cần phù hợp với chính sách áp dụng cho tổ chức và loại dữ liệu. Không có một số ngày chung tự động phù hợp cho mọi bằng chứng IAM.

## 8. Bằng chứng cho các kiểm soát IAM thường gặp

| Khẳng định cần đánh giá | Bằng chứng liên quan | Giới hạn cần lưu ý |
|---|---|---|
| Cấp quyền có phê duyệt | Yêu cầu, chính sách, người phê duyệt, thời điểm, liên kết đến thao tác cấp | Phải đối chiếu cả những lần cấp không có yêu cầu trong nguồn quản lý |
| Quyền vẫn phù hợp công việc | Snapshot rà soát, ngữ cảnh nghiệp vụ, reviewer, quyết định, ngoại lệ | Một lần chứng nhận không bảo đảm nhu cầu không thay đổi sau đó |
| Quyết định thu hồi đã thực thi | Quyết định, thao tác thu hồi, readback, các đường cấp liên quan | Xóa một đường cấp chưa chứng minh mất toàn bộ quyền có hiệu lực |
| Không còn xung đột nhiệm vụ trong phạm vi | Quy tắc xung đột, dữ liệu quyền hợp nhất, kết quả đánh giá, ngoại lệ | Chất lượng phụ thuộc đối sánh danh tính và độ bao phủ quyền |
| Tài khoản nghỉ việc được xử lý | Sự kiện có hiệu lực, liên kết tài khoản, hành động vô hiệu hóa/thu hồi và xác minh | Khóa SSO không tự chứng minh mọi phiên hoặc đăng nhập riêng đã dừng |
| Đặc quyền tạm thời đã hết hiệu lực | Phê duyệt, thời hạn, bản ghi kích hoạt, kết quả hết hạn và xác minh | Chỉ có ngày hết hạn trên yêu cầu chưa chứng minh đích đã thu hồi |
| Chính sách MFA được thực thi cho phạm vi xác định | Chính sách, đối tượng áp dụng, bằng chứng luồng xác thực liên quan | Đăng ký một phương thức MFA không tự chứng minh mọi lần truy cập đều bị yêu cầu MFA |
| Danh tính workload có chủ sở hữu hợp lệ | Liên kết owner, mục đích, quyền, thời hạn và xác nhận vòng đời | Tên người trong trường owner chưa đủ nếu người đó đã nghỉ hoặc không còn chịu trách nhiệm |

Bảng này giúp tránh suy luận vượt bằng chứng. Ví dụ, “đã bật cấu hình MFA” và “yêu cầu cụ thể đã thỏa chính sách MFA” là hai khẳng định cần những dữ liệu bổ sung khác nhau.

Đối với quyền hình thành qua RBAC hoặc ABAC, cần lưu được phiên bản vai trò, chính sách và thuộc tính liên quan ở mức cần thiết. Chỉ ghi tên vai trò hiện tại có thể không tái dựng được quyền ở thời điểm lịch sử.

## 9. Ví dụ: chứng minh thu hồi quyền phê duyệt

Tổ chức yêu cầu thu hồi quyền phê duyệt thanh toán của An sau khi chuyển bộ phận. An có cùng quyền qua một gán trực tiếp và một nhóm dự án.

Các thời điểm dưới đây là thời gian UTC minh họa.

| Thời điểm | Bản ghi hoặc quan sát | Điều có thể kết luận |
|---|---|---|
| 09:00 | Nhận sự kiện chuyển bộ phận, hiệu lực 09:00 | Có căn cứ thay đổi nhu cầu quyền từ mốc hiệu lực |
| 09:02 | Quyết định thu hồi, liên kết chính sách và người có thẩm quyền | Ý định thu hồi đã được xác lập |
| 09:04 | Connector báo xóa gán trực tiếp thành công | Có bằng chứng về kết quả mà connector nhận được |
| 09:05 | Readback không còn gán trực tiếp | Gán trực tiếp không hiện diện trong nguồn và phạm vi đã đọc |
| 09:06 | Lệnh bỏ nhóm dự án bị timeout | Chưa biết chắc thao tác nhóm đã có hiệu lực hay chưa |
| 09:08 | Đọc lại thấy An vẫn thuộc nhóm dự án | Đường cấp qua nhóm còn tồn tại |
| 09:12 | Sau xử lý, readback xác nhận không còn hai đường cấp trong phạm vi đã thu thập | Đạt hậu điều kiện về các quan hệ quyền đã xác định |
| 09:15 | Kiểm tra cơ chế áp dụng quyền và trạng thái truy cập liên quan theo chính sách ứng dụng | Bổ sung bằng chứng về mức hiệu lực thực tế có thể kiểm tra |

Nếu báo cáo được tạo lúc 09:05 và chỉ lấy job xóa gán trực tiếp, kết luận “đã thu hồi quyền phê duyệt” sẽ quá rộng.

Một kết luận phù hợp ở 09:08 là:

> Gán trực tiếp đã được xác minh là không còn. Đường cấp qua nhóm dự án vẫn tồn tại; yêu cầu thu hồi chưa hoàn tất, hành động khắc phục đang được theo dõi.

Tại 09:12, kết luận vẫn cần giữ phạm vi: đã xác minh các đường cấp được xác định trong ứng dụng. Nếu còn phiên hoặc cơ chế quyền được lưu đệm chưa được đánh giá, không nên khẳng định mọi truy cập đã chấm dứt tức thì.

Bằng chứng tốt không chỉ ghi kết quả cuối cùng. Nó còn cho thấy khoảng thời gian tồn đọng, lý do, hành động và trách nhiệm xử lý.

## 10. Chuẩn bị một gói bằng chứng có thể kiểm tra

Một gói bằng chứng không nhất thiết là một file lớn. Nó có thể là tập hồ sơ có liên kết, gồm phần mô tả và các hiện vật nguồn được bảo vệ.

Cấu trúc khái niệm:

```text
Gói bằng chứng
├── Phạm vi, thời gian và các khẳng định được đánh giá
├── Danh mục nguồn và kết quả thu thập
├── Danh sách đối tượng, định danh và quy tắc đối sánh
├── Chính sách, quyết định và thẩm quyền
├── Thao tác thực thi cùng các lần thử
├── Readback, đối soát và kết quả xác minh
├── Ngoại lệ, thiếu dữ liệu và việc khắc phục còn mở
└── Manifest hiện vật, phiên bản và thông tin kiểm tra toàn vẹn
```

Đây là cách tổ chức thông tin minh họa; không yêu cầu tạo các file hay thư mục có tên cố định.

### Nội dung manifest

Manifest có thể ghi định danh hiện vật, nguồn, thời gian thu thập, định dạng, phiên bản, mức phân loại và vị trí lưu. Nếu dùng hash, cần ghi thuật toán cùng giá trị đối chiếu và bảo vệ manifest phù hợp.

Một hiện vật đã chuyển đổi hoặc che dữ liệu cần được nhận diện là bản dẫn xuất, liên kết với bản gốc và nêu phép biến đổi. Điều này giúp người kiểm tra hiểu vì sao số dòng hoặc nội dung có thể khác.

### Kiểm tra khả năng tái dựng

Một người được cấp quyền kiểm tra nên có thể:

1. Chọn một quyết định cụ thể.
2. Tìm đúng chủ thể, tài khoản, quyền và phạm vi.
3. Xem căn cứ cùng phiên bản chính sách.
4. Xác định người hoặc cơ chế quyết định có thẩm quyền.
5. Theo liên kết đến hành động thực thi.
6. Xem kết quả đọc lại và giới hạn của kết luận.
7. Tìm các ngoại lệ hoặc việc khắc phục còn liên quan.

Nếu phải dựa vào trí nhớ của một quản trị viên để giải thích toàn bộ chuỗi, hồ sơ chưa đủ tự mô tả. Ngược lại, đóng gói quá nhiều dữ liệu không liên quan có thể làm khó kiểm tra và tăng rủi ro lộ thông tin.

### Mẫu và toàn bộ tập đối tượng

Một số hoạt động đánh giá dùng lấy mẫu để kiểm tra sâu. Kết quả trên mẫu cần nêu cách chọn mẫu, tập gốc và giới hạn suy luận.

Không dùng vài trường hợp thành công để khẳng định mọi quyền trong toàn tổ chức đều phù hợp. Cũng không gọi một mẫu là toàn bộ dữ liệu chỉ vì mẫu chứa tất cả các trường hợp mà công cụ đang nhìn thấy.

## 11. Xử lý khi bằng chứng thiếu, mâu thuẫn hoặc bị sửa

Không phải mọi mục đều có thể kết luận đúng hoặc sai ngay. Cần ít nhất phân biệt **đã xác minh**, **không đạt** và **chưa đủ bằng chứng**.

| Tình huống | Cách xử lý có trách nhiệm |
|---|---|
| Thiếu dữ liệu từ một hệ thống | Ghi rõ phần thiếu, chủ sở hữu, ảnh hưởng và hành động thu thập tiếp |
| Log báo thành công nhưng readback không khớp | Giữ cả hai nguồn, điều tra độ trễ, sai đối tượng hoặc lỗi thực thi |
| Thời gian các nguồn không nhất quán | Kiểm tra múi giờ, sai lệch đồng hồ và thời gian nhận dữ liệu |
| Đối sánh danh tính mơ hồ | Chưa gắn kết luận với một người cụ thể; chuyển điều tra liên kết |
| Bằng chứng bị đính chính | Giữ lịch sử, lý do và đánh giá lại kết luận bị ảnh hưởng |
| Phát hiện sửa đổi không được phép | Bảo vệ dữ liệu còn lại, điều tra và đánh giá lại độ tin cậy theo quy trình sự cố |

### Không có log không đồng nghĩa không có hành động

Một hành động không xuất hiện trong log có thể do chưa từng xảy ra, nhưng cũng có thể do nguồn không thu thập loại sự kiện đó, log đã hết thời gian lưu, lỗi truyền hoặc bộ lọc sai.

Muốn dùng sự vắng mặt của bản ghi để hỗ trợ một kết luận, phải hiểu khả năng ghi nhận và độ bao phủ của nguồn trong khoảng thời gian liên quan. Với nhiều hệ thống phân tán, cần nêu giới hạn thay vì coi sự vắng mặt là bằng chứng tuyệt đối.

### Ví dụ về độ bao phủ

Giả sử tập cần đánh giá có 100 tài khoản, được xác định từ một danh mục có thẩm quyền. Dữ liệu quyền đầy đủ được thu thập cho 98 tài khoản, còn 2 tài khoản không đọc được do lỗi connector.

Không nên báo “100% tài khoản đạt” vì cả 98 tài khoản quan sát được đều đạt. Báo cáo cần thể hiện 98 tài khoản đã đánh giá và 2 tài khoản chưa đủ bằng chứng, cùng ảnh hưởng của chúng đến kết luận.

Nếu bản thân tập gốc cũng chưa được xác định đáng tin cậy, phải ghi thêm giới hạn đó. Con số 100 chỉ có ý nghĩa khi biết nó đại diện cho tập nào và được xác định bằng cách nào.

## 12. Vận hành bằng chứng như một phần của IAM

Bằng chứng nên được sinh và liên kết trong quy trình, thay vì chỉ tập hợp thủ công khi có đợt kiểm tra.

### Phân định trách nhiệm

- Chủ kiểm soát xác định khẳng định, phạm vi và điều kiện đạt.
- Chủ nguồn dữ liệu chịu trách nhiệm về ý nghĩa, khả năng thu thập và giới hạn của nguồn.
- Đội IAM liên kết vòng đời, quyết định, quyền và thực thi.
- Người phê duyệt chịu trách nhiệm về quyết định trong phạm vi thẩm quyền.
- Chủ ứng dụng hỗ trợ xác minh quyền và khả năng truy cập tại đích.
- Đơn vị quản lý kho bằng chứng bảo vệ lưu trữ, truy xuất và lịch sử quản trị.
- Người đánh giá kiểm tra bằng chứng và nêu kết luận trong phạm vi quan sát.

Một tổ chức có thể gộp hoặc tách các vai trò này, nhưng trách nhiệm và quyền sửa dữ liệu cần rõ.

### Chỉ số hữu ích

Nên theo dõi độ bao phủ nguồn, độ trễ thu thập, tỷ lệ đối sánh thành công, số chuỗi bằng chứng thiếu mắt xích, số hành động chưa có readback và thời gian tồn đọng của các mục chưa xác minh.

Số lượng log thu thập được hoặc dung lượng kho không phản ánh trực tiếp hiệu quả quản trị. Một triệu bản ghi không liên kết đúng đối tượng có thể ít giá trị hơn một chuỗi bằng chứng đầy đủ cho một quyền nhạy cảm.

Cần phân biệt các tỷ lệ theo giai đoạn: đã phê duyệt, đã thực thi, đã xác minh và còn ngoại lệ. Mẫu số cùng mốc báo cáo phải rõ để tránh che những mục khó xử lý.

### Kiểm tra định kỳ khả năng sử dụng

Định kỳ thử truy xuất một số hồ sơ, kiểm tra liên kết còn hoạt động, hiện vật còn đọc được và quy trình bảo vệ toàn vẹn còn khả dụng. Việc sao lưu thành công chưa tự chứng minh một hồ sơ lịch sử có thể được tái dựng đầy đủ.

Khi thay connector, định nghĩa vai trò hoặc nền tảng lưu trữ, cần đánh giá ảnh hưởng đến bằng chứng lịch sử. Không nên để tên quyền mới thay thế âm thầm ý nghĩa của quyền trong báo cáo cũ.

## 13. Những sai lầm cần tránh

**Coi ảnh chụp màn hình là bằng chứng đầy đủ:** ảnh có thể hữu ích nhưng thường thiếu nguồn, thời gian, bộ lọc, phạm vi và dữ liệu có cấu trúc để kiểm tra.

**Đồng nhất phê duyệt với thực thi:** một quyết định hợp lệ vẫn có thể gặp lỗi cấp hoặc thu hồi quyền. Cần theo dõi chuỗi đến kết quả đã xác minh.

**Đồng nhất hash với sự thật:** hash giúp kiểm tra thay đổi so với đối chiếu đáng tin cậy, không sửa được dữ liệu gốc sai hoặc thiếu.

**Chỉ giữ trạng thái hiện tại:** không tái dựng được quyền, chính sách và thẩm quyền ở thời điểm quyết định lịch sử.

**Dùng tên hiển thị làm khóa duy nhất:** dễ nhầm người, nhóm hoặc quyền khi dữ liệu đổi tên hay tái sử dụng.

**Loại các bản ghi thiếu dữ liệu để làm báo cáo đẹp:** làm sai độ bao phủ và mức tin cậy của kết luận. Cần giữ trạng thái chưa đủ bằng chứng.

**Thu thập bí mật để “đủ thông tin”:** tạo thêm rủi ro truy cập. Cần lưu metadata và kết quả kiểm tra cần thiết thay vì chính bí mật.

**Để một người có thể cấp quyền và sửa sạch bằng chứng:** làm suy giảm khả năng phát hiện sai phạm. Cần kiểm soát quyền quản trị và lịch sử thay đổi.

**Kết luận rộng hơn phạm vi quan sát:** xóa một nhóm không tự chứng minh mọi quyền hoặc mọi phiên đều đã hết hiệu lực.

Governance evidence giúp biến một tuyên bố về quản trị quyền thành một kết luận có thể kiểm tra. Giá trị nằm ở mối liên kết giữa căn cứ, quyết định, hành động và trạng thái đã xác minh, cùng sự minh bạch về những điều còn chưa biết.
