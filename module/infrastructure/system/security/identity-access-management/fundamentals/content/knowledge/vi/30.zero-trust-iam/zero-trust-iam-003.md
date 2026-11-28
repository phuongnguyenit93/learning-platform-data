# Continuous verification

## 1. Vì sao một lần đăng nhập chưa đủ?

Một người dùng xác thực thành công lúc 08:00 không có nghĩa mọi yêu cầu của người đó đều hợp lệ trong suốt ngày làm việc. Sau thời điểm đăng nhập, tài khoản có thể bị vô hiệu hóa, vai trò có thể bị thu hồi, thiết bị có thể không còn đáp ứng chính sách hoặc tài nguyên có thể chuyển sang mức nhạy cảm cao hơn.

**Continuous verification**, hay xác minh liên tục, là cách duy trì quyết định truy cập dựa trên bằng chứng và chính sách còn phù hợp tại thời điểm sử dụng. Hệ thống kiểm tra quyền ở các điểm truy cập cần thiết và đánh giá lại khi có thay đổi liên quan, thay vì coi kết quả đăng nhập ban đầu là sự tin cậy vô thời hạn.

Trong IAM theo định hướng Zero Trust, mục tiêu không phải là bắt người dùng nhập mật khẩu hoặc MFA ở mọi lần bấm nút. Mục tiêu là không tiếp tục cấp quyền chỉ vì một chủ thể từng được chấp nhận trước đó.

Ví dụ, Lan đăng nhập từ thiết bị công ty để sử dụng ứng dụng quản lý tài liệu. Đến 09:00, hệ thống nhận một sự kiện đáng tin cậy cho biết tài khoản Lan đã bị khóa. Nếu ứng dụng vẫn chấp nhận mọi yêu cầu đến khi token hết hạn vào buổi chiều, việc khóa tài khoản chưa được thực thi hiệu quả tại ứng dụng đó.

Một thiết kế xác minh liên tục cần trả lời được: thay đổi nào làm quyết định truy cập cũ không còn phù hợp, thay đổi được truyền tới đâu và thành phần nào thực sự chặn truy cập tiếp theo?

## 2. Xác minh lại điều gì?

Quyết định truy cập cần gắn với chủ thể, tài nguyên, hành động và ngữ cảnh cụ thể. Các bằng chứng liên quan có thể đến từ nhiều lớp.

| Lớp thông tin | Câu hỏi điển hình | Ví dụ thay đổi cần xem xét |
|---|---|---|
| Identity | Chủ thể còn tồn tại và được phép hoạt động không? | Tài khoản bị khóa hoặc chấm dứt |
| Authentication | Bằng chứng xác thực có hợp lệ và đủ mới cho thao tác không? | Phiên quá lâu chưa xác thực lại cho một thao tác nhạy cảm |
| Authorization | Chủ thể còn quyền với tài nguyên và hành động này không? | Thu hồi role, membership hoặc grant chia sẻ |
| Thiết bị hoặc workload | Nguồn thực hiện có đáp ứng chính sách hiện tại không? | Thiết bị bị đánh dấu có sự cố; workload không còn cấu hình được chấp thuận |
| Phiên và credential | Phiên hoặc credential có bị thu hồi, hết hạn hay sai phạm vi không? | Access token dùng sai dịch vụ đích; phiên đã bị kết thúc |
| Tài nguyên và môi trường | Điều kiện truy cập của tài nguyên có thay đổi không? | Tài liệu được phân loại nhạy cảm hơn hoặc policy mới có hiệu lực |

Không phải ứng dụng nào cũng có đầy đủ mọi tín hiệu. Thiết kế phải xác định bằng chứng nào là bắt buộc cho từng hành động và cách xử lý khi thiếu bằng chứng đó.

Một địa chỉ IP nội bộ, thiết bị được quản lý hoặc một lần MFA thành công có thể là đầu vào của quyết định. Không yếu tố nào trong số đó tự động tạo quyền đọc mọi tài nguyên.

Nếu Lan không có quyền `document.export`, việc xác thực lại thành công không được biến Lan thành người có quyền export. Xác thực bổ sung đáp ứng một điều kiện bảo mật; nó không thay thế quyết định cấp quyền nghiệp vụ.

## 3. Vòng lặp đánh giá và thực thi

