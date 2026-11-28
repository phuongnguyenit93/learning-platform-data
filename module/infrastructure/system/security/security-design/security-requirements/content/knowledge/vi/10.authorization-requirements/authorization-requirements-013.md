# Authorization cache

## 1. Cache quyết định quyền là một phần của cơ chế bảo mật

Authorization cache là bộ nhớ đệm cho kết quả hoặc dữ liệu phục vụ quyết định phân quyền. Mục tiêu thường là giảm độ trễ, giảm tải cho bộ đánh giá chính sách và hạn chế việc đọc lặp lại vai trò, quan hệ hoặc thuộc tính tài nguyên.

Ví dụ, API hỏi người dùng Minh có được đọc tài liệu D trong tenant A hay không. Nếu câu trả lời vừa được tính và các điều kiện còn hiệu lực, hệ thống có thể tái sử dụng kết quả thay vì đánh giá lại toàn bộ.

Tuy nhiên, quyền có thể thay đổi trong thời gian cache tồn tại:

- Minh bị xóa khỏi nhóm có quyền đọc.
- D được chuyển sang phạm vi hạn chế.
- Quản trị viên thay chính sách hoặc thêm lệnh chặn.
- Phiên bị thu hồi, quyền ủy quyền hết hạn.
- Lần xác thực mạnh không còn đủ mới cho hành động nhạy cảm.

Vì vậy, yêu cầu “cache quyền trong 5 phút” chưa đủ để thiết kế an toàn. Cần nói rõ cache cái gì, khóa chứa những đầu vào nào, kết quả được dùng đến khi nào, thay đổi nào làm mất hiệu lực và hệ thống phản ứng ra sao khi không xác định được độ mới.

Trong chương **Yêu cầu authorization**, bài này hướng đến việc chuyển các rủi ro của cache thành yêu cầu cụ thể, đo được và kiểm chứng được; liên kết chúng với kiến trúc, logging, thu hồi và tiêu chí kiểm thử trong vòng đời phát triển.

## 2. Xác định chính xác đối tượng được cache

Không phải mọi loại cache liên quan người dùng đều có cùng ý nghĩa.

| Loại cache | Dữ liệu thường lưu | Rủi ro chính |
|---|---|---|
| Cache quyết định | Cho phép/từ chối hành động của chủ thể trên tài nguyên | Tái sử dụng kết quả sai phạm vi hoặc đã cũ |
| Cache vai trò/quyền được cấp | Vai trò, tập quyền hoặc membership | Tiếp tục dùng quyền đã bị thu hồi |
| Cache quan hệ | Nhóm, sở hữu, chia sẻ, parent trong ReBAC | Quan hệ cũ tạo ra quyền suy diễn không còn hợp lệ |
| Cache thuộc tính | Tenant tài nguyên, trạng thái, mức nhạy cảm | Đánh giá đúng công thức nhưng bằng dữ liệu lỗi thời |
| Cache chính sách | Phiên bản quy tắc hoặc chương trình đánh giá | Tiếp tục áp dụng policy cũ |
| Cache trạng thái phiên/token | Hiệu lực phiên, kết quả kiểm tra token | Không phát hiện phiên hoặc token bị thu hồi |
| Cache phản hồi nghiệp vụ | Nội dung tài liệu, hồ sơ, file xuất | Trả dữ liệu cho người không còn được phép dù quyết định cache đã bị xóa |

Một kết quả quyết định có thể mới được tạo từ dữ liệu thuộc tính đã cũ. Xóa cache quyết định nhưng giữ cache membership cũ có thể tạo ngay một kết quả ALLOW cũ với thời hạn mới.

Tương tự, vô hiệu hóa cache quyền không tự làm mất hiệu lực URL tải file, bản phản hồi trong CDN hoặc phiên đang được xử lý. Đặc tả phải theo toàn bộ đường cung cấp dữ liệu.

## 3. Xác định hợp đồng an toàn trước mục tiêu hiệu năng

### 3.1. Ba câu hỏi nền tảng

Trước khi chọn TTL, cần trả lời:

1. **Phạm vi tương đương:** hai yêu cầu nào thực sự được dùng chung một quyết định?
2. **Độ mới:** thay đổi quyền hoặc dữ liệu được phép chưa phản ánh trong bao lâu?
3. **Điểm thực thi:** kiểm tra phải còn đúng tại lúc đọc, lúc ghi, lúc phát lệnh hay trong cả một luồng dài?

TTL, hay time to live, là thời gian tồn tại của mục cache. Nó là một công cụ thực thi giới hạn độ cũ, không tự định nghĩa hợp đồng thu hồi của hệ thống.

### 3.2. Phân nhóm hành động theo rủi ro

Ví dụ cho một nền tảng quản lý tài liệu nhiều tổ chức:

| Hành động | Chính sách cache mẫu | Điều kiện bổ sung |
|---|---|---|
| Xem metadata thông thường | Cho phép tái sử dụng quyết định trong giới hạn độ cũ đã thống nhất | Vẫn xác thực yêu cầu và kiểm tra đúng tài nguyên/tenant |
| Đọc nội dung hạn chế | Cần mốc quyền đủ mới cho phiên bản dữ liệu | Không đọc nội dung mới bằng quyền trước thay đổi phạm vi |
| Xuất dữ liệu hàng loạt | Kiểm tra quyền khi nhận việc, trước truy vấn và trước tải | Quyền riêng và bằng chứng xác thực đủ mới |
| Cấp quyền quản trị | Không tái sử dụng quyết định ALLOW qua các yêu cầu trong ví dụ này | Kiểm tra điều kiện hiện hành tại điểm ghi |
| Thanh toán hoặc xác nhận một lần | Không coi ALLOW được cache là bằng chứng đã tiêu thụ quyền một lần | Vẫn cần kiểm tra và tiêu thụ nguyên tử |

Đây là lựa chọn minh họa, không phải quy định chung cho mọi sản phẩm. Tắt cache quyết định của một hành động cũng chưa đủ nếu bộ đánh giá vẫn đọc thuộc tính quá cũ.

### 3.3. Cách viết yêu cầu có thể nghiệm thu

> Với các API đọc thuộc phạm vi, hệ thống chỉ tái sử dụng quyết định cho cùng chủ thể, tenant, hành động, tài nguyên và ngữ cảnh ảnh hưởng đến quyền. Không được dùng quyết định quá hạn hoặc không đáp ứng mốc quyền tối thiểu. Quan hệ bị thu hồi không được tiếp tục tạo quyền sau tối đa 60 giây từ lúc lệnh thu hồi được ghi nhận thành công tại nguồn có thẩm quyền.

