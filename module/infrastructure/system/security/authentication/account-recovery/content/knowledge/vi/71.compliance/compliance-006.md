# Regional recovery constraints — Ràng buộc khôi phục tài khoản theo khu vực

## 1. Vì sao recovery cần biết bối cảnh khu vực?

Một người dùng đăng ký tài khoản tại Việt Nam, dùng số điện thoại Singapore, đi công tác ở châu Âu và gửi yêu cầu khôi phục từ mạng của khách sạn. Dữ liệu tài khoản nằm ở một vùng cloud; nhân viên hỗ trợ lại làm việc tại vùng khác. Nếu hệ thống lấy quốc gia của địa chỉ IP làm căn cứ duy nhất, nó có thể chọn sai quy trình, gửi dữ liệu sai nơi hoặc cho phép đối phương chủ động đổi policy bằng VPN.

**Regional recovery constraints** là tập ràng buộc có liên quan đến khu vực khi khôi phục tài khoản: quy định có áp dụng, cam kết hợp đồng, nơi dữ liệu được xử lý, khả năng sử dụng kênh xác minh và điều kiện vận hành địa phương. Các ràng buộc này tác động tới việc chọn phương thức recovery và cách thực hiện, nhưng không tự chứng minh danh tính của người yêu cầu.

Trong phạm vi `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, cần xử lý việc mất mật khẩu, MFA, passkey hoặc thiết bị xác thực mà vẫn kiểm soát nguy cơ chiếm đoạt tài khoản. Khu vực là một phần ngữ cảnh quyết định; nó không phải lý do để tự giảm mức xác minh khi một kênh gửi mã gặp khó khăn.

Ví dụ, SMS không tới được người đang roaming không có nghĩa hệ thống được phép bỏ MFA. Hệ thống phải tìm phương án đã được phê duyệt với mức bảo vệ phù hợp, chuyển sang xử lý có kiểm soát hoặc tạm dừng thao tác chưa đủ điều kiện.

Bài học tập trung vào cách mô hình hóa và thực thi ràng buộc. Các ví dụ pháp lý được đối chiếu ngày 24/11/2026 để minh họa phương pháp; không phải danh sách đầy đủ nghĩa vụ cho mọi doanh nghiệp, ngành nghề hoặc quốc gia.

## 2. Không gộp mọi khái niệm thành một trường `region`

| Thuộc tính | Nó mô tả điều gì? | Không thể tự suy ra điều gì? |
| --- | --- | --- |
| Vị trí truy cập hiện tại | Nơi mạng hoặc thiết bị dường như đang hoạt động | Danh tính, quốc tịch hay toàn bộ luật áp dụng |
| Nơi cư trú đã khai hoặc xác minh | Một thông tin hồ sơ có nguồn gốc và thời điểm cập nhật | Nơi xử lý dữ liệu hoặc quyền dùng một kênh recovery |
| Pháp nhân cung cấp dịch vụ | Chủ thể cung cấp hoặc ký hợp đồng dịch vụ | Mọi bên xử lý dữ liệu đều ở cùng nơi |
| Phạm vi pháp lý đã được đánh giá | Các nghĩa vụ được xác định cho hoạt động xử lý cụ thể | Có thể thay bằng quốc gia lấy từ IP |
| Vùng lưu trữ và xử lý được cho phép | Những vị trí được duyệt cho từng loại dữ liệu và tác vụ | Mọi truy cập từ xa hoặc nhà thầu phụ đều đã được duyệt |
| Quốc gia của số điện thoại | Thông tin định tuyến và bối cảnh liên lạc | Người dùng đang ở nước đó hoặc có quyền đối với tài khoản |
| Ngôn ngữ và múi giờ giao diện | Cách trình bày thông tin cho người dùng | Policy bảo đảm danh tính được phép thay đổi |
| Vị trí của nhân viên hỗ trợ | Một yếu tố của luồng truy cập và xử lý dữ liệu | Quyền xem chứng cứ hoặc phê duyệt recovery |

Một mô hình dữ liệu tốt giữ những thuộc tính này riêng biệt và ghi nguồn của chúng. Chẳng hạn, `requestCountry` từ tín hiệu mạng khác với `contractingEntity` từ hồ sơ dịch vụ. Nếu không phân biệt, một cập nhật phục vụ giao diện có thể vô tình thay đổi quyền chọn policy.

Không nên thu thập thêm quốc tịch, giấy tờ hoặc vị trí chính xác chỉ vì muốn “xác định region tốt hơn”. Chỉ lấy dữ liệu cần thiết cho quyết định đã xác định mục đích; khi thiếu thông tin, dùng trạng thái chưa rõ và một quy trình giải quyết phù hợp.

## 3. Phân loại ràng buộc trước khi thiết kế phương thức khôi phục

| Nhóm ràng buộc | Câu hỏi cần trả lời | Ảnh hưởng lên recovery |
| --- | --- | --- |
| Pháp lý và ngành nghề | Quy định nào thực sự áp dụng cho hoạt động này? | Điều kiện xử lý dữ liệu, xác minh, lưu giữ hoặc nghĩa vụ chuyên ngành |
| Hợp đồng và tenant | Khách hàng đã được cam kết điều gì? | Vùng dữ liệu, nhà cung cấp, quyền truy cập hỗ trợ |
| An toàn tài khoản | Bằng chứng nào đủ để cấp quyền cụ thể? | Cách thay mật khẩu, MFA, passkey và xử lý session |
| Khả năng kênh liên lạc | Kênh có hoạt động với tài khoản và điểm đến này không? | Chọn phương án đã duyệt, xử lý chậm hoặc không gửi được |
| Vận hành địa phương | Có nhân sự, ngôn ngữ và thời gian hỗ trợ phù hợp không? | Cách xếp hàng, thông báo chờ và chuyển cấp |
| Bảo vệ dữ liệu | Dữ liệu nào đi qua bên nào, ở đâu? | Định tuyến provider, phân quyền evidence, retention và telemetry |

Những nhóm này cần được xét cùng nhau. Một phương thức xác minh có thể mạnh về kỹ thuật nhưng không được phép dùng với một loại dữ liệu ở một tuyến xử lý cụ thể. Ngược lại, một provider được phép xử lý dữ liệu chưa chắc cung cấp đủ bằng chứng cho việc thay MFA.

Không gom mọi kết quả vào một nhãn `countryAllowed=true`. Quyết định cần chỉ ra hành động nào được phép, dùng phương thức nào, qua provider nào, với giới hạn dữ liệu và quyền sau khôi phục ra sao.

## 4. Giữ nền bảo vệ chung, cho phép khác biệt có lý do

### 4.1. Những bất biến an toàn của thiết kế minh họa

Một sản phẩm có thể đặt ra các bất biến chung sau cho mọi deployment:

- Không cấp quyền thay credential khi chưa có bằng chứng được policy chấp nhận.
- Grant khôi phục được giới hạn theo tài khoản, tenant, mục đích và transaction.
- Quyền dùng một lần có cơ chế chống dùng lại, kể cả request đồng thời.
- Mất kênh gửi mã không tự mở một nhánh yếu hơn.
- Thay mật khẩu không mặc nhiên cho phép xóa MFA hoặc gắn passkey mới.
- Mọi thay đổi phải xử lý authenticator cũ và session theo policy của luồng.
- Quyết định có thể truy vết mà không ghi bí mật recovery vào log.

Đây là các quyết định thiết kế trong bài học, không phải lời khẳng định mọi luật đều có cùng nội dung. Khi áp dụng tiêu chuẩn kỹ thuật, tổ chức còn phải kiểm tra đúng yêu cầu và điều kiện của tiêu chuẩn đã chọn.

### 4.2. Những khác biệt cần cấu hình rõ

Khu vực có thể ảnh hưởng đến kênh được hỗ trợ, nhà cung cấp, loại chứng cứ phù hợp, mẫu thông báo, hàng đợi helpdesk hoặc tuyến lưu dữ liệu. Các khác biệt này phải có nguồn quyết định và kiểm thử; không giấu chúng trong những nhánh `if country == ...` rải rác trong code.

Ví dụ: hai tenant cùng dùng một mức xác minh nội bộ, nhưng tenant thứ nhất cho phép dịch vụ xác minh A còn tenant thứ hai chỉ cho phép dịch vụ B. Nếu dịch vụ B lỗi, không được tự gửi chứng cứ sang A chỉ vì A đang hoạt động.

Một thay đổi giao diện như chuyển sang tiếng Việt không được tự đổi phương thức xác minh. Thay đổi route cloud để giảm độ trễ cũng không được tự thay cơ chế thu hồi session.

## 5. Một số ví dụ pháp lý cần đọc đúng phạm vi

### 5.1. EU: phạm vi áp dụng và việc chuyển dữ liệu là hai câu hỏi

GDPR Điều 3 xác định phạm vi áp dụng theo những điều kiện cụ thể; quốc tịch hoặc IP không thay thế phép đánh giá này. Chương V, bắt đầu từ Điều 44, quy định việc chuyển dữ liệu tới nước thứ ba hoặc tổ chức quốc tế. Không diễn giải thành lệnh cấm chung mọi xử lý ngoài EU. Xem [GDPR trên EUR-Lex](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng).

Trong recovery, hãy xác định pháp nhân xử lý, bên nhận chứng cứ, mục đích và tuyến dữ liệu trước khi chọn provider. Kết quả đánh giá phải gắn với hoạt động cụ thể; không chỉ gắn nhãn “tài khoản châu Âu”.

EDPB Guidelines 05/2021, phiên bản 2.0, dùng ba tiêu chí tích lũy để nhận diện một hoạt động chuyển dữ liệu. Ví dụ 11 phân tích truy cập từ xa của một processor ở nước thứ ba vào dữ liệu tại EU. Không được suy mọi nhân viên truy cập khi đi nước ngoài đều thuộc cùng tình huống đó; ví dụ 8 phân biệt nhân viên là bộ phận của cùng controller. Xem [EDPB — Guidelines 05/2021](https://www.edpb.europa.eu/system/files/documents/2023-02/edpb_guidelines_05-2021_interplay_between_the_application_of_art3-chapter_v_of_the_gdpr_v2_en_0.pdf).

### 5.2. Việt Nam: dùng đúng bối cảnh văn bản đang có hiệu lực

Luật Bảo vệ dữ liệu cá nhân số 91/2025/QH15 và Nghị định 356/2025/NĐ-CP cùng có hiệu lực từ 01/01/2026, theo thông tin trên Cổng Thông tin điện tử Chính phủ. Một thiết kế được lập trong năm 2026 cần đối chiếu hệ thống văn bản áp dụng tại thời điểm triển khai, thay vì giữ nguyên một checklist cũ chưa rà soát. Xem [Luật 91/2025/QH15](https://chinhphu.vn/?docid=214590&pageid=27160) và [Nghị định 356/2025/NĐ-CP](https://chinhphu.vn/?docid=216387&pageid=27160).

Điều 3 của Luật đề cập phạm vi, mục đích và thời gian lưu trữ dữ liệu; Điều 20 quy định các trường hợp chuyển dữ liệu cá nhân xuyên biên giới cùng điều kiện liên quan. Không suy chỉ từ đó rằng mọi dữ liệu recovery phải ở một cloud region trong nước, hoặc rằng dùng cloud ngoài nước luôn được phép. Xem [toàn văn Luật trong Công báo](https://congbao.cdnchinhphu.vn/CongBaoCP/VanBan/2025/6/45578/57730-1-2025971-97291-2025-qh15.pdf).

Về triển khai, hồ sơ cần mô tả cả nơi nhận ảnh chứng cứ, nơi chạy dịch vụ phân tích, tuyến hỗ trợ và log. Việc đánh giá điều kiện, ngoại lệ hoặc nghĩa vụ hồ sơ phải dựa trên văn bản đầy đủ và bối cảnh thực tế.

### 5.3. Singapore: xem riêng bảo vệ, lưu giữ và chuyển dữ liệu

Hướng dẫn của PDPC về các khái niệm chính trong PDPA phân biệt nghĩa vụ bảo vệ, giới hạn lưu giữ và giới hạn chuyển dữ liệu. Phần chuyển dữ liệu đề cập yêu cầu bảo vệ có mức tương đương khi chuyển ra ngoài Singapore theo điều kiện áp dụng. Không đồng nhất điều này với một yêu cầu chung lưu mọi dữ liệu trong Singapore. Xem [PDPC — Advisory Guidelines on Key Concepts in the PDPA](https://www.pdpc.gov.sg/-/media/Files/PDPC/PDF-Files/Advisory-Guidelines/AG-on-Key-Concepts/Advisory-Guidelines-on-Key-Concepts-in-the-PDPA-17-May-2022.pdf).

Trong thiết kế recovery, cùng một provider có thể tạo nhiều tuyến: gửi mã, hỗ trợ vận hành, log và sao lưu. Đánh giá cần theo tuyến thực tế và bên chịu trách nhiệm, không chỉ theo địa chỉ của trụ sở provider.

### 5.4. Tiêu chuẩn kỹ thuật không thay thế đánh giá luật áp dụng

NIST SP 800-63B-4 là hướng dẫn về xác thực và quản lý authenticator; mục 4.2 xử lý account recovery. Một tổ chức có thể lựa chọn hoặc phải áp dụng nó trong bối cảnh cụ thể, nhưng không được gọi nó là luật bắt buộc cho mọi tài khoản trên toàn cầu. Xem [NIST SP 800-63B-4 — bản công bố chính thức](https://csrc.nist.gov/pubs/sp/800/63/B/4/final).

Ba ví dụ khu vực trên minh họa cách chuyển câu hỏi pháp lý thành đầu vào thiết kế. Chúng không bao phủ mọi yêu cầu chuyên ngành, luật khác có liên quan hoặc mọi lãnh thổ mà sản phẩm có thể phục vụ.

## 6. Xác định policy từ dữ liệu đáng tin cậy

Một policy resolver không nên nhận `country=XX` từ request rồi chọn ngay quy trình recovery. Request có thể cung cấp tín hiệu, nhưng quyết định cần tham chiếu dữ liệu có thẩm quyền từ backend và hồ sơ áp dụng đã được quản lý.

Quy trình minh họa:

```text
Nhận yêu cầu
    → tìm account và tenant theo cơ chế không tiết lộ tài khoản
    → lấy pháp nhân, policy và phạm vi xử lý từ nguồn backend
    → thêm tín hiệu rủi ro của request, không dùng nó thay metadata
    → xác định các ràng buộc cùng có hiệu lực
    → tìm phương án đáp ứng đồng thời các ràng buộc
    → đủ điều kiện: tạo recovery transaction có phạm vi
    → chưa đủ: chọn trạng thái chờ, chuyển cấp hoặc từ chối phù hợp