Một vòng lặp xác minh liên tục thường gồm thu thập bằng chứng, đánh giá chính sách, thực thi kết quả và tiếp nhận thay đổi.

```text
Yêu cầu truy cập + bằng chứng đã xác minh
                    ↓
          Đánh giá chính sách hiện tại
                    ↓
     Cho phép / giới hạn / yêu cầu bổ sung / từ chối
                    ↓
         Điểm thực thi áp dụng quyết định
                    ↓
      Quan sát trạng thái và sự kiện liên quan
                    ↓
        Đánh giá lại tại điểm thích hợp
```

Có thể phân biệt các trách nhiệm sau:

- **Nguồn tín hiệu** cung cấp trạng thái identity, quyền, thiết bị, phiên hoặc tài nguyên.
- **Thành phần đánh giá chính sách** kết hợp bằng chứng với quy tắc để tạo quyết định.
- **Điểm thực thi chính sách** bảo vệ API, dịch vụ hoặc tài nguyên và áp dụng quyết định đó.

Đây là cách phân tách trách nhiệm để hiểu kiến trúc, không yêu cầu mọi hệ thống phải triển khai thành các dịch vụ độc lập. Một ứng dụng có thể kết hợp các trách nhiệm trong cùng tiến trình, nhưng vẫn cần biết nơi nào quyết định và nơi nào ngăn hành động.

Một cảnh báo được ghi vào dashboard chưa phải là thực thi. Nếu API tiếp tục trả dữ liệu như trước, hệ thống mới quan sát được thay đổi chứ chưa thay đổi quyền truy cập.

### Ba cách kích hoạt đánh giá lại

| Cách kích hoạt | Khi nào diễn ra? | Vai trò |
|---|---|---|
| Theo yêu cầu hoặc thao tác | Khi đọc tài nguyên, gọi API hoặc thực hiện hành động nhạy cảm | Kiểm tra quyết định tại điểm sử dụng |
| Theo sự kiện | Khi khóa tài khoản, thu hồi quyền, phát hiện thiết bị có sự cố hoặc cập nhật policy | Rút ngắn thời gian quyết định cũ còn được sử dụng |
| Theo thời gian | Khi bằng chứng, cache hoặc quyết định được lưu tạm đạt giới hạn độ mới | Tránh phụ thuộc vào dữ liệu cũ vô thời hạn |

Ba cách này bổ sung cho nhau. Chỉ kiểm tra định kỳ có thể để lại khoảng trễ giữa hai lần kiểm tra. Chỉ dựa vào sự kiện có thể bỏ sót thay đổi khi sự kiện bị mất hoặc một thành phần chưa hỗ trợ tiếp nhận.

“Liên tục” không có nghĩa mọi tín hiệu đều được thu thập lại từ nguồn gốc cho từng gói tin mạng. Nó có nghĩa các quyết định có điểm kiểm tra, giới hạn hiệu lực và cơ chế phản ứng phù hợp với mức nhạy cảm của truy cập.

## 4. Chất lượng tín hiệu quyết định chất lượng kiểm tra

Một tín hiệu chỉ hữu ích khi hệ thống hiểu được nguồn gốc, độ mới và đối tượng mà nó mô tả.

### 4.1. Nguồn gốc và liên kết đúng đối tượng

Giả sử client gửi header `Device-Compliant: true`. Nếu ứng dụng tin trực tiếp giá trị này, người gọi có thể tự khai thiết bị của mình an toàn. Bằng chứng về thiết bị cần đến từ một nguồn được hệ thống tin cậy và được liên kết với đúng thiết bị, identity hoặc phiên đang được đánh giá.

Tương tự, một sự kiện “thu hồi phiên” cần chỉ đúng phiên hoặc phạm vi tài khoản. Không nên kết thúc phiên của một người khác chỉ vì các hệ thống dùng cùng chuỗi định danh cục bộ mà không đối chiếu nguồn phát hành hoặc tenant.

Với sự kiện từ một thành phần bên ngoài, hệ thống cần kiểm tra tính xác thực của nguồn gửi, phạm vi áp dụng và cách nhận diện sự kiện. Chấp nhận một message chứa `accountDisabled=true` từ bất kỳ bên gửi nào có thể tạo ra một đường gây gián đoạn dịch vụ.