Yêu cầu này cần được chi tiết hóa bằng nguồn dữ liệu, điểm kiểm soát, ngân sách độ trễ và bằng chứng kiểm thử. Con số 60 giây trong bài là tham số giả định.

## 4. Thiết kế khóa cache theo ý nghĩa quyết định

### 4.1. Những đầu vào có thể làm thay đổi quyền

Một khóa khái niệm:

```text
key = hash(canonical(
    namespace,
    subjectIdentity,
    delegationContext,
    tenantIdentity,
    action,
    resourceType,
    resourceIdentity,
    relevantPolicyVersion,
    relevantAuthorizationVersions,
    relevantContext
))
```

Không phải hệ thống nào cũng dùng toàn bộ trường này dưới dạng khóa. Một số thuộc tính có thể được kiểm tra khi đọc entry hoặc được quản lý bằng cơ chế version. Điều bắt buộc là không cho hai ngữ cảnh có kết quả khác nhau dùng nhầm cùng kết quả.

| Thành phần | Vì sao cần xét? | Lỗi nếu thiếu |
|---|---|---|
| Chủ thể ổn định | Phân biệt người dùng và danh tính dịch vụ | Người B nhận quyết định của A |
| Tenant | Cùng ID hoặc role có thể tồn tại ở nhiều tổ chức | Vượt ranh giới tổ chức |
| Hành động | Read, edit, share và export có ý nghĩa khác nhau | Quyền đọc bị dùng để sửa/xuất |
| Kiểu và ID tài nguyên | Hai kiểu có thể có cùng ID cục bộ | Quyền tài liệu bị dùng cho hồ sơ khác |
| Ngữ cảnh ủy quyền | Dịch vụ có thể thực hiện thay những người khác nhau | Dùng quyền rộng của dịch vụ thay người yêu cầu |
| Policy/version quyền | Quy tắc hoặc quan hệ có thể thay đổi | Quyết định cũ sống qua một lần thu hồi |
| Mức và thời điểm xác thực | Hành động có thể yêu cầu MFA gần đây | Kết quả trước đó bỏ qua step-up |
| Ngữ cảnh ảnh hưởng quyền | Phân công, mục đích, trạng thái hoặc thời hạn | Tái sử dụng ngoài điều kiện đã được đánh giá |

Không đưa mọi header vào khóa một cách máy móc. Cần liệt kê những thuộc tính thực sự quyết định quyền, xác định nguồn tin cậy và kiểm thử tác động của chúng.

### 4.2. Thuộc tính phải đến từ nguồn tin cậy

Không được dùng role, tenant, mức xác thực hoặc phiên bản quyền do khách tự khai làm căn cứ tin cậy.

Ví dụ, token có thể chứa số phiên bản quyền tại lúc phát hành. Chữ ký hợp lệ chứng minh claim do bên phát hành đưa ra; nó không chứng minh đây vẫn là phiên bản hiện hành sau khi người dùng bị thu hồi quyền. Muốn dùng version để phát hiện thay đổi, cần có cách đối chiếu với trạng thái đủ mới từ nguồn có thẩm quyền.

Tenant trong URL có thể là tham chiếu người dùng yêu cầu truy cập. Máy chủ còn phải kiểm tra tư cách thành viên và tenant thật của tài nguyên.

### 4.3. Chuẩn hóa khóa và tách không gian

Chuẩn hóa phải bảo toàn ý nghĩa:

- Phân biệt trường vắng mặt với giá trị cụ thể nếu chính sách phân biệt chúng.
- Không nhập nhằng số, chuỗi, chữ hoa/thường hoặc ký tự phân cách.
- Nếu một tập được coi là không có thứ tự, chuẩn hóa thứ tự trước khi băm.
- Tách môi trường, dịch vụ, loại quyết định và phiên bản định dạng entry.
- Không trộn ID cục bộ của các tenant hoặc loại tài nguyên.

Ghép chuỗi tùy ý như `user + ":" + action + ":" + id` có thể gây va chạm ngữ nghĩa nếu thành phần được phép chứa cùng ký tự phân cách. Dùng cấu trúc tuần tự hóa có định nghĩa rõ.

Băm khóa không phải mã hóa dữ liệu. Không đưa bearer token hoặc thông tin nhạy cảm không cần thiết vào khóa, log hoặc nhãn metric chỉ vì đã băm một phần.

## 5. Entry phải chứa điều kiện hiệu lực, không chỉ ALLOW

Một cấu trúc khái niệm:

```text
AuthorizationCacheEntry:
    formatVersion
    effect
    policyVersion
    authorizationRevisionOrDependencyVersions
    evaluatedAt
    sourceFreshnessBounds
    usableUntil
    obligations
    trustedIssuerOrIntegrityMetadata
```

Trong đó:

- **effect:** kết quả như ALLOW hoặc DENY; một số hệ thống có kết quả yêu cầu điều kiện bổ sung.
- **usableUntil:** thời điểm cuối được phép tái sử dụng theo chính sách.
- **sourceFreshnessBounds:** giới hạn độ mới của dữ liệu nguồn được sử dụng.
- **obligations:** nghĩa vụ mà điểm thực thi phải thực hiện.
- **version:** thông tin để phát hiện policy, quan hệ hoặc định dạng đã thay đổi.

Một entry đọc được thành công vẫn có thể không dùng được vì sai version, không đủ mới, thiếu trường hoặc không thực thi được nghĩa vụ. Cache hit ở tầng lưu trữ không đồng nghĩa cache hit hợp lệ về mặt bảo mật.

### 5.1. Nghĩa vụ phải chạy cả khi cache hit

Ví dụ ALLOW đi kèm:

- Chỉ trả một số trường.
- Ghi audit cho mỗi lần xuất dữ liệu.
- Yêu cầu xác thực gần đây.
- Giới hạn phạm vi truy vấn.
- Thực hiện kiểm tra hạn mức hoặc tiêu thụ xác nhận một lần.

Nếu chỉ làm các bước này khi cache miss, đường cache hit trở thành đường bỏ kiểm soát.

Không cache việc “còn một lượt” rồi cho nhiều yêu cầu cùng dùng lượt đó. Quyết định được phép thử hành động và việc tiêu thụ quota, phê duyệt hoặc token một lần là các thao tác khác nhau; phần tiêu thụ vẫn cần cơ chế nguyên tử.

### 5.2. Thời hạn phụ thuộc ngữ cảnh

Ví dụ người dùng có bằng chứng MFA đã 4 phút 50 giây; tác vụ yêu cầu không quá 5 phút. Quyết định không được tái sử dụng thêm 60 giây chỉ vì TTL chung là 60 giây.