```

Không công khai cho người gọi biết account thuộc tenant nào hoặc có policy đặc biệt nào chỉ qua khác biệt thông báo. Những thông tin cần cho quyết định backend không nhất thiết cần trả về ở API public.

### 6.1. Thiếu hoặc mâu thuẫn dữ liệu

Ví dụ hồ sơ hợp đồng cho phép một tuyến xử lý, nhưng danh mục provider chưa có tuyến hợp lệ cho việc nhận chứng cứ ở thời điểm yêu cầu. Không tự chọn “global default” hoặc cho người dùng tự đổi quốc gia để bỏ qua xung đột.

Một kết quả có kiểm soát có thể là `POLICY_REVIEW_REQUIRED`, trong đó backend ghi mã lý do nội bộ và giao diện cung cấp hướng dẫn hỗ trợ phù hợp. Trạng thái này không chứng minh có gian lận; nó thể hiện hệ thống chưa đủ căn cứ để thực hiện một thao tác nhạy cảm.

Nếu người dùng thực sự chuyển nơi cư trú hoặc thay quan hệ dịch vụ, cập nhật hồ sơ phải qua quy trình riêng với nguồn dữ liệu và kiểm tra thích hợp. Không cho thay hồ sơ áp dụng pháp lý như một bước phụ chưa xác minh trong chính luồng recovery.

## 7. Kết hợp ràng buộc: không chỉ xếp thứ tự các quốc gia

Giả sử một transaction có ba ràng buộc nội bộ đã được xác nhận:

1. Loại tài khoản chỉ được thay MFA bằng các phương án đã duyệt trong bộ phương thức H.
2. Tenant chỉ cho phép nhóm provider P xử lý chứng cứ.
3. Dữ liệu loại D chỉ được đi qua các tuyến T đã được phê duyệt.

Phương án khả thi phải thỏa cả ba điều kiện, đồng thời đáp ứng khả năng kỹ thuật hiện tại. Một phương án trong H nhưng dùng provider ngoài P vẫn không phù hợp. Một provider trong P không được dùng nếu tuyến cụ thể không thuộc T.

Có thể mô tả bài toán bằng tập các phương án:

```text
FeasiblePlans = {
  plan | đáp ứng yêu cầu xác minh
         và đáp ứng policy tenant
         và có tuyến dữ liệu được cho phép
         và kênh có khả năng hoạt động
         và thỏa điều kiện vận hành
}
```

Mỗi phần tử là một **kế hoạch hoàn chỉnh**, không chỉ là tên một yếu tố. Nếu policy đòi tổ hợp hai bằng chứng, không lấy giao của các tập “tên yếu tố” rồi làm mất điều kiện kết hợp. Có email trong hai danh sách không có nghĩa một email riêng lẻ đã tạo ra kế hoạch hợp lệ.

“Chọn policy nghiêm nhất” cũng chưa phải thuật toán đủ rõ. Một policy cấm một loại thu thập, policy khác yêu cầu loại chứng cứ đó; hai điều kiện có thể không có phương án thỏa đồng thời. Khi đó phải giải quyết xung đột hoặc dừng thao tác, không tự ghép thành một policy mới chưa được đánh giá.

## 8. Gắn policy với transaction và kiểm tra lại khi thực thi

Khi tạo transaction, lưu phiên bản policy, phạm vi account/tenant, loại recovery, phương án được chọn và các tham chiếu tuyến xử lý. Các dữ liệu này giúp giải thích quyết định và ngăn một request sau tự đổi khu vực để nhận quyền khác.

Tuy nhiên, lưu snapshot không có nghĩa bỏ qua mọi thay đổi đến khi transaction hết hạn. Nếu một provider bị đình chỉ, một tuyến bị thu hồi quyền sử dụng hoặc xuất hiện rủi ro mới, bước thực thi phải kiểm tra điều kiện hiện hành có liên quan.

Một quy tắc thiết kế hợp lý là:

> Dùng snapshot để giữ nguyên ngữ cảnh và ranh giới quyền đã cấp; dùng kiểm tra hiện hành để không tiếp tục một kế hoạch đã bị thu hồi hoặc không còn đủ điều kiện. Nếu cần phương án mới, tạo hoặc phê duyệt lại kế hoạch theo quy trình có kiểm soát.

Các tình huống quan trọng:

| Thay đổi giữa luồng | Hành vi cần định nghĩa trong policy |
| --- | --- |
| Người dùng đổi ngôn ngữ | Đổi cách trình bày; không đổi quyền xác minh |
| IP chuyển sang nước khác | Đánh giá rủi ro; không tự thay phạm vi pháp lý của account |
| Provider bị thu hồi phê duyệt | Không gửi mới theo tuyến đó; xử lý transaction đang chờ theo kế hoạch sự cố |
| Policy mới yêu cầu xác minh bổ sung | Xác định transaction nào cần đánh giá lại; không âm thầm bỏ điều kiện mới |
| Người dùng xin dùng kênh khác | Chọn lại trong các phương án được phép và kiểm soát tính hợp lệ của proof cũ |
| Hệ thống chuyển vùng xử lý | Giữ ràng buộc dữ liệu và trạng thái chống replay; kiểm tra tuyến dự phòng đã duyệt |

## 9. Hồ sơ cấu hình khu vực minh họa

YAML sau là mô hình tài liệu thiết kế, không phải schema YAML bài học, không phải cấu hình đang được triển khai và không chứng nhận một tuyến đáp ứng luật. Các mã profile, method set và approval là mã nội bộ giả định.

```yaml
profileId: customer-recovery-profile-example
version: example-v3
state: draft