### 4.2. Độ mới của bằng chứng

Cần phân biệt thời điểm trạng thái được quan sát tại nguồn với thời điểm ứng dụng nhận được thông báo. Một message vừa được nhận có thể chứa thông tin đã cũ nhiều giờ.

Ví dụ bằng chứng minh họa:

```yaml
signal:
  type: DEVICE_POSTURE
  source: managed-device-service
  deviceId: device-27
  subjectId: user-lan
  state: COMPLIANT
  observedAt: "2026-06-01T08:00:00Z"
  receivedAt: "2026-06-01T08:00:05Z"
  sourceVersion: 42
```

Đây là schema minh họa, không phải định dạng giao thức bắt buộc. Policy cần xác định trạng thái `COMPLIANT` được chấp nhận trong bao lâu cho hành động đang xét. Thời hạn thích hợp cho việc đọc một thông báo nội bộ có thể khác với việc thay đổi quyền quản trị.

Phiên bản hoặc số thứ tự từ nguồn, khi có và được dùng đúng, có thể hỗ trợ xử lý sự kiện trùng lặp hoặc đến sai thứ tự. Không nên để một sự kiện trạng thái tốt cũ ghi đè một trạng thái thu hồi mới hơn chỉ vì sự kiện cũ được nhận sau.

### 4.3. Unknown không có nghĩa là an toàn

Không nhận được thông tin về thiết bị không đồng nghĩa thiết bị đáp ứng chính sách. Cần giữ riêng các trạng thái như `COMPLIANT`, `NON_COMPLIANT`, `UNKNOWN` hoặc bằng chứng quá cũ.

| Tình trạng tín hiệu | Cách diễn giải |
|---|---|
| Đủ mới và xác nhận đáp ứng điều kiện | Có thể dùng để thỏa một yêu cầu của policy |
| Đủ mới và xác nhận vi phạm điều kiện bắt buộc | Không cho phép hành động đòi hỏi điều kiện đó |
| Không có dữ liệu hoặc dữ liệu quá cũ | Chưa đủ bằng chứng; áp dụng quy tắc dành cho thiếu tín hiệu |
| Nguồn hoặc liên kết đối tượng không xác minh được | Không dùng làm bằng chứng đáng tin cậy |

Không nên gộp mọi thứ thành một điểm số rồi cho phép tín hiệu “mạng nội bộ” bù cho tình trạng “tài khoản đã bị khóa”. Điều kiện từ chối bắt buộc cần giữ hiệu lực ngay cả khi những tín hiệu khác có vẻ thuận lợi.

## 5. Kết quả đánh giá không chỉ có cho phép hoặc chặn

Tùy chính sách, hệ thống có thể đưa ra nhiều kết quả:

- **Cho phép:** bằng chứng và quyền hiện tại đáp ứng yêu cầu.
- **Cho phép có giới hạn:** chỉ đọc, giới hạn tài nguyên hoặc cấp quyền ngắn hạn theo policy được định nghĩa rõ.
- **Yêu cầu xác thực bổ sung:** cần chứng minh thêm quyền kiểm soát tài khoản hoặc đáp ứng độ mới xác thực.
- **Yêu cầu khắc phục:** thiết bị hoặc workload cần đáp ứng lại một điều kiện trước khi tiếp tục.
- **Từ chối hoặc thu hồi:** không cho phép yêu cầu mới, kết thúc phiên hoặc ngắt kênh truy cập đang mở khi có cơ chế hỗ trợ.

Kết quả có điều kiện phải được thực thi tại máy chủ. Ví dụ, nếu quyết định chỉ cho phép đọc thì API cập nhật phải bị từ chối, ngay cả khi giao diện vẫn hiển thị nút lưu.

Với yêu cầu xác thực bổ sung, hành động nhạy cảm chưa được thực hiện cho tới khi bằng chứng bổ sung được xác minh. Sau đó hệ thống cần đánh giá lại những điều kiện còn lại, vì quyền hoặc trạng thái tài nguyên có thể đã thay đổi trong thời gian người dùng hoàn tất xác thực.

Một quyết định cũng cần có phạm vi và thời hạn rõ ràng. Quyết định cho phép Lan đọc tài liệu A trong tenant An Phú không được tái sử dụng để Lan xuất toàn bộ tài liệu tenant Bình Minh.