Một công thức khái niệm:

```text
usableUntil = minimum(
    evaluationTime + decisionTTL,
    sourceFreshnessDeadline,
    authenticationFreshnessDeadline,
    delegationExpiry,
    policyNotAfter,
    otherRelevantDeadlines
)
```

Chỉ đưa những hạn có liên quan vào công thức. Nếu một điều kiện động không thể được ràng buộc an toàn bằng khóa hoặc thời hạn, hãy kiểm tra lại điều kiện đó tại mỗi lần sử dụng hoặc không cache kết quả tương ứng.

Thời hạn cache không được làm cho token hoặc phiên hết hiệu lực trở lại có hiệu lực. Mỗi yêu cầu vẫn phải đi qua cơ chế xác thực và hiệu lực phiên theo hợp đồng của hệ thống.

## 6. TTL không tự bảo đảm thời hạn thu hồi

### 6.1. Độ cũ có thể đi qua nhiều tầng

Xét luồng:

```text
Nguồn quan hệ
    -> bản sao quan hệ
    -> cache thuộc tính
    -> cache quyết định dùng chung
    -> cache cục bộ trong tiến trình
    -> điểm thực thi
```

Sau khi nguồn thu hồi một membership, bản sao cũ có thể vẫn trả “còn là thành viên”. Bộ đánh giá tạo một ALLOW mới từ dữ liệu đó. Sau đó cache cục bộ lại sao chép ALLOW và tự bắt đầu một TTL mới.

Nếu mỗi tầng cấp lại toàn bộ thời gian sống mà không xét tuổi và hạn của nguồn, quyền cũ có thể tồn tại lâu hơn TTL được công bố.

### 6.2. Ngân sách độ cũ từ đầu đến cuối

Một mô hình bảo thủ cho một đường thực thi:

```text
B_total =
    B_upstream_staleness
    + B_reuse_after_evaluation
    + B_clock_uncertainty
    + B_enforcement_delay
```

Yêu cầu là `B_total <= R`, với R là giới hạn thu hồi của hành động đó.

Công thức chỉ hữu ích nếu từng thành phần có giới hạn thực sự và mọi tầng trung gian được tính đúng. Nếu nhiều cache kéo dài tuổi độc lập, phải đưa phần kéo dài đó vào ngân sách; không giả định chúng tự nằm trong cùng một TTL.

Ví dụ giả định cho R = 60 giây:

| Thành phần | Giới hạn mẫu |
|---|---:|
| Dữ liệu quan hệ/thuộc tính có thể chậm sau nguồn | 20 giây |
| Tái sử dụng quyết định tính từ thời điểm đánh giá | 25 giây |
| Bất định thời gian đã được kiểm soát | 2 giây |
| Từ kiểm tra đến điểm thực thi có bảo vệ | 5 giây |
| Tổng ngân sách | 52 giây |

Ví dụ chỉ có ý nghĩa khi cache cục bộ và cache dùng chung giữ nguyên hạn tối đa của cùng quyết định, không tự cấp thêm TTL mới; và không có nguồn hoặc hàng đợi nào chưa được tính vào 20 giây.

Nếu yêu cầu chạy lâu rồi mới gây tác dụng, giới hạn 5 giây không tự tồn tại. Cần kiểm tra lại ở điểm phù hợp hoặc thiết kế điều kiện giao dịch để đáp ứng cam kết.

### 6.3. Sao chép không được làm trẻ entry

Khi copy L2 sang L1:

- Giữ giới hạn hiệu lực gốc hoặc tính thời gian còn lại.
- Không đổi `evaluatedAt` thành thời điểm copy.
- Không coi việc đọc từ cache là bằng chứng nguồn mới.
- Không gia hạn ALLOW chỉ vì có nhiều người sử dụng.

Sliding expiration có thể hữu ích với dữ liệu thông thường nhưng nguy hiểm nếu mọi lần hit lại kéo dài quyền đã thu hồi. Nếu dùng cơ chế này, vẫn phải có một hạn an toàn tuyệt đối không được kéo dài.

Khi làm mới quyết định, dữ liệu nguồn cũng phải đáp ứng độ mới. Đánh giá lại cùng membership lỗi thời không phải một lần làm mới hợp lệ cho cam kết thu hồi.

### 6.4. Thời gian và ranh giới hết hạn

Đặc tả phải nêu rõ tại `now == usableUntil` entry đã không còn được dùng.

Trong một tiến trình, đo khoảng thời gian bằng đồng hồ đơn điệu có thể tránh việc chỉnh lùi đồng hồ làm tăng tuổi thọ. Khi truyền thời hạn giữa các máy, cần quy tắc về đồng bộ và bất định thời gian. Không thể so trực tiếp các giá trị đồng hồ đơn điệu của hai máy như cùng một mốc.

Sau khởi động lại hoặc khi không thể xác định entry còn hạn một cách tin cậy, không được tự cấp lại thời gian sống đầy đủ. Có thể bỏ entry và đánh giá lại theo đường đủ mới.

## 7. Vô hiệu hóa cache và cuộc đua với đánh giá đang chạy

### 7.1. Invalidation theo sự kiện

Khi quan hệ hoặc policy thay đổi, nguồn có thể phát sự kiện vô hiệu hóa. Yêu cầu cần xác định:

- Thay đổi nào phát sự kiện.
- Những cache và điểm thực thi nào phải nhận.
- Độ trễ tối đa.
- Cách xử lý sự kiện trùng, sai thứ tự hoặc bị mất.
- Cách phục hồi sau mất kết nối.
- Cách biết consumer đã theo kịp mốc bắt buộc.

Sự kiện cần được phát bền vững theo cơ chế phối hợp với cập nhật nguồn, chẳng hạn outbox phù hợp. Chỉ “publish sau khi lưu” mà không xử lý trường hợp tiến trình chết giữa hai bước sẽ tạo khoảng mất sự kiện.

TTL có thể là giới hạn dự phòng khi invalidation thất bại, nhưng TTL dự phòng và độ cũ nguồn vẫn phải nằm trong ngân sách thu hồi.

### 7.2. Xóa cache có thể bị kết quả cũ ghi trở lại

Trình tự nguy hiểm:

```text
1. Request A đọc membership cũ và bắt đầu đánh giá.
2. Membership bị thu hồi.
3. Sự kiện xóa entry khỏi cache.
4. Request A hoàn tất ALLOW từ dữ liệu cũ.
5. Request A ghi ALLOW trở lại với TTL mới.
```

Yêu cầu “xóa cache khi thu hồi” không xử lý đủ trường hợp này.