applicability:
  source: server-managed-service-profile
  accountClasses:
    - customer
  legalAssessmentRef: pending-real-assessment
  contractAssessmentRef: pending-real-assessment
  requestCountryIsAuthoritative: false
  localeChangesSecurityPolicy: false

security:
  baselineRef: recovery-baseline-example
  methodPlanSetRef: approved-combinations-example
  grantBindings:
    - accountId
    - tenantId
    - purpose
    - transactionId
    - policyVersion
  allowAutomaticWeakerFallback: false
  revalidateBeforeCredentialChange: true

dataHandling:
  processingRouteSetRef: approved-routes-example
  supportAccessSetRef: approved-support-access-example
  notificationProviderSetRef: approved-notification-example
  retentionPolicyRef: data-class-retention-example
  rawRecoverySecretsInTelemetry: false
  emergencyCrossRegionBypass: false

failureHandling:
  noFeasiblePlan: controlled-review-or-stop
  deliveryFailure: retry-or-replan-without-downgrade
  missingApplicability: policy-review-required
  providerApprovalRevoked: stop-new-processing-and-review

assessment:
  deploymentVerified: false
  sourceReviewCompleted: false
  endToEndTestsCompleted: false
```

`state: draft` và các giá trị đánh giá `false` cố ý cho biết ví dụ chưa được phê duyệt hoặc kiểm thử. Không thay chúng thành `true` chỉ vì đã tạo được tệp cấu hình.

Các tham chiếu trong cấu hình phải được giải quyết tới đối tượng có chủ sở hữu và phiên bản. Một chuỗi `approved-routes-example` không tự thực thi bất cứ giới hạn nào; backend, adapter, cơ sở hạ tầng và công cụ hỗ trợ phải cùng tôn trọng quyết định đó.

## 10. Vẽ tuyến dữ liệu cho toàn bộ recovery

Nơi đặt database chính chỉ là một phần của bức tranh. Recovery thường đi qua API gateway, bộ giới hạn, dịch vụ đánh giá rủi ro, provider gửi tin, công cụ hỗ trợ, kho chứng cứ và hệ thống quan sát. Mỗi thành phần có thể xử lý một loại dữ liệu khác nhau ở một địa điểm khác nhau.

| Tuyến | Dữ liệu cần kiểm kê | Câu hỏi ràng buộc khu vực |
| --- | --- | --- |
| Client → recovery backend | Định danh, tín hiệu request, proof được nhập | Backend nào nhận dữ liệu; edge có ghi request body không? |
| Backend → email/SMS provider | Địa chỉ liên hệ, mã hoặc liên kết theo thiết kế | Provider và tuyến xử lý nào được duyệt; log của họ chứa gì? |
| Client/backend → dịch vụ xác minh | Tài liệu, ảnh hoặc kết quả xác minh tùy phương án | Dữ liệu có được gửi vào đúng nơi và đúng mục đích không? |
| Backend → hệ thống chống lạm dụng | Tín hiệu mạng, thiết bị, account hoặc transaction | Dữ liệu có được giảm thiểu; tuyến phân tích có trong phạm vi đánh giá không? |
| Helpdesk → kho chứng cứ | Tài liệu, quyết định và lịch sử thao tác | Ai được xem, từ đâu, với quyền nào; có khả năng tải xuống không? |
| Dịch vụ → log, trace, cảnh báo | Mã transaction, mã lý do, lỗi và metadata | Có vô tình xuất bí mật hoặc dữ liệu nhạy cảm sang hệ thống quan sát khác vùng không? |
| Kho dữ liệu → backup hoặc DR | Bản sao và trạng thái khôi phục | Backup ở đâu; restore có đưa dữ liệu hoặc token cũ trở lại trạng thái sử dụng được không? |

Mỗi tuyến nên có bản ghi gồm loại dữ liệu, bên gửi, bên nhận, nơi xử lý, nơi lưu, quyền truy cập, mục đích, chính sách lưu giữ, căn cứ phê duyệt và điều kiện failover. Nếu một trường chưa rõ, đánh dấu chưa rõ và giao owner xác minh; không coi nó là “không có chuyển dữ liệu”.

### 10.1. Mã hóa không thay thế đánh giá tuyến

Mã hóa truyền tải và lưu trữ là các biện pháp bảo vệ quan trọng trong thiết kế. Chúng không tự giải quyết mọi câu hỏi về bên nhận, quyền truy cập, mục đích hoặc việc chuyển dữ liệu. Cần biết ai có khóa và ai có thể xem dữ liệu sau giải mã.

Tương tự, ký hiệu “data residency” trong hợp đồng cần được đọc đúng phạm vi. Một cam kết về nơi lưu có thể khác cam kết về mọi nơi xử lý, hỗ trợ từ xa hoặc sao lưu. Kiến trúc phải thực thi đúng điều đã cam kết, không tự mở rộng hoặc thu hẹp ý nghĩa của từ đó.

### 10.2. Log toàn cầu có thể phá vỡ ý định thiết kế

Giả sử ảnh chứng cứ được giữ trong một kho đã duyệt, nhưng lỗi HTTP từ adapter bị ghi kèm request body vào log tập trung. Vùng lưu kho chính vẫn đúng mà tuyến log đã phát sinh một bản sao ngoài dự kiến.

Cách xử lý là thiết kế schema log theo trường cho phép, che hoặc loại dữ liệu nhạy cảm trước khi xuất và kiểm tra cả proxy, APM, dead-letter queue lẫn công cụ hỗ trợ. Không chỉ thêm một dòng “không log OTP” vào tài liệu rồi giả định mọi lớp đã tuân thủ.

## 11. Kênh email, SMS và phương án thay thế

### 11.1. Khả năng gửi được không đồng nghĩa đủ quyền xác minh

Một SMS được provider chấp nhận không chứng minh người dùng đã nhận nó. Một delivery receipt cũng không tự chứng minh đúng chủ tài khoản đang kiểm soát thiết bị. Kết quả gửi là dữ liệu vận hành; quyền khôi phục phải đến từ bước kiểm tra proof và policy của phương án.

Trong từng thị trường, cần kiểm tra khả năng hoạt động thực tế của tuyến gửi: điểm đến được hỗ trợ, các điều kiện sử dụng sender, thời gian xử lý, giới hạn gửi và cách phản hồi lỗi. Các quy tắc telecom cụ thể phải được xác minh với nguồn có thẩm quyền và hợp đồng provider, không lấy ví dụ của thị trường khác để áp dụng mặc định.

Nếu cần thêm provider dự phòng, phê duyệt cả provider và tuyến trước khi sử dụng. “Cùng gửi SMS” không bảo đảm hai nhà cung cấp có cùng nơi xử lý, nhà thầu phụ, log hoặc điều kiện hợp đồng.

### 11.2. Resend và chuyển kênh vẫn thuộc cùng mô hình chống lạm dụng

Một người có thể thử gửi mã từ nhiều IP, thay endpoint hoặc chọn ngôn ngữ khác để né giới hạn. Các biến thể đó không nên tạo vô hạn transaction mới hoặc tách rời bộ đếm quan trọng của account và luồng.

Policy phải quy định rõ việc resend giữ hay thay proof, proof cũ còn hiệu lực không, số lần thử được tính thế nào và request nào có quyền chuyển kênh. Không giữ đồng thời nhiều mã hợp lệ ngoài ý định thiết kế chỉ để xử lý vấn đề chậm gửi.

Khi chuyển từ SMS sang một phương án khác, cần đánh giá lại kế hoạch hoàn chỉnh. Không thay SMS bằng email theo từng bước nếu tổ hợp bằng chứng sau thay đổi không còn đáp ứng yêu cầu của việc thay MFA.

### 11.3. Độ trễ không được âm thầm kéo dài bí mật

Nếu một mã tới muộn, hệ thống vẫn phải kiểm tra thời hạn tại backend. Giao diện không thể làm mã hợp lệ trở lại bằng cách đổi múi giờ, đặt lại đồng hồ đếm ngược hoặc cho thêm thời gian sau mỗi lần mở trang.

Thời hạn, số lần thử và cách resend là quyết định policy cần kiểm thử. Không có một giá trị TTL duy nhất đúng cho mọi loại recovery, kênh hoặc phạm vi tiêu chuẩn. Vấn đề độ trễ nên được xử lý bằng thiết kế phương án và vận hành kênh, thay vì tự gia hạn mọi mã đang tồn tại.

## 12. Chứng cứ danh tính và helpdesk theo khu vực

### 12.1. Loại giấy tờ khác nhau không có nghĩa hạ mục tiêu xác minh

Người dùng có thể không sở hữu loại giấy tờ phổ biến tại nơi nhóm phát triển làm việc. Tên, địa chỉ hoặc định dạng tài liệu cũng có thể khác. Một thiết kế chỉ chấp nhận một mẫu nội địa có thể khóa nhầm người dùng hợp lệ.

Giải pháp không phải chấp nhận mọi ảnh tài liệu. Cần xác định phương án chứng cứ được phép, khả năng thẩm định, mục tiêu xác minh và tuyến xử lý cho từng nhóm trường hợp. Nếu có phương án thay thế, nó phải được phê duyệt theo mục tiêu bảo vệ tương ứng.

Không mặc định thu hộ chiếu hoặc dữ liệu sinh trắc học từ mọi người yêu cầu recovery. Mỗi loại thu thập tạo thêm yêu cầu về tính cần thiết, bảo vệ dữ liệu, khả năng xử lý và lưu giữ. Khi chưa đủ điều kiện dùng loại chứng cứ đó, không chuyển trách nhiệm sang người dùng bằng một checkbox chung.

### 12.2. Phân quyền hỗ trợ phải xét hành động và phạm vi dữ liệu

Một nhân viên biết ngôn ngữ của người dùng chưa chắc có quyền xem tài liệu của tenant đó hoặc phê duyệt thay MFA. Có thể tách các khả năng: phiên dịch thông báo, kiểm tra tài liệu, đánh giá ngoại lệ và cấp quyền thực hiện thay đổi.

Một ma trận quyền nội bộ có thể kiểm tra đồng thời vai trò, tenant, loại hành động, tuyến hỗ trợ được duyệt và mức nhạy cảm của dữ liệu. Chỉ kiểm tra `role=SUPPORT` là quá ít cho một công cụ có thể chuyển quyền kiểm soát tài khoản.

| Thao tác helpdesk | Điều cần giới hạn trong thiết kế |
| --- | --- |
| Hướng dẫn người dùng | Chỉ hiển thị dữ liệu cần cho hỗ trợ; không đọc hoặc yêu cầu cung cấp OTP qua kênh tùy ý |
| Xem chứng cứ | Quyền theo vụ việc và loại dữ liệu; tuyến truy cập được duyệt |
| Phê duyệt ngoại lệ | Người có thẩm quyền; tiêu chí và lý do có thể kiểm tra |
| Khởi tạo bước recovery | Grant có purpose và phạm vi; không biến thành quyền đăng nhập thay người dùng |
| Xử lý ca khẩn cấp | Quy trình đã định nghĩa; giới hạn thời gian và hành động; hậu kiểm phù hợp |

Nhân viên không nên sao chép chứng cứ sang ứng dụng chat cá nhân để nhờ đồng nghiệp ở khu vực khác xem giúp. Nếu cần chuyển cấp, dùng công cụ và tuyến đã được phê duyệt, kèm mức dữ liệu tối thiểu cho vai trò nhận.

### 12.3. Giờ làm việc không đổi mức xác minh

Nếu hàng đợi phù hợp chỉ hoạt động trong giờ địa phương, người dùng cần được thông báo rõ khoảng chờ và cách theo dõi. Không tự giảm yêu cầu vì ca trực đêm thiếu nhân viên hoặc vì sắp vi phạm một SLA nội bộ.

Có thể cải thiện tính sẵn sàng bằng phương án dự phòng đã duyệt, tăng năng lực nhân sự hoặc giúp người dùng thiết lập phương tiện phục hồi trước khi có sự cố. Trải nghiệm tốt không đòi hỏi mở một đường tắt thiếu kiểm soát.

## 13. Ngôn ngữ, múi giờ và khả năng tiếp cận

### 13.1. Ngôn ngữ phục vụ hiểu đúng hành động

Thông báo cần giúp người dùng phân biệt đang đặt lại mật khẩu, thay MFA, đăng ký passkey hay xử lý nghi bị chiếm đoạt. Bản dịch không được đổi ý nghĩa quyền sẽ cấp hoặc bỏ mất cảnh báo quan trọng.

Các đường dẫn hỗ trợ phải phù hợp với sản phẩm và ngôn ngữ được công bố. Không tạo số điện thoại địa phương giả hoặc hứa hỗ trợ mọi múi giờ khi chưa có dịch vụ tương ứng. Khi một ngôn ngữ chưa được hỗ trợ, nêu lựa chọn thực tế trong quy trình đã duyệt.

### 13.2. Thời gian dùng cho bảo vệ phải được đánh giá tại server

Một mô hình triển khai có thể lưu các mốc như `issuedAt`, `expiresAt`, `approvedAt` và `consumedAt` dưới dạng thời điểm thống nhất, sau đó đổi sang múi giờ người dùng để hiển thị. Trong Java, `Instant` phù hợp để biểu diễn thời điểm tuyệt đối; cách định dạng giao diện là trách nhiệm riêng.

Ví dụ, thông báo có thể hiển thị cả ngày, giờ và múi giờ khi nói về lịch hẹn hỗ trợ. Nhưng quyết định grant hết hạn phải dựa trên thời gian backend đáng tin cậy và policy, không dựa trên chuỗi ngày giờ do client gửi.

Cần phân biệt thời hạn proof, thời gian chờ vận hành, cửa sổ đánh giá rủi ro và thời hạn lưu dữ liệu. Chúng có mục đích khác nhau. Gia hạn ticket hỗ trợ không tự gia hạn reset token; hết hạn token cũng không tự có nghĩa phải xóa ngay mọi dấu quyết định liên quan.

### 13.3. Khả năng tiếp cận cần được thiết kế thành phương án

Một người không dùng được cuộc gọi thoại hoặc không thực hiện được một bước giao diện vẫn cần có đường hỗ trợ phù hợp với mục tiêu xác minh. Không coi khó khăn tiếp cận là tín hiệu gian lận; cũng không tự bỏ bước bảo vệ để xử lý nhanh.

Đánh giá phương án thay thế từ trước và kiểm thử trải nghiệm ở các ngôn ngữ, kích thước màn hình, công cụ hỗ trợ và loại kênh có trong phạm vi sản phẩm. Nếu có nghĩa vụ pháp lý về khả năng tiếp cận tại một thị trường, ghi nguồn cụ thể trong hồ sơ áp dụng; không suy tất cả nơi có cùng yêu cầu.

## 14. Failover khu vực, trạng thái dùng một lần và session

### 14.1. Một kế hoạch DR cần bảo vệ cả dữ liệu lẫn quyền

Khi vùng xử lý chính gặp sự cố, hệ thống có thể chuyển request sang vùng dự phòng. Trước đó phải biết vùng dự phòng được phép xử lý loại dữ liệu nào, có đủ policy và trạng thái nào, có tuyến provider nào được duyệt và cách duy trì các bất biến an toàn.

Một cờ `allowFailover=true` không đủ. Cần mô tả cả tuyến dữ liệu, quyền vận hành và giao thức trạng thái trong tình huống lỗi.

| Rủi ro khi chuyển vùng | Hậu quả có thể xảy ra | Điều cần kiểm tra |
| --- | --- | --- |
| Bản sao trạng thái tiêu thụ bị chậm | Grant đã dùng được chấp nhận lại | Nơi có thẩm quyền quyết định và cách xử lý trạng thái chưa chắc chắn |
| Bộ đếm thử mã bị tách theo vùng | Đối phương có thêm lượt thử bằng cách đổi vùng | Phạm vi bộ đếm và chiến lược nhất quán phù hợp |
| Key hoặc policy khác phiên bản | Một vùng chấp nhận grant bị vùng khác từ chối | Phiên bản, quá trình luân chuyển và điều kiện từ chối an toàn |
| Provider dự phòng chưa được duyệt | Dữ liệu được gửi sang tuyến không nằm trong phạm vi cho phép | Catalog tuyến và kiểm tra trước lúc gửi |
| Restore backup cũ | Khôi phục credential hoặc grant đã bị thu hồi | Quy trình đối soát trạng thái thu hồi và xử lý dữ liệu phục hồi |
| Session store cập nhật chậm | Token cũ tiếp tục được một service chấp nhận | Cơ chế thu hồi, cache và cửa sổ hiệu lực đã cam kết |

Trong hệ thống phân tán, phải xác định rõ nơi có quyền tiêu thụ grant và cách đạt hành vi đúng khi có tranh chấp hoặc mất liên lạc. Không tuyên bố “đúng một lần toàn cầu” chỉ vì từng database có transaction cục bộ.

Nếu vùng dự phòng không thể biết chắc một grant đã bị tiêu thụ hay chưa, phương án an toàn cho thao tác nhạy cảm có thể là trì hoãn hoặc yêu cầu khởi động lại theo quy trình. Cần ghi quyết định đó trong thiết kế và thông báo cho người dùng phù hợp, không tự mở quyền vì muốn giữ tỉ lệ thành công.

### 14.2. Khôi phục credential không kết thúc việc bảo vệ tài khoản

Sau thay mật khẩu, MFA hoặc đăng ký passkey mới, phải xử lý quyền tiếp tục truy cập theo policy của luồng. Một ca mất thiết bị khác với một ca nghi đối phương đang có session; không dùng duy nhất vị trí địa lý để quyết định session nào đáng tin.

Liệt kê session web, mobile, refresh token, access token và phiên liên kết với IdP nếu có. Xác định nơi thực thi thu hồi và độ trễ chấp nhận được. Kiểm thử token cũ ở các service và vùng xử lý liên quan; việc một vùng đã xóa bản ghi không chứng minh mọi vùng đều ngừng chấp nhận nó.

Khi người dùng đi du lịch, có thể xuất hiện session hợp lệ ở nhiều nơi. Thu hồi cần theo policy và bằng chứng rủi ro, không chỉ xóa mọi session có quốc gia khác hồ sơ cư trú rồi coi đó là đã loại bỏ đối phương.

## 15. Thuật toán chọn kế hoạch: ví dụ ở mức thiết kế

Đoạn dưới là pseudocode mô tả thứ tự quyết định, không phải mã production hay cách tự động xác định luật áp dụng. `applicabilityProfile` đến từ hồ sơ backend đã được quản lý; nó không được tạo trực tiếp từ `Accept-Language`, IP hoặc trường quốc gia tùy ý của client.

```text
function planRecovery(account, tenant, requestedAction, requestSignals):
    profile = loadManagedApplicabilityProfile(account, tenant)
    if profile is missing or unresolved:
        return CONTROLLED_REVIEW

    baseline = loadSecurityPolicy(account.class, requestedAction)
    constraints = loadApplicableConstraints(profile, tenant)
    candidates = buildCompleteMethodPlans(baseline, account)

    feasible = []
    for plan in candidates:
        if not satisfiesProofRequirements(plan, baseline):
            continue
        if not satisfiesAllConstraints(plan, constraints):
            continue
        if not hasApprovedProcessingRoutes(plan, profile):
            continue
        if not hasRequiredOperationalCapabilities(plan):
            continue
        if not allowedByRiskDecision(plan, requestSignals):
            continue
        feasible.add(plan)

    if feasible is empty:
        return CONTROLLED_REVIEW_OR_STOP

    selected = selectPlanUsingApprovedPreference(feasible)
    return createScopedRecoveryTransaction(selected, profile, baseline)