## 6. Chính sách minh họa cho thao tác export

Giả sử ứng dụng có hai hành động: đọc tài liệu và export dữ liệu nhạy cảm. Policy minh họa sau đây được đặt ra cho ví dụ, không phải bộ điều kiện chuẩn cho mọi tổ chức.

```text
Đối với mọi hành động:
  - Identity, membership và phiên phải còn hợp lệ.
  - Tenant và tài nguyên phải đúng phạm vi.
  - Chủ thể phải có quyền nghiệp vụ tương ứng.
  - Tài khoản hoặc phiên đã bị thu hồi → từ chối.

Đối với export dữ liệu nhạy cảm:
  - Cần thiết bị đáp ứng policy và bằng chứng đủ mới.
  - Cần bằng chứng xác thực đủ mạnh và đủ mới theo policy.
  - Thiếu bằng chứng thiết bị bắt buộc → không thực hiện export.
  - Thiếu độ mới xác thực nhưng các điều kiện khác hợp lệ
    → yêu cầu xác thực bổ sung rồi đánh giá lại.
```

Một số quyết định có thể phát sinh:

| Ngữ cảnh | Kết quả theo policy minh họa |
|---|---|
| Có quyền export, thiết bị đạt yêu cầu, xác thực đủ mới | Có thể cho phép export |
| Có quyền export nhưng xác thực chưa đủ mới | Yêu cầu xác thực bổ sung; chưa chạy export |
| Không có quyền export dù MFA vừa thành công | Từ chối export |
| Tài khoản đã bị khóa | Từ chối; không dùng MFA để bỏ qua trạng thái khóa |
| Không lấy được bằng chứng thiết bị bắt buộc | Không chạy export cho đến khi đủ điều kiện |
| Token hợp lệ về định dạng và thời hạn nhưng phiên đã bị thu hồi | Từ chối nếu điểm thực thi đã nhận và áp dụng trạng thái thu hồi |

Mã giả cho luồng quyết định:

```text
function handleSensitiveAction(request):
    context = verifyCredentialAndBindContext(request)
    require context.identityIsActive
    require context.sessionIsUsable
    require context.tenantAndResourceAreConsistent

    permission = loadEffectivePermission(context, request.action)
    require permission.allowsAction

    signals = loadRelevantSignalsWithFreshness(context, request.action)
    decision = evaluateCurrentPolicy(context, permission, signals)

    if decision.requiresAdditionalEvidence:
        return challengeWithoutExecutingAction(decision.requirements)

    if decision.deniesAction:
        recordDecisionWithoutSecrets(context, decision)
        return denied

    enforceDecisionScopeAndObligations(decision)
    revalidateAtExecutionBoundaryWhenRequired(context, decision)
    return executeWithinAuthorizedScope(request, decision)
```

Mã giả mô tả trách nhiệm chứ chưa phải một triển khai hoàn chỉnh. Nếu quyết định được lưu tạm hoặc gửi sang thành phần khác, cần ràng buộc nó với đúng chủ thể, phiên, tenant, tài nguyên, hành động và thời hạn. Một kết quả `ALLOW` không có ngữ cảnh không đủ để thực thi an toàn.

Đối với thay đổi đặc quyền hoặc thao tác ghi quan trọng, có thể cần kiểm tra phiên bản quyền hay trạng thái tài nguyên ngay tại ranh giới thực thi. Điều này giảm nguy cơ quyền đã bị thu hồi sau khi đánh giá nhưng trước khi thay đổi được ghi. Kiến trúc vẫn cần xác định rõ tính nhất quán và khoảng trễ thực tế, thay vì giả định mọi thành phần cập nhật đồng thời.

## 7. Phiên, token và khoảng trễ thu hồi

### 7.1. Token còn hạn chưa nói hết trạng thái truy cập

Một access token có thể vẫn còn hạn sau khi tài khoản hoặc quyền của chủ thể thay đổi. Nếu resource server chỉ xác minh chữ ký và thời hạn của token, nó có thể chưa biết một thay đổi xảy ra sau thời điểm token được cấp.

Kiểm tra token tại mỗi yêu cầu là cần thiết theo mô hình credential đang dùng, nhưng không tự động biến các claim thành trạng thái hiện tại. Role được chụp vào token lúc cấp có thể đã khác với role hiệu lực lúc sử dụng.