Có thể dùng revision, generation hoặc cơ chế fencing để ngăn kết quả cũ được công bố cho thế hệ mới. Fencing ở đây là việc kiểm tra mốc hợp lệ để chặn kết quả đã lỗi thời ghi trở lại.

Ví dụ:

> Mọi kết quả đánh giá phải mang phiên bản dữ liệu/quyền đã sử dụng. Cache không được công bố hoặc sử dụng kết quả thuộc thế hệ trước sau khi điểm thực thi đã ghi nhận thế hệ mới bắt buộc.

Cơ chế phiên bản cũng có giới hạn: nếu “phiên bản hiện hành” được đọc từ chính một cache quá cũ, nó không tự chứng minh đủ mới. Nguồn version, cách lan truyền và giới hạn độ trễ phải có hợp đồng.

### 7.3. Không làm sống lại phiên bản cũ khi sự kiện sai thứ tự

Nếu sự kiện revision 12 đến trước revision 11, consumer không được đưa trạng thái trở lại 11. Retry phải idempotent và cập nhật version phải đơn điệu trong miền phiên bản đã định nghĩa.

Không so sánh các version không cùng nguồn như thể chúng là một số thứ tự toàn cục. Một hệ thống có thể cần nhiều mốc cho policy, tenant, chủ thể và tài nguyên.

Khi thay định dạng hoặc policy, cần namespace/version rõ để entry cũ không được diễn giải theo ngữ nghĩa mới.

## 8. Cache ALLOW, cache DENY và xử lý sự cố

### 8.1. Kết quả cho phép và từ chối có rủi ro khác nhau

- **ALLOW cũ** có thể tiếp tục cung cấp quyền đã bị thu hồi.
- **DENY cũ** có thể trì hoãn quyền mới, gây gián đoạn và làm người dùng tưởng quyền chưa được cấp.
- **Lỗi đánh giá** không phải một kết quả DENY nghiệp vụ ổn định.

Có thể dùng TTL khác nhau cho ALLOW và DENY theo rủi ro. Ví dụ ALLOW được tái sử dụng tối đa 25 giây còn DENY tối đa 5 giây, với điều kiện cả hai tuân thủ version và nguồn dữ liệu của chính sách mẫu.

Giới hạn 5 giây cho DENY không tự chứng minh quyền mới xuất hiện trong 5 giây nếu nguồn cấp quyền hoặc chỉ mục còn chậm. Cam kết cấp quyền mới phải tính toàn bộ chuỗi tương tự thu hồi.

Không cache một timeout dưới dạng “người này không bao giờ có quyền”. Nếu cần giảm tải khi dependency lỗi, trạng thái lỗi và thời hạn phục hồi phải được quản lý riêng, không đánh đồng với quyết định chính sách.

### 8.2. Cache hỏng có thể đi theo đường đánh giá gốc

Nếu cache không khả dụng nhưng nguồn phân quyền gốc còn hoạt động, hệ thống có thể đánh giá trực tiếp với giới hạn tải phù hợp.

Cần phân biệt:

1. Cache miss bình thường.
2. Cache trả entry không hợp lệ.
3. Cache không đọc được.
4. Bộ đánh giá hoặc nguồn thuộc tính không khả dụng.
5. Không thể xác minh độ mới bắt buộc.

Ba trường hợp đầu có thể đi theo đường gốc nếu đường đó đáp ứng cùng hợp đồng an toàn. Hai trường hợp sau không được tự chuyển thành ALLOW.

### 8.3. Không kéo dài ALLOW vô hạn khi dependency lỗi

Cơ chế stale-while-revalidate cho phép dùng dữ liệu cũ trong lúc làm mới có thể phù hợp với một số dữ liệu thông thường. Với phân quyền, phải phân biệt:

- Mốc cần làm mới để giữ hiệu năng và giảm tuổi dữ liệu.
- Hạn an toàn cuối cùng `usableUntil`.

Có thể làm mới nền trong khoảng đã được chấp nhận, nhưng không dùng ALLOW sau hạn an toàn chỉ vì dependency đang lỗi. Nếu nghiệp vụ chấp nhận một cửa sổ cũ bổ sung, cửa sổ đó phải được đưa vào hợp đồng thu hồi ngay từ đầu, không phát sinh âm thầm trong sự cố.

Truy cập khẩn cấp, nếu có, cần danh tính, phạm vi, thời hạn và audit riêng. Nó không phải nhánh tự động “cache và PDP đều lỗi thì cho qua”.

PDP là Policy Decision Point, thành phần đánh giá chính sách. PEP là Policy Enforcement Point, thành phần thực thi kết quả như API, worker hoặc dịch vụ tải file.

### 8.4. Cache stampede không được làm mất kiểm soát

Khi nhiều entry cùng hết hạn, nhiều yêu cầu có thể đồng thời đánh giá lại và làm quá tải nguồn. Có thể dùng:

- Gộp yêu cầu trùng khóa trong một khoảng ngắn.
- Giới hạn số đánh giá đồng thời.
- Phân tán thời điểm làm mới trong phạm vi không vượt hạn an toàn.
- Làm mới sớm hoặc giới hạn tải có kiểm soát.

Nếu gộp yêu cầu, khóa gộp phải có cùng phạm vi bảo mật như quyết định. Không dùng một kết quả đang tính cho người A để trả người B chỉ vì cùng tài nguyên.

Hết thời gian chờ khóa hoặc không còn ngân sách đánh giá phải dẫn đến phản hồi có kiểm soát, không trở thành lý do bỏ kiểm tra quyền. Jitter chỉ được rút ngắn hoặc nằm trong giới hạn thời gian đã được cấp, không tự tăng hạn an toàn tối đa.

## 9. Bảo vệ cache khỏi giả mạo và đầu độc

Cache quyền có thể trở thành điểm cấp quyền nếu kẻ tấn công ghi được ALLOW hoặc làm sai khóa.

Yêu cầu bảo vệ nên bao gồm:

- Chỉ dịch vụ được ủy quyền được ghi loại entry tương ứng.
- Danh tính và quyền truy cập kho cache được giới hạn theo nhiệm vụ.
- Bảo vệ kênh truyền và dữ liệu lưu theo mức nhạy cảm.
- Tách namespace giữa môi trường, dịch vụ và phiên bản.
- Kiểm tra cấu trúc, version, hạn và nguồn entry.
- Không tin một entry chỉ vì đọc được từ mạng nội bộ.
- Không nhận cache key hoàn chỉnh hoặc nội dung entry do khách cung cấp như dữ liệu có thẩm quyền.
- Không để endpoint debug ghi/xóa/tải toàn bộ quyết định cho người không có quyền.