```

Thứ tự ưu tiên giữa các phương án khả thi có thể xét chi phí, khả năng sử dụng hoặc trải nghiệm. Nó chỉ được chạy **sau** khi đã loại phương án không đáp ứng các điều kiện bắt buộc. Phương án rẻ hoặc gửi nhanh hơn không được nhận quyền vượt qua bộ lọc an toàn và tuyến dữ liệu.

Trước thao tác thay credential, cần kiểm tra lại grant, proof, trạng thái transaction, thời hạn, quyền hành động và các điều kiện bị thu hồi. Việc “đã chọn kế hoạch” chưa phải “đã được khôi phục tài khoản”.

Khi tiêu thụ quyền dùng một lần, thao tác thay đổi phải tuân thủ giao thức nhất quán của hệ thống. Nếu cần gọi dịch vụ ngoài transaction cục bộ, thiết kế phải có xử lý idempotency, retry và trạng thái trung gian tương ứng; không dùng một dòng pseudocode để che phần này.

Mã lý do chi tiết có thể được ghi nội bộ cho vận hành. API public chỉ nên trả thông tin người dùng cần biết để tiếp tục, tránh tiết lộ account, tenant, bằng chứng đã có hoặc policy đặc biệt cho một định danh chưa được xác minh.

## 16. Ma trận kiểm thử cho ràng buộc khu vực

Những bài kiểm thử dưới đây là kế hoạch minh họa; bài học không khẳng định chúng đã được triển khai hoặc đã chạy trên module. Khi áp dụng, dùng tài khoản thử nghiệm, tuyến mô phỏng hoặc môi trường đã được cho phép.

| Ca thử | Mục tiêu kiểm tra | Kết quả cần xác minh |
| --- | --- | --- |
| Đổi IP hoặc dùng VPN giữa luồng | Không lấy vị trí mạng thay hồ sơ áp dụng | Ranh giới quyền không tự đổi; tín hiệu rủi ro được xử lý đúng policy |
| Đổi ngôn ngữ hoặc múi giờ | Không dùng presentation để đổi security policy | Nội dung hiển thị đổi phù hợp; proof và grant giữ điều kiện hợp lệ |
| Gửi trường quốc gia tùy ý trong request | Chống sửa ngữ cảnh từ client | Backend không tin trường đó để mở phương thức recovery khác |
| Tài khoản thiếu applicability profile | Không chọn policy ngầm dễ hơn | Chuyển trạng thái kiểm soát, không cấp grant thay credential |
| SMS bị chặn hoặc gửi chậm | Không tự hạ mức xác minh | Retry hoặc chọn lại trong tập phương án hợp lệ; không bỏ MFA |
| Mã đến sau thời điểm hết hạn | Kiểm tra tại backend | Mã bị từ chối; UI không làm thay đổi thời hạn |
| Resend từ nhiều vùng | Không chia nhỏ giới hạn ngoài ý định | Bộ đếm và số proof hợp lệ đúng policy; không phát sinh quyền cộng dồn |
| Provider được duyệt nhưng tuyến chưa duyệt | Phân biệt tổ chức với tuyến xử lý | Chặn gửi dữ liệu qua tuyến thiếu điều kiện |
| Thu hồi phê duyệt provider giữa luồng | Kiểm tra điều kiện hiện hành | Không tiếp tục gửi mới theo phê duyệt cũ; transaction được xử lý rõ ràng |
| Helpdesk ở tuyến truy cập không được phép | Thực thi quyền dữ liệu ở backend | Không xem hoặc xuất chứng cứ chỉ nhờ có vai trò hỗ trợ |
| Request đồng thời ở hai vùng | Chống replay sau failover | Không có thêm tác động thay credential hoặc thêm quyền từ cùng grant |
| Restore backup cũ | Không hồi sinh quyền đã mất hiệu lực | Trạng thái thu hồi và hết hạn được đối soát trước phục vụ |
| Token cũ gọi service ở vùng khác | Hiệu lực thu hồi session | Hành vi phù hợp cửa sổ thu hồi và phạm vi đã công bố |
| Adapter trả lỗi có chứa payload | Ngăn rò qua telemetry | Log, trace và dead-letter queue không nhận dữ liệu bị cấm xuất |

### 16.1. Kiểm tra cả tác động và luồng dữ liệu

Với một ca chuyển provider bị chặn, không chỉ kiểm tra mã HTTP từ API. Cần xác nhận provider không nhận payload, không có bản sao trong hàng đợi và không có tác vụ nền tiếp tục gửi sau đó.

Với một ca replay, kiểm tra số lần chuyển trạng thái có hiệu lực, credential được tạo hoặc thay đổi và quyền truy cập sau thao tác. Hai response giống nhau có thể là idempotency; một response lỗi vẫn có thể che side effect nếu thiết kế sai.

Với quyền helpdesk, thử cả đường UI, API trực tiếp, đường tải file và công cụ xuất dữ liệu nếu có trong phạm vi. Ẩn nút không tạo thành ranh giới phân quyền.

### 16.2. Kiểm tra thay đổi policy và cấu hình triển khai

Mỗi kết quả test cần chỉ ra release, phiên bản policy, tập route và cấu hình provider liên quan. Nếu sau test có thay một trong các thành phần quyết định, phải đánh giá tác động tới bằng chứng cũ.

Có thể tự động kiểm tra profile tham chiếu route không tồn tại, thiếu owner hoặc chứa cấu hình fallback chưa được phép. Những kiểm tra cấu trúc này không chứng minh việc xử lý dữ liệu hợp pháp hoặc phương án đủ mức bảo đảm; chúng hỗ trợ phát hiện lỗi trước khi chạy test hành vi và đánh giá chuyên môn.

## 17. Tình huống tổng hợp: người dùng mất điện thoại khi đi công tác

Một người dùng có account do pháp nhân A phục vụ, thuộc tenant T. Họ đang ở nước khác, mất điện thoại chứa phương tiện xác thực thường dùng và còn một mã phục hồi đã thiết lập trước. SMS tới số đã đăng ký không tới được do vấn đề kênh. Tenant chỉ cho phép một tập tuyến xử lý chứng cứ và một nhóm hỗ trợ cụ thể.

Đây là tình huống giả định để phân tích. Không gán nghĩa vụ của một quốc gia cụ thể cho pháp nhân A hoặc tenant T.

### 17.1. Những lựa chọn dễ gây lỗi

- Dùng IP mới để chuyển account sang policy ở nơi người dùng đang đi công tác.
- Coi mã quốc gia số điện thoại là căn cứ đủ để chọn mọi quy tắc pháp lý.
- Cho nhập lại email mới rồi gửi toàn bộ quyền recovery tới địa chỉ đó mà chưa có kiểm tra tương ứng.
- Bỏ yêu cầu về MFA vì SMS không hoạt động.
- Cho helpdesk bất kỳ xem chứng cứ qua chat ngoài hệ thống.
- Chuyển payload sang provider toàn cầu chưa được duyệt để giảm thời gian chờ.
- Hoàn tất thay credential nhưng để grant cũ hoặc quyền tiếp tục truy cập ngoài ý định policy.

### 17.2. Cách xử lý có cấu trúc

1. Lấy account, tenant và hồ sơ áp dụng từ backend; xem vị trí request là tín hiệu rủi ro riêng.
2. Xác định chính xác người dùng mất những phương tiện nào và còn phương án đã thiết lập nào, theo luồng được phép.
3. Đối chiếu mã phục hồi cùng các điều kiện còn lại với những kế hoạch hoàn chỉnh được policy chấp nhận cho hành động cần thực hiện.
4. Nếu có kế hoạch khả thi, kiểm tra tuyến dữ liệu và khả năng vận hành trước khi thực hiện; không suy có một mã là đã đủ cho mọi loại account.
5. Nếu cần hỗ trợ, đưa vụ việc tới vai trò và tuyến truy cập phù hợp, chỉ cung cấp dữ liệu cần thiết.
6. Nếu chưa có kế hoạch đáp ứng, giữ trạng thái chờ hoặc dừng thao tác nhạy cảm; giải thích lựa chọn hỗ trợ thực tế mà không tiết lộ thông tin nội bộ quá mức.
7. Khi đủ điều kiện, cấp quyền giới hạn theo purpose, thay hoặc đăng ký phương tiện theo policy và xử lý phương tiện bị mất.
8. Tiêu thụ quyền một lần, xử lý session và gửi thông báo theo kế hoạch; ghi quyết định đã che dữ liệu để hỗ trợ kiểm tra sau đó.

Một trải nghiệm tốt giải thích rõ đang chờ gì, kênh hỗ trợ nào có sẵn và điều người dùng có thể làm tiếp. Nó không cần hứa “khôi phục ngay” khi hệ thống chưa có bằng chứng đủ để bảo vệ quyền sở hữu account.

## 18. Quản lý thay đổi pháp lý và thay đổi vận hành

Ràng buộc khu vực không đứng yên. Một văn bản có thể có ngày ban hành, ngày có hiệu lực và điều khoản chuyển tiếp khác nhau. Một provider có thể đổi nhà thầu phụ, nơi hỗ trợ hoặc tuyến gửi mà tên dịch vụ thương mại vẫn giữ nguyên.

Hồ sơ nguồn cần ghi tên, phiên bản hoặc mã văn bản, ngày đối chiếu, tình trạng áp dụng, điều kiện liên quan, phần diễn giải nội bộ và người xác nhận. Đừng lấy ngày tìm thấy một bài giới thiệu làm ngày quy định bắt đầu có hiệu lực.

| Thay đổi | Phần cần đánh giá lại |
| --- | --- |
| Văn bản hoặc điều khoản áp dụng thay đổi | Applicability profile, dữ liệu thu thập, tuyến xử lý và quy trình liên quan |
| Mở thị trường hoặc loại khách hàng mới | Pháp nhân phục vụ, hợp đồng, phương án chứng cứ, hỗ trợ và nhà cung cấp |
| Đổi SMS/email provider | Tuyến payload, log, subprocessor, điều kiện gửi và kế hoạch dự phòng |
| Thêm vùng cloud hoặc DR | Phạm vi dữ liệu, quyền truy cập, trạng thái token và cơ chế session |
| Thuê thêm nhóm helpdesk | Quyền dữ liệu, tuyến truy cập, đào tạo, phê duyệt và chuyển cấp |
| Thêm phương thức recovery | Mức bảo vệ, dữ liệu cần dùng, khả năng hoạt động theo thị trường và test âm |
| Thay retention hoặc telemetry | Phạm vi bản sao, cơ chế xóa và dữ liệu có thể ra ngoài tuyến dự kiến |

Các thay đổi cần đi qua đánh giá tác động và kiểm thử tương ứng. Cơ chế rollback cũng phải biết tuyến nào còn được phép dùng; không quay về một cấu hình đã bị thu hồi phê duyệt chỉ vì đó là bản chạy ổn định trước đây.

Khi nguồn hoặc diễn giải còn chưa rõ, kỹ sư cần mô tả cụ thể dữ liệu, hành động và tuyến dự kiến để người có trách nhiệm có thể đánh giá. Một câu hỏi “có tuân thủ không?” thiếu sơ đồ và bối cảnh thường không đủ để có quyết định hữu ích.

## 19. Câu hỏi tự kiểm tra

**Câu 1:** Người dùng chuyển IP từ Việt Nam sang Đức. Backend có nên tự đổi applicability profile sang một profile dành cho Đức không?

Không chỉ dựa vào thay đổi đó. Vị trí request là tín hiệu cho đánh giá rủi ro hoặc trải nghiệm; hồ sơ áp dụng cần dựa trên những điều kiện và nguồn có thẩm quyền đã xác định. Nếu có thay đổi thực sự trong quan hệ dịch vụ hoặc dữ liệu hồ sơ, xử lý qua quy trình cập nhật phù hợp.

**Câu 2:** Chứng cứ được lưu ở một region đã duyệt, nhưng đội hỗ trợ và log ở nơi khác. Đã đủ để kết luận tuyến xử lý đúng ràng buộc chưa?

Chưa. Phải kiểm kê cả truy cập, bên nhận, telemetry, hàng đợi và bản sao. Việc đánh giá pháp lý còn phụ thuộc chủ thể và điều kiện cụ thể; không chỉ phụ thuộc vị trí ổ đĩa chính.

**Câu 3:** Có thể tự chuyển từ SMS sang email khi roaming làm SMS không tới không?

Chỉ khi kế hoạch sau chuyển kênh đã được policy cho phép và vẫn đáp ứng đồng thời các điều kiện xác minh, tuyến dữ liệu và chống lạm dụng. Một sự cố gửi tin không tự tạo quyền hạ mức bảo vệ.

**Câu 4:** Một transaction lưu snapshot policy trước khi provider bị thu hồi phê duyệt. Có được tiếp tục gửi chứng cứ theo snapshot không?

Không nên coi snapshot là giấy phép bỏ qua việc thu hồi. Bước xử lý phải kiểm tra điều kiện hiện hành có liên quan và chuyển sang phương án được duyệt hoặc xử lý có kiểm soát. Snapshot vẫn cần để giải thích quyết định trước đó.

**Câu 5:** Dùng chung một mức xác minh cho mọi nơi có loại bỏ nhu cầu cấu hình khu vực không?

Không. Mức xác minh chung không giải quyết mọi khác biệt về tuyến dữ liệu, hợp đồng, provider, loại chứng cứ, ngôn ngữ, vận hành hoặc nghĩa vụ áp dụng. Những khác biệt cần được biểu diễn rõ mà vẫn giữ các bất biến an toàn.

**Câu 6:** Tại sao không chỉ lấy giao các phương thức được phép?

Vì yêu cầu có thể áp dụng cho tổ hợp chứng cứ và toàn bộ kế hoạch, không chỉ cho tên từng phương thức. Giao hai tập có chứa email không chứng minh một email đơn lẻ đủ cho việc thay MFA. Cần đánh giá các kế hoạch hoàn chỉnh và xử lý trường hợp không có kế hoạch thỏa tất cả ràng buộc.

## 20. Kiểm tra thiết kế trước khi đưa vào vận hành

Một thiết kế recovery có xử lý khu vực cần trả lời được những câu hỏi sau:

- Backend lấy phạm vi áp dụng từ đâu, và dữ liệu nào client không được tự sửa?
- Vị trí truy cập, vùng dữ liệu, pháp nhân, tenant và ngôn ngữ đã được phân biệt chưa?
- Mỗi phương án có đáp ứng yêu cầu xác minh cho đúng loại mất mật khẩu, MFA, passkey hoặc thiết bị không?
- Mọi tuyến provider, helpdesk, log, backup và DR đã được kiểm kê và phê duyệt đúng phạm vi chưa?
- Kênh chậm hoặc lỗi có dẫn tới hạ mức xác minh, kéo dài proof hoặc nhân số lượt thử không?
- Thay đổi policy giữa luồng có được kiểm tra lại trước khi thay credential không?
- Failover có giữ được ràng buộc dữ liệu, chống replay và hành vi thu hồi session không?
- Người dùng có hướng dẫn phù hợp về ngôn ngữ, thời gian chờ và khả năng tiếp cận không?
- Hồ sơ nguồn, quyết định triển khai và kết quả kiểm thử có phiên bản để rà soát khi thay đổi không?

Khu vực cần làm cho quyết định recovery chính xác hơn: đúng điều kiện áp dụng, đúng tuyến dữ liệu, đúng phương thức xác minh và đúng quyền sau khôi phục. Nó không nên trở thành một biến client có thể sửa để đi vòng qua bảo vệ tài khoản.