Các cơ chế có thể kết hợp gồm:

- Access token có thời hạn phù hợp để giới hạn thời gian sử dụng dữ liệu cũ.
- Kiểm tra phiên, quyền hoặc phiên bản quyền tại máy chủ.
- Tra cứu trạng thái token theo cơ chế của hệ thống xác thực.
- Tiếp nhận sự kiện thu hồi để cập nhật danh sách phiên hoặc credential không còn được chấp nhận.
- Vô hiệu hóa cache quyết định quyền khi có thay đổi liên quan.

Mỗi cơ chế có chi phí, phụ thuộc vận hành và giới hạn riêng. Tra cứu trạng thái nhưng lưu kết quả quá lâu cũng có thể giữ quyết định cũ. Token ngắn hạn giúp giới hạn một khoảng thời gian, nhưng không tương đương với việc thu hồi tức thời trong khoảng thời gian đó.

### 7.2. Phải xác định thu hồi cái gì

| Hành động | Điều nó trực tiếp tác động | Điều không nên mặc định |
|---|---|---|
| Thu hồi một phiên ứng dụng | Phiên do ứng dụng quản lý và các điểm có kiểm tra trạng thái đó | Mọi access token ở mọi dịch vụ tự động vô hiệu |
| Thu hồi refresh credential | Khả năng nhận credential mới theo cơ chế tương ứng | Access token đã cấp lập tức hết hiệu lực |
| Thu hồi role hoặc membership | Quyền hiệu lực ở nguồn quản lý quyền | Mọi cache và token đã nhận thay đổi ngay |
| Chặn một thiết bị | Truy cập gắn với thiết bị theo khả năng liên kết và thực thi | Tự động khóa toàn bộ identity trong mọi trường hợp |

Chính sách thu hồi cần khớp với khả năng của resource server và những kênh truy cập đang tồn tại. Nếu một dịch vụ chưa tiêu thụ sự kiện thu hồi, phải ghi nhận giới hạn đó trong thiết kế và chọn biện pháp phù hợp cho dữ liệu nhạy cảm.

### 7.3. Khoảng trễ phản ứng cần đo được

Có thể hình dung thời gian phản ứng của một đường xử lý sự kiện gồm thời gian phát hiện thay đổi, thời gian truyền thay đổi và thời gian điểm thực thi áp dụng thay đổi. Đây là mô hình phân tích vận hành, không phải công thức đảm bảo cho mọi kiến trúc.

Nếu điểm thực thi chỉ cập nhật khi cache hết hạn hoặc khi token được làm mới, thời gian chờ đó cũng ảnh hưởng cửa sổ truy cập còn lại. Vì vậy, cần đo từ lúc một trạng thái được xác lập ở nguồn đến lúc một yêu cầu liên quan thực sự bị từ chối tại các dịch vụ đích.

## 8. Kết nối dài và tác vụ bất đồng bộ

Đánh giá lại từng HTTP request không đủ cho mọi loại truy cập. Một kết nối WebSocket, phiên điều khiển từ xa hoặc luồng tải dữ liệu có thể kéo dài sau thời điểm thiết lập ban đầu.

Thiết kế cần xác định các điểm kiểm tra trong vòng đời kênh đó: khi mở kết nối, khi bắt đầu một hành động nhạy cảm, theo thời hạn đánh giá hoặc khi nhận sự kiện thu hồi. Nếu có yêu cầu ngắt truy cập đang mở, điểm thực thi phải có khả năng tìm và đóng đúng kênh.

Với một luồng dữ liệu, việc thu hồi chỉ có thể chặn các hành động hoặc dữ liệu chưa được cung cấp theo khả năng của hệ thống. Nó không thu lại dữ liệu mà người dùng đã tải hoặc đã nhìn thấy.

Đối với job export hoặc xử lý nền, cần phân biệt thẩm quyền của người yêu cầu và thẩm quyền của workload thực thi. Hệ thống phải quy định job có cần kiểm tra lại quyền người yêu cầu khi bắt đầu chạy hay ở các mốc tiếp theo không.