Tùy ranh giới tin cậy, có thể cần cơ chế kiểm chứng toàn vẹn như MAC hoặc chữ ký ngoài kiểm soát truy cập kho. Điều này không thay kiểm tra hạn, version hoặc thu hồi.

Entry bị hỏng hoặc không xác minh được có thể được bỏ và đi theo đường đánh giá gốc hợp lệ. Không “sửa” một entry thiếu điều kiện bằng cách giữ effect ALLOW rồi bỏ các trường không hiểu.

Cache miss, thời gian phản hồi và metric cũng có thể tiết lộ người dùng hoặc tài nguyên nào tồn tại. API công khai cần hạn chế tiết lộ và không đưa danh sách khóa vào thông báo lỗi.

## 10. Không bỏ sót cache phản hồi, file và luồng dài

### 10.1. Cache quyền và cache nội dung cần phối hợp

Một chuỗi nguy hiểm:

1. API kiểm tra quyền và tạo phản hồi chứa dữ liệu riêng tư.
2. Reverse proxy cache phản hồi theo URL.
3. Người khác gọi cùng URL.
4. Proxy trả nội dung mà không chạy lại kiểm tra quyền.

Ngay cả khi cache quyết định được thiết kế đúng, hệ thống vẫn lộ dữ liệu.

Đặc tả cần quy định endpoint nào được cache phản hồi, phạm vi chia sẻ và nơi thực thi quyền trên mỗi lần phục vụ. Nếu không có thiết kế cache dùng chung an toàn, phản hồi nhạy cảm phải có chỉ dẫn lưu trữ phù hợp và cấu hình proxy/CDN không tái sử dụng trái phạm vi.

Chỉ thêm một header hoặc đưa Authorization vào Vary không tự chứng minh toàn bộ luồng an toàn. Cần xét cấu hình thực tế, cookie, tenant, cơ chế chuẩn hóa khóa và quyền đã bị thu hồi.

### 10.2. Không cấp khả năng truy cập sống lâu hơn hợp đồng

Sau một cache hit ALLOW, API có thể cấp URL tải hoặc token tác vụ. Nếu mỗi lần như vậy lại cấp 1 giờ truy cập, entry chỉ còn hợp lệ 2 giây vẫn có thể tạo tác dụng kéo dài 1 giờ.

Yêu cầu phải giới hạn artifact được cấp theo hợp đồng riêng có kiểm tra thu hồi, hoặc theo thời hạn còn lại phù hợp của bằng chứng đã dùng. Không để một quyết định ngắn hạn tạo ra khả năng truy cập dài hạn không được kiểm soát.

Tương tự, tác vụ nền phải kiểm tra lại quyền tại các điểm đã quy định, không coi ALLOW khi xếp hàng là giấy phép vĩnh viễn cho toàn bộ quá trình.

### 10.3. Định nghĩa phạm vi thu hồi cho streaming

Với WebSocket, tải file dài hoặc stream sự kiện, cần nói rõ:

- Chỉ kiểm tra khi mở kết nối hay kiểm tra lại định kỳ.
- Thu hồi có làm ngừng gửi dữ liệu mới không.
- Khoảng tối đa từ thu hồi đến lần kiểm tra hoặc ngắt.
- Cách phân quyền từng kênh, tài nguyên hoặc thông điệp.
- Điều gì xảy ra khi dependency không đáp ứng độ mới.

Hệ thống không thể lấy lại dữ liệu đã được gửi và lưu ở thiết bị người dùng. Cam kết thu hồi cần tập trung vào khả năng tiếp tục truy cập hoặc nhận dữ liệu mới, với điểm bắt đầu và giới hạn đo rõ ràng.

## 11. Minh họa luồng thực thi có cache

Đoạn mã giả dưới đây dùng cho một API đọc được phép cache theo chính sách. Nó minh họa các điều kiện, không cung cấp một triển khai nhất quán phân tán hoàn chỉnh.

```text
function authorizeAndRead(request):
    identity = authenticateAndValidateSession(request)
    if identity is absent:
        return authenticationRequired()

    context = buildTrustedAuthorizationContext(identity, request)
    metadata = loadResourceMetadataWithinTrustedScope(context, request)
    if metadata is absent:
        return responseWithoutUnnecessaryExistenceDisclosure()

    requirements = loadActionRequirements(context.action)
    currentBounds = resolveRequiredVersionsAndFreshness(
        identity, metadata, requirements
    )
    if currentBounds cannot be established:
        return controlledServiceFailure()

    cacheKey = canonicalKey(
        identity,
        context,
        metadata.typedResourceId,
        currentBounds
    )

    entry = tryReadCache(cacheKey)
    if not isReusable(entry, context, currentBounds, serverNow()):
        result = evaluateWithSufficientlyFreshInputs(
            identity, context, metadata, currentBounds
        )

        if result is INDETERMINATE:
            return controlledServiceFailure()

        entry = deriveBoundedEntry(result, requirements)
        # Phải ngăn kết quả của thế hệ cũ ghi đè sau invalidation.
        publishOnlyUnderValidGeneration(cacheKey, entry, currentBounds)

        if not isReusable(entry, context, currentBounds, serverNow()):
            return retryOrFailWithinBudget()

    if entry.effect != ALLOW:
        return policyResponse(entry)

    if not canEnforceAll(entry.obligations):
        return controlledServiceFailure()

    enforcePerUseObligations(entry, identity, metadata)
    return readDataConsistentWithAuthorization(metadata, entry)
```

Các hàm về version, freshness và generation phải có hợp đồng thực sự. Một lần CAS trên cache cục bộ không tự ngăn được việc nguồn đã thu hồi nhưng sự kiện chưa đến. Khi không có kiểm tra tức thời, giới hạn độ trễ đó phải nằm trong ngân sách được chấp nhận.

Quyền phải còn phù hợp ở điểm thực thi dữ liệu. Nếu metadata hoặc điều kiện nhạy cảm thay đổi sau kiểm tra, cần kiểm tra phiên bản hoặc đánh giá lại theo thiết kế. Không dùng mã giả để suy ra rằng kiểm tra rồi đọc ở bất kỳ khoảng cách thời gian nào cũng an toàn.

## 12. Bộ yêu cầu mẫu có thể nghiệm thu

Bộ dưới đây dành cho nền tảng tài liệu giả định. TTL và ngưỡng đo là ví dụ cần điều chỉnh theo rủi ro, kiến trúc và tải thực tế.

| ID | Yêu cầu | Tiêu chí kiểm chứng |
|---|---|---|
| AC-01 | Quyết định chỉ được dùng lại cho cùng chủ thể, tenant, hành động, kiểu/ID tài nguyên và ngữ cảnh ảnh hưởng quyền | Cùng user/resource nhưng khác tenant, action hoặc người được đại diện không dùng nhầm entry |
| AC-02 | Mọi đầu vào quyết định phải có nguồn tin cậy; version từ khách hoặc token cũ không tự đại diện trạng thái hiện hành | Sửa role, tenant, auth_time hoặc revision tự khai không tạo quyền |
| AC-03 | ALLOW của nhóm API đọc mẫu được tái sử dụng tối đa 25 giây từ đánh giá và không vượt hạn của các điều kiện phụ thuộc | MFA chỉ còn 10 giây độ mới thì entry không dùng được sau 10 giây |
| AC-04 | Tại thời điểm bằng usableUntil, entry không được tái sử dụng; copy giữa L2/L1 không kéo dài hạn | Hit liên tục, copy qua tầng hoặc restart không làm trẻ quyết định |
| AC-05 | Quan hệ thu hồi không tiếp tục tạo quyền sau tối đa 60 giây từ khi nguồn có thẩm quyền ghi nhận thành công | Đo toàn chuỗi gồm nguồn cũ, cache, replica, worker, file và điểm thực thi |
| AC-06 | Invalidation phải xử lý được sự kiện trùng/sai thứ tự và có cơ chế phục hồi khi mất sự kiện | Revision 12 rồi 11 không đưa trạng thái về cũ; mất sự kiện không vượt thời hạn thu hồi |
| AC-07 | Kết quả đánh giá đang chạy bằng thế hệ cũ không được làm sống lại quyền quá hợp đồng sau invalidation | Tạm dừng evaluator trước ghi cache, thu hồi, rồi cho ghi tiếp vẫn không vượt cam kết |
| AC-08 | Entry sai cấu trúc, nguồn, toàn vẹn, policy version hoặc nghĩa vụ không được dùng như ALLOW | Chèn entry lỗi hoặc policy cũ không trả dữ liệu nhạy cảm |
| AC-09 | Cache không khả dụng được đi đường đánh giá gốc khi đường đó đáp ứng cùng yêu cầu; thiếu nguồn đủ mới thì không cấp quyền | Tắt cache còn PDP tốt vẫn xử lý hợp lệ; PDP/nguồn lỗi không cho qua |
| AC-10 | Không dùng ALLOW sau hạn an toàn khi làm mới nền hoặc dependency lỗi | stale-while-revalidate và chế độ sự cố không kéo dài usableUntil |
| AC-11 | Nghĩa vụ ghi audit, lọc trường và kiểm tra phạm vi phải được thực hiện trên mọi cache hit | Hai lần dùng cùng ALLOW đều có audit cần thiết và chỉ nhận trường được phép |
| AC-12 | Quota, xác nhận hoặc quyền dùng một lần phải được tiêu thụ nguyên tử riêng, không được tái sử dụng từ cache | Hai yêu cầu cùng hit không cùng dùng được một lượt còn lại |
| AC-13 | DENY của nhóm API mẫu được tái sử dụng tối đa 5 giây; timeout không được lưu như DENY nghiệp vụ bền vững | Quyền mới được đánh giá lại theo hợp đồng; sự cố không tạo từ chối kéo dài ngoài chính sách |
| AC-14 | Tác vụ cấp quyền quản trị mẫu không dùng ALLOW giữa các yêu cầu và phải kiểm tra điều kiện hiện hành tại điểm ghi | Quyền nguồn bị thay trước commit không bị bỏ qua do cache |
| AC-15 | Phản hồi, URL tải, token tác vụ và stream không được vượt hợp đồng truy cập chỉ vì đã có cache hit | Nội dung/đường tải không tiếp tục dùng quyền cũ ngoài giới hạn đã quy định |
| AC-16 | Metrics/log phải phân biệt hit hợp lệ, entry cũ, invalidation, lỗi và không ghi token hoặc dữ liệu nhạy cảm ngoài chính sách | Điều tra được một quyết định cũ được dùng ở đâu mà không cần lộ bí mật |
| AC-17 | Gộp yêu cầu và giới hạn tải không được trộn chủ thể/ngữ cảnh hoặc bỏ kiểm tra khi hết ngân sách | Stampede, timeout khóa và quá tải không tạo ALLOW ngoài quyền |

AC-05 đo việc ngừng sử dụng nguồn quyền bị thu hồi. Nếu người dùng còn đường cấp quyền khác hợp lệ, họ có thể vẫn được phép. Muốn nghiệm thu “mất mọi quyền”, dữ liệu kiểm thử phải loại bỏ các đường còn lại hoặc áp dụng lệnh chặn theo chính sách.

AC-13 không cam kết quyền mới xuất hiện sau đúng 5 giây chỉ từ TTL DENY. Cần thêm giới hạn độ trễ cấp quyền từ nguồn đến nơi thực thi nếu sản phẩm có cam kết đó.

AC-14 cũng yêu cầu xem xét cache thuộc tính và tính đồng thời, không chỉ tắt một lời gọi cache quyết định.

## 13. Truy vết rủi ro với kiến trúc và kiểm thử

| Rủi ro | Yêu cầu chính | Thành phần thực thi | Kiểm thử đại diện |
|---|---|---|---|
| Dùng nhầm quyền của người/tenant khác | AC-01, AC-02 | Tạo context, chuẩn hóa khóa, PEP | Đổi tenant/action/subject với cùng ID tài nguyên |
| Quyền cũ tồn tại quá lâu | AC-03, AC-04, AC-05 | Nguồn thuộc tính, L1/L2, TTL | Thu hồi ngay sau khi cache được nạp, đọc sát ranh giới |
| Sự kiện thu hồi không đến | AC-05, AC-06 | Outbox, consumer, phục hồi version | Mất kết nối, mất/trùng/sai thứ tự sự kiện |
| Đánh giá cũ ghi sau invalidation | AC-07 | Evaluator, publication, generation | Điều khiển thứ tự đọc–thu hồi–ghi cache |
| Entry bị giả hoặc đầu độc | AC-08 | Kho cache, kiểm chứng entry | Chèn ALLOW giả, sai schema hoặc policy |
| Sự cố trở thành đường vượt quyền | AC-09, AC-10 | Fallback, circuit/load control | Tắt cache/PDP/nguồn và thử entry đã quá hạn |
| Bỏ nghĩa vụ khi hit | AC-11, AC-12 | PEP, audit, kiểm soát quota | Cache hit lặp lại và yêu cầu đồng thời |
| Gián đoạn do DENY cũ | AC-13 | Negative cache, cấp quyền | Cấp quyền sau DENY và đo thời gian phục hồi |
| Hành động nhạy cảm dùng quyền cũ | AC-14 | Dịch vụ quản trị, điểm commit | Đổi quyền cạnh tranh với thao tác ghi |
| Nội dung/file bypass cache quyền | AC-15 | Proxy/CDN, file, worker, stream | Quyền mất nhưng URL/kết nối vẫn tồn tại |
| Không điều tra được độ cũ | AC-16 | Logging, metrics, version trace | Truy một quyết định qua nguồn và các tầng |
| Quá tải làm mất ranh giới | AC-17 | Gộp yêu cầu, giới hạn đánh giá | Nhiều người dùng gọi cùng tài nguyên khi cache lạnh |