Ví dụ, một export nhạy cảm có thể kiểm tra quyền khi nhận yêu cầu, khi worker bắt đầu xử lý và khi người dùng tải kết quả. Việc hủy job không tự động làm mất hiệu lực một liên kết tải đã được cấp trước đó; cơ chế phân phối kết quả phải có thiết kế thời hạn và thu hồi tương ứng.

## 9. Tình huống xuyên suốt: thay đổi trạng thái trong một phiên

Lan đăng nhập vào ứng dụng tài liệu của An Phú. Thiết bị được quản lý, membership hoạt động và Lan có quyền đọc lẫn export.

| Thời điểm | Sự kiện | Hành vi mong đợi theo policy ví dụ |
|---|---|---|
| T0 | Lan đăng nhập thành công | Tạo phiên; vẫn kiểm tra quyền với tài nguyên ở các lần sử dụng |
| T1 | Lan đọc một tài liệu được phép | Kiểm tra tenant, quyền đọc và điều kiện hiện hành rồi trả dữ liệu |
| T2 | Lan yêu cầu export; bằng chứng xác thực chưa đủ mới | Chưa export; yêu cầu xác thực bổ sung |
| T3 | Lan hoàn tất xác thực bổ sung | Đánh giá lại quyền và điều kiện trước khi chạy export |
| T4 | Nguồn thiết bị báo thiết bị không còn đáp ứng điều kiện bắt buộc | Cập nhật trạng thái; chặn các hành động yêu cầu điều kiện đó khi điểm thực thi áp dụng thay đổi |
| T5 | Tài khoản Lan bị khóa | Từ chối truy cập theo cơ chế thu hồi; xử lý phiên và kênh đang mở trong phạm vi hệ thống hỗ trợ |

Nếu sự kiện T4 chỉ xuất hiện trên dashboard còn API export tiếp tục cho phép vô thời hạn, vòng lặp thực thi chưa hoàn chỉnh.

Nếu Lan hoàn tất MFA ở T3 nhưng quyền export đã bị thu hồi trong lúc đó, kết quả đúng vẫn là từ chối export. Một lần xác thực mới không khôi phục một quyền đã bị gỡ.

Nếu tài liệu đã được tải xong ở T1, hệ thống không thể xem thao tác khóa tài khoản tại T5 như cách xóa bản sao đã nằm trên thiết bị. Xác minh liên tục giới hạn các truy cập tiếp theo; bảo vệ dữ liệu sau khi cung cấp còn cần những kiểm soát khác phù hợp với sản phẩm.

## 10. Khi nguồn tín hiệu hoặc dịch vụ chính sách gặp lỗi

Xác minh liên tục tạo thêm các phụ thuộc cần được vận hành. Nguồn trạng thái thiết bị có thể chậm; sự kiện thu hồi có thể đến sai thứ tự; thành phần đánh giá chính sách có thể không truy cập được.

Thiết kế cần quy định trước cách xử lý cho từng loại hành động:

- Với hành động đòi hỏi bằng chứng bắt buộc mà không có bằng chứng đủ mới, không thực hiện hành động đó.
- Với hành động ít nhạy cảm hơn, policy có thể cho phép sử dụng bằng chứng hoặc quyết định đã lưu trong một giới hạn cụ thể, nếu mức rủi ro đã được chấp nhận rõ ràng.
- Không tự động chuyển lỗi kiểm tra thành `ALLOW` cho mọi hành động.
- Không để một quyết định lưu tạm mất thời hạn trở thành quyền truy cập vô hạn khi hệ thống phụ thuộc bị lỗi.

Một cơ chế truy cập khẩn cấp, nếu có, cần được thiết kế riêng với phạm vi, người chịu trách nhiệm, thời hạn và audit. Nó không nên là hành vi fallback ngầm mà bất kỳ người gọi nào cũng có thể kích hoạt bằng cách làm một dịch vụ kiểm tra bị lỗi.

Các chỉ số hữu ích gồm độ mới của tín hiệu tại thời điểm quyết định, thời gian thu hồi được áp dụng tại dịch vụ đích, tỷ lệ quyết định dùng cache, số hành động bị chặn do thiếu tín hiệu và số điểm thực thi chưa nhận được phiên bản policy hiện hành.

Audit nên ghi chủ thể, tenant, hành động, tài nguyên hoặc phạm vi cần thiết, kết quả, lý do và phiên bản chính sách hoặc bằng chứng liên quan. Không lưu mật khẩu, token đầy đủ hay dữ liệu nhạy cảm quá mức để giải thích một quyết định.