Ma trận cho thấy tối ưu cache liên quan nhiều thành phần ngoài kho cache. Một yêu cầu không có điểm thực thi hoặc một tầng chưa được đo là khoảng trống cần làm rõ trước nghiệm thu.

## 14. Kế hoạch kiểm thử có chủ đích

### 14.1. Chuẩn bị dữ liệu và khả năng điều khiển thời gian

Một bộ dữ liệu hữu ích gồm:

- Hai tenant có tài nguyên trùng ID cục bộ.
- Hai người dùng cùng role nhưng khác quyền đối tượng.
- Một người có nhiều đường được cấp quyền.
- Một dịch vụ thực hiện thay hai người dùng khác nhau.
- Chính sách có read, edit, export và điều kiện MFA gần đây.
- L1, L2 và một nguồn thuộc tính có thể tạo độ trễ.
- Một tác vụ chờ, một file tải và một stream đang mở.
- Khả năng chủ động trì hoãn evaluator, consumer và dependency.

Kiểm thử thời gian nên dùng mốc có kiểm soát khi có thể. Chỉ chờ ngẫu nhiên vài giây rồi thử lại thường không chứng minh được hành vi ranh giới hoặc cuộc đua.

### 14.2. Các tình huống cần bao phủ

| Tình huống | Cách kiểm thử | Kết quả mong đợi |
|---|---|---|
| Hit hợp lệ | Lặp cùng yêu cầu trong hạn, không đổi điều kiện | Có thể dùng cache nhưng vẫn thực hiện nghĩa vụ |
| Khác hành động | Dùng cache read rồi gọi edit/export | Không dùng nhầm ALLOW |
| Khác tenant/chủ thể | Giữ resource ID, đổi người hoặc tenant | Không rò dữ liệu giữa phạm vi |
| Khác ủy quyền | Dịch vụ gọi thay A rồi thay B | Quyền của A không chuyển cho B |
| Hạn chứng thực gần hết | MFA còn 10 giây, TTL chung 25 giây | Entry chỉ dùng trong giới hạn MFA |
| Đúng lúc hết hạn | Gọi ngay trước, đúng và sau usableUntil | Tại hạn không tái sử dụng entry |
| Sao chép cache | Nạp L1 từ L2 ngay trước hạn | Hạn gốc không được kéo dài |
| Sliding expiration | Hit liên tục sau thu hồi | Không duy trì ALLOW vô hạn |
| Nguồn cũ | Xóa decision cache nhưng giữ membership cũ | Không vượt ngân sách độ cũ đã đặc tả |
| Thu hồi nhiều đường | Xóa một quan hệ rồi xóa toàn bộ nguồn quyền | Phân biệt quyền còn hợp lệ và quyền đã hết |
| Mất invalidation | Chặn sự kiện đến một nút | Nút đó vẫn dừng dùng quyền cũ trước giới hạn |
| Sai thứ tự | Gửi revision mới rồi cũ | Không lùi trạng thái/version |
| Ghi kết quả muộn | Giữ evaluator cũ, thu hồi, xử lý invalidation rồi cho ghi tiếp | Không làm sống lại quyền ngoài hợp đồng |
| Giả version | Gửi revision cũ/mới tùy ý từ khách | Không làm giảm mốc bắt buộc hoặc tạo quyền |
| Cache lỗi | Làm kho cache timeout | Chỉ fallback sang đường gốc an toàn |
| Nguồn lỗi | Cho entry quá hạn rồi tắt nguồn | Không dùng lại ALLOW quá hạn |
| Nghĩa vụ | Hai cache hit cho cùng hành động có audit/filter | Cả hai đều được ghi nhận/lọc đúng |
| Quyền một lần | Hai yêu cầu đồng thời cùng hit ALLOW | Chỉ một lần tiêu thụ được phép |
| Stampede | Nhiều yêu cầu cùng hết hạn | Không trộn context và không bỏ quyền khi quá tải |
| Cache phản hồi | A mở URL rồi B mở cùng URL | B không nhận nội dung riêng của A |
| Artifact dài hạn | Cấp URL khi ALLOW sắp hết | URL không phá cam kết thu hồi |
| Stream/tác vụ | Thu hồi khi đang mở hoặc chờ thực thi | Dừng cấp dữ liệu mới theo mốc đã quy định |
| Restart/đồng hồ | Khởi động lại hoặc điều chỉnh thời gian có kiểm soát | Không gia hạn quyết định ngoài chính sách |

### 14.3. Bằng chứng nghiệm thu

Cần đối chiếu:

- Thời điểm nguồn chấp nhận thay đổi.
- Version hoặc revision trước/sau.
- Thời điểm đánh giá và nguồn dữ liệu đã dùng.
- usableUntil ban đầu và sau khi copy.
- Cache layer, hit/miss và lý do bỏ entry.
- Quyết định tại PEP và tác dụng dữ liệu thực sự.
- Điểm cuối cùng còn sử dụng quyền cũ.
- Audit và trạng thái token/file/tác vụ liên quan.

Không chỉ dựa vào tỷ lệ hit cao hoặc vài phản hồi 403. Phải chứng minh không có nội dung, thông điệp, file hoặc tác dụng ghi trái phép được tạo ra sau giới hạn.

## 15. Quan sát vận hành và quản lý thay đổi

### 15.1. Sự kiện cần phân biệt

```text
authz.cache.valid_hit
authz.cache.miss
authz.cache.expired
authz.cache.version_mismatch
authz.cache.integrity_failure
authz.cache.invalidation_received
authz.cache.invalidation_lag
authz.cache.old_generation_rejected
authz.cache.fallback_evaluation
authz.evaluation.indeterminate
```

Có thể lấy mẫu các sự kiện lưu lượng lớn theo chính sách, nhưng audit bắt buộc của hành động nhạy cảm không được biến mất chỉ vì lấy mẫu cache log.

Trường hữu ích gồm định danh tương quan, tầng cache, hành động, policy version, revision, tuổi entry, hạn và reason code. Không ghi raw token, toàn bộ thuộc tính nhạy cảm hoặc payload tài liệu. Nhãn metric không nên chứa từng user ID/resource ID nếu làm lộ dữ liệu hoặc tạo số lượng chuỗi đo không kiểm soát.

### 15.2. Chỉ số cần có định nghĩa

| Chỉ số | Định nghĩa mẫu | Cách diễn giải |
|---|---|---|
| Tỷ lệ hit hợp lệ | Số lần tái sử dụng entry đạt mọi điều kiện / tổng số yêu cầu thuộc nhóm được cache | Khác tỷ lệ đọc thấy key trong kho |
| Tuổi quyết định khi dùng | Thời điểm sử dụng trừ evaluatedAt, theo quy tắc thời gian đã định | Không thay thế tuổi của dữ liệu nguồn |
| Độ trễ invalidation | Từ nguồn ghi nhận đến consumer áp dụng | Cần theo từng tầng/vùng quan trọng |
| Độ trễ thu hồi thực tế | Từ nguồn ghi nhận đến mọi PEP trong phạm vi ngừng dùng nguồn quyền cũ | Đo kết quả bảo mật, không chỉ đường sự kiện |
| Kết quả cũ bị chặn | Số lần từ chối publication/use vì generation cũ | Phát hiện cuộc đua và độ trễ evaluator |
| Tỷ lệ fallback | Yêu cầu đi đường đánh giá gốc do cache lỗi / tổng yêu cầu tương ứng | Theo dõi tải và khả năng phục hồi |
| Tỷ lệ chưa xác định | INDETERMINATE / tổng đánh giá | Phân biệt với DENY hợp lệ |
| Vi phạm hạn an toàn | Số lần tái sử dụng sau usableUntil | Mục tiêu của chính sách mẫu là 0 |

Ví dụ yêu cầu hiệu năng có thể là p95 kiểm tra quyền từ PEP không quá 40 ms dưới tải 300 yêu cầu/giây trong môi trường, kích thước dữ liệu và tỷ lệ cache hit được mô tả. Đo thêm cache lạnh và dependency chậm để hiểu đường fallback.

Tỷ lệ hit thấp có thể là tối ưu hóa chưa hiệu quả, nhưng tỷ lệ hit quá cao cũng không chứng minh an toàn: khóa quá rộng hoặc entry được kéo dài sai cũng có thể tạo số đo đẹp.

### 15.3. Thay đổi TTL, khóa hoặc policy là thay đổi bảo mật

Khi thay TTL, cần tính lại ngân sách thu hồi. Khi đổi khóa, phải xem có entry cũ bị dùng dưới nghĩa mới không. Khi đổi policy hoặc schema entry, cần version và kế hoạch loại bỏ dữ liệu không tương thích.

Quay lại phiên bản phần mềm không được làm sống lại cache hoặc quyền đã thu hồi. Thao tác rollback cần giữ nguyên các ràng buộc về trạng thái quyền hiện hành, không chỉ đưa ứng dụng về một bản chạy được.

## 16. Những đặc tả cần làm rõ

| Cách viết chưa đủ | Khoảng trống | Cách viết cụ thể hơn |
|---|---|---|
| “Cache quyền 1 phút” | Không rõ nguồn cũ, tầng cache và thời điểm tính | Nêu đối tượng cache, evaluatedAt, hạn, độ mới nguồn và ngân sách thu hồi |
| “Key theo user và role” | Bỏ tài nguyên, hành động, tenant và ngữ cảnh | Liệt kê đầu vào ảnh hưởng quyết định và cách chuẩn hóa |
| “Có sự kiện là thu hồi ngay” | Sự kiện có thể mất, chậm hoặc bị ghi đè bởi evaluator cũ | Nêu độ trễ, phục hồi, fencing và TTL dự phòng |
| “Cache hit thì bỏ qua kiểm tra” | Bỏ phiên, nghĩa vụ và thời hạn động | Nêu điều kiện entry được tái sử dụng và việc vẫn phải làm mỗi lần |
| “PDP lỗi thì dùng kết quả gần nhất” | Không có giới hạn cũ cuối cùng | Chỉ dùng trong usableUntil đã được chấp nhận |
| “Xóa cache là xong” | Nguồn thuộc tính, phản hồi và URL vẫn có thể cũ | Theo toàn bộ đường quyết định và cung cấp dữ liệu |
| “Version trong JWT là version hiện tại” | Token chỉ phản ánh thời điểm phát hành | Có cách đối chiếu nguồn đủ mới hoặc giới hạn độ cũ rõ |
| “Hit rate đạt 95% nên an toàn” | Chỉ là chỉ số hiệu năng | Nghiệm thu khóa, thu hồi, nghĩa vụ và tác dụng thực tế |

## 17. Bài tập áp dụng

Một dịch vụ lưu ALLOW trong Redis 5 phút và sao chép vào cache cục bộ thêm 5 phút từ mỗi lần đọc. Bộ đánh giá lấy membership từ một cache riêng có TTL 10 phút. Khi người dùng rời nhóm, hệ thống gửi một sự kiện xóa key theo user ID. API tải file cấp URL có hiệu lực 1 giờ. Sản phẩm yêu cầu quyền bị thu hồi trong 60 giây.

Hãy tạo đặc tả cải tiến:

1. Liệt kê mọi nơi có thể giữ hoặc tạo lại quyền cũ.
2. Xác định khóa quyết định và đầu vào tin cậy cần thiết.
3. Phân bổ ngân sách độ cũ từ nguồn đến điểm thực thi.
4. Quy định usableUntil và cách copy giữa các tầng.
5. Thiết kế yêu cầu chống kết quả cũ ghi lại sau invalidation.
6. Nêu hành vi khi cache lỗi, membership lỗi và mất sự kiện.
7. Liên kết URL tải, worker và stream với cùng cam kết thu hồi.
8. Viết các ca kiểm thử ranh giới, cuộc đua, khác tenant và nghĩa vụ trên cache hit.
9. Lập ma trận rủi ro, ID yêu cầu, nơi thực thi và bằng chứng nghiệm thu.

Một phương án đạt yêu cầu phải chứng minh thời hạn 60 giây cho toàn bộ đường truy cập. Chỉ giảm TTL Redis xuống 60 giây chưa đủ khi membership, cache cục bộ hoặc URL tải vẫn giữ khả năng truy cập lâu hơn.