Thu thập nhiều tín hiệu hơn không tự động làm policy tốt hơn. Cần giới hạn dữ liệu theo mục đích, bảo vệ quyền truy cập vào tín hiệu và có cách xử lý khi tín hiệu sai dẫn tới chặn nhầm người dùng hợp lệ.

## 11. Áp dụng cho workload identity

Continuous verification không chỉ dành cho con người. Một dịch vụ xử lý đơn hàng hoặc worker export cũng có identity, credential, quyền và trạng thái triển khai có thể thay đổi.

Ví dụ, worker export chỉ được đọc một tập dữ liệu cho một tenant trong một tác vụ cụ thể. Việc nó nằm trong mạng nội bộ không thay thế kiểm tra workload identity, dịch vụ đích, tenant và quyền của tác vụ.

Các kiểm tra có thể gồm credential còn hợp lệ, quyền workload còn hiệu lực, phạm vi token hoặc chứng thực phù hợp và cấu hình triển khai đáp ứng policy của tổ chức. Nếu sử dụng bằng chứng môi trường thực thi, nguồn và độ mới của bằng chứng đó cũng cần được xác minh.

Workload không giải quyết xác thực bổ sung bằng cách hiện hộp thoại MFA. Thay vào đó, hệ thống có thể yêu cầu credential mới theo cơ chế được thiết kế, đánh giá lại quyền, chặn tác vụ, cách ly workload hoặc yêu cầu người có thẩm quyền xử lý qua quy trình vận hành riêng.

Luân chuyển credential hỗ trợ quản lý vòng đời bí mật nhưng không thay thế kiểm tra quyền. Một credential vừa được cấp vẫn có thể mang phạm vi quá rộng hoặc được dùng cho một hành động ngoài nhiệm vụ.

## 12. Những hiểu lầm và câu hỏi tự kiểm tra

**“Continuous verification là bắt MFA liên tục.”** Nhiều kiểm tra diễn ra ở máy chủ và không cần người dùng tương tác. MFA chỉ là một loại bằng chứng xác thực.

**“Đã kiểm tra token ở mọi API nên quyền luôn mới.”** Token có thể chứa trạng thái tại thời điểm cấp. Cần xem resource server biết thay đổi quyền hoặc thu hồi bằng cách nào.

**“Thiết bị đạt chuẩn thì được truy cập mọi tài nguyên.”** Trạng thái thiết bị chỉ thỏa một điều kiện, không thay thế quyền nghiệp vụ, tenant hoặc phạm vi tài nguyên.

**“Phát hiện rủi ro là đã bảo vệ được truy cập.”** Cần có đường truyền và điểm thực thi áp dụng quyết định mới.

**“Đã thu hồi refresh credential là mọi token cũ đều hỏng ngay.”** Hiệu lực access token đã cấp còn phụ thuộc cách resource server kiểm tra và tiếp nhận thu hồi.

**“Xác minh liên tục bảo đảm không còn khoảng trễ.”** Mọi kiến trúc có giới hạn về truyền trạng thái, cache, xử lý đang diễn ra và khả năng ngắt kênh. Cần đo và quản lý các giới hạn đó.

Câu hỏi tự kiểm tra:

1. Vì sao một lần MFA mới không đủ để cho phép thao tác mà chủ thể đã bị thu hồi quyền?
2. Sự khác nhau giữa `UNKNOWN` và trạng thái đáp ứng điều kiện là gì khi nguồn tín hiệu không truy cập được?
3. Khi tài khoản bị khóa, những thành phần nào phải nhận hoặc tra cứu trạng thái để yêu cầu tiếp theo bị từ chối?
4. Một WebSocket đang mở hoặc job export đang chờ cần các điểm đánh giá lại nào?
5. Làm thế nào đo được khoảng thời gian từ sự kiện thu hồi tại nguồn đến khi API đích thực sự chặn truy cập?

Continuous verification duy trì mối liên hệ giữa bằng chứng hiện hành, chính sách và hành động được thực thi. Giá trị của nó nằm ở khả năng thay đổi quyết định khi trạng thái thay đổi, với phạm vi và độ trễ được xác định rõ cho từng loại truy cập.
