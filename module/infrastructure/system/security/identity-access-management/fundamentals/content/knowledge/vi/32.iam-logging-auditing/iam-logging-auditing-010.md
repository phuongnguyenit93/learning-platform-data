# Token revocation: ghi log và kiểm toán việc thu hồi token

## 1. Audit cần chứng minh điều gì đã bị thu hồi

**Token revocation** là việc kết thúc khả năng sử dụng một token hoặc một phạm vi cấp quyền liên quan theo cơ chế của hệ thống, có thể trước thời hạn vốn có của token.

Trong logging và audit IAM, câu hỏi không chỉ là “đã gọi API thu hồi chưa?”. Cần xác định:

- Ai yêu cầu và ai thực hiện?
- Token, chuỗi token, phiên hoặc quyền cấp phát nào thuộc phạm vi?
- Trạng thái thu hồi đã được lưu ở thành phần có thẩm quyền chưa?
- Các điểm xác minh nào cần nhận thay đổi?
- Khi nào việc sử dụng tiếp theo thực sự bị từ chối?
- Còn phạm vi nào chưa được xử lý hoặc chưa đủ bằng chứng?

Ví dụ, tài khoản Lan bị nghi ngờ đã lộ thông tin truy cập. Hệ thống ngừng cho sử dụng refresh token của Lan để cấp access token mới. Nếu access token đã cấp vẫn được API chấp nhận, audit không nên ghi “mọi truy cập của Lan đã bị thu hồi”.

Một dấu vết tốt mô tả đúng phạm vi và giới hạn của bằng chứng. Nó không biến việc tiếp nhận một yêu cầu thành khẳng định rằng mọi dịch vụ đã chặn mọi token.

## 2. Phân biệt token, phiên và quyền cấp phát

| Đối tượng | Vai trò | Điều cần xác định khi audit thu hồi |
| --- | --- | --- |
| Access token | Được trình cho dịch vụ để truy cập tài nguyên | Dịch vụ nhận có kiểm tra trạng thái thu hồi hoặc cơ chế hiệu lực nào? |
| Refresh token | Dùng để yêu cầu token mới theo thiết kế | Token hoặc chuỗi refresh token nào không còn được sử dụng? |
| Authorization grant hoặc quyền ủy nhiệm | Căn cứ cho một phạm vi cấp token hoặc truy cập | Thu hồi grant ảnh hưởng những token và lần cấp mới nào? |
| Phiên tại nhà cung cấp danh tính | Duy trì ngữ cảnh đăng nhập tại nguồn danh tính | Có kết thúc phiên này và ngăn lần đăng nhập tiếp theo không? |
| Phiên tại ứng dụng | Duy trì trạng thái truy cập riêng của ứng dụng | Ứng dụng có nhận và áp dụng yêu cầu kết thúc phiên không? |

Một ứng dụng xóa cookie trên trình duyệt chưa chắc đã thu hồi token ở server. Ngược lại, thu hồi một refresh token không nhất thiết kết thúc mọi phiên ứng dụng đang tồn tại.

Nếu hệ thống có token phục vụ mục đích khác, như xác nhận đăng nhập, phải ghi rõ loại và mục đích. Không gom tất cả thành một loại access token hoặc giả định mọi loại token đều được xử lý bằng cùng một cơ chế.

Các quan hệ giữa token, grant và phiên cần được quản lý ở nguồn có thẩm quyền. Không nên suy ra quan hệ chỉ từ email hoặc một đoạn nội dung token chưa được xác minh.

## 3. Vòng đời audit của một yêu cầu thu hồi

Một chuỗi mốc minh họa:

```text
Tiếp nhận yêu cầu
    -> xác minh thẩm quyền và phạm vi
    -> ghi trạng thái thu hồi bền vững
    -> phát thay đổi đến các thành phần liên quan
    -> cập nhật cache hoặc trạng thái xác minh
    -> quan sát và xác nhận theo phạm vi đã định
```

Có thể định nghĩa các sự kiện sau:

| Sự kiện minh họa | Bằng chứng sự kiện cung cấp |
| --- | --- |
| `TOKEN_REVOCATION_REQUESTED` | Một yêu cầu thu hồi đã được tiếp nhận |
| `TOKEN_REVOCATION_DENIED` | Bên gọi không được thực hiện phạm vi yêu cầu |
| `TOKEN_REVOCATION_STATE_COMMITTED` | Nguồn trạng thái có thẩm quyền đã lưu thay đổi |
| `TOKEN_REVOCATION_PROPAGATION_STARTED` | Thay đổi đang được chuyển đến những nơi cần áp dụng |
| `TOKEN_REVOCATION_ENFORCEMENT_RESULT` | Một điểm thực thi báo kết quả áp dụng trong phạm vi cụ thể |
| `TOKEN_REVOCATION_PARTIAL` | Chưa hoàn tất một phần phạm vi bắt buộc |
| `REVOKED_TOKEN_USE_DETECTED` | Có lần sử dụng token mà hệ thống xác định đã bị thu hồi |
| `TOKEN_REVOCATION_FAILED` | Một bước cần thiết thất bại theo định nghĩa của quy trình |

Tên sự kiện là lựa chọn thiết kế, không phải schema bắt buộc.

Nếu một hệ thống chỉ kiểm soát được việc cấp token mới, trạng thái thành công của nó phải mang ý nghĩa tương ứng. Muốn tuyên bố đã chặn tại các resource server, cần biết tập resource server thuộc phạm vi và có bằng chứng phù hợp từ các nơi đó.

## 4. Ghi đúng actor và tài khoản bị tác động

### 4.1. Người dùng tự thu hồi

Lan có thể tự đăng xuất khỏi một thiết bị hoặc ngắt một tích hợp đã cấp quyền. Audit cần ghi danh tính Lan đã được xác minh và phạm vi mà Lan được phép thu hồi.

Quyền thu hồi một token của mình không tự cho phép thu hồi token của người khác hoặc mọi token trong tenant.

### 4.2. Quản trị viên hoặc đội ứng phó sự cố

Nếu Minh thu hồi quyền truy cập của Lan, cần phân biệt:

```text
actor = security-operator-minh
targetSubject = user-lan
operation = revoke-access
scope = phạm vi đã được cho phép
reasonReference = incident-128
```

Không ghi actor thành Lan chỉ vì token thuộc tài khoản Lan.

Nếu công cụ quản trị gọi một dịch vụ nội bộ để thực hiện, có thể cần giữ cả người vận hành thật và danh tính workload thực thi. Điều này giúp phân biệt ai ra quyết định với thành phần nào đã thay đổi trạng thái.

### 4.3. Tự động thu hồi

Một chính sách có thể tự thu hồi khi phát hiện dùng lại refresh token, khi tài khoản bị khóa hoặc khi có thay đổi quyền.

Audit nên ghi nguồn quyết định, phiên bản chính sách và sự kiện kích hoạt. Một cảnh báo rủi ro không tự chứng minh tài khoản đã bị chiếm; bản ghi cần giữ đúng lý do được hệ thống sử dụng.

### 4.4. Đầu vào chưa được xác minh

Một request chứa một token bất kỳ không đủ để kết luận người gửi là chủ token hoặc target được khai báo là chính xác.

Cần ghi trạng thái xác thực của bên gọi và chỉ xác lập tài khoản đích sau khi đối chiếu qua nguồn đáng tin cậy. Không dùng payload token chưa xác minh để ghi một kết quả thu hồi thành công cho một người dùng.

## 5. Schema giúp liên kết yêu cầu với kết quả thực tế

Các trường có thể gồm:

| Trường | Ý nghĩa |
| --- | --- |
| `eventId` | Định danh riêng của một sự kiện |
| `schemaVersion`, `eventType` | Ý nghĩa và phiên bản cấu trúc |
| `occurredAt`, `recordedAt` | Thời điểm phát sinh và thời điểm thu thập |
| `revocationOperationId` | Liên kết toàn bộ lần thu hồi |
| `requestId`, `correlationId` | Theo dõi xử lý kỹ thuật |
| `actor`, `targetSubject` | Người thực hiện thật và chủ thể bị tác động |
| `tenantId`, `environment` | Phạm vi tổ chức và môi trường |
| `tokenType`, `tokenReference` | Loại và tham chiếu không mang khả năng sử dụng token |
| `grantReference`, `sessionReference` | Quan hệ liên quan khi đã xác định hợp lệ |
| `requestedScope`, `appliedScope` | Phạm vi được yêu cầu và phạm vi đã xử lý |
| `stateVersion` | Phiên bản thay đổi để đối chiếu áp dụng |
| `result`, `reasonCode` | Kết quả và lý do có cấu trúc |
| `enforcementPoint` | Nơi áp dụng hoặc xác minh việc chặn |

`tokenReference` cần là tham chiếu phục vụ quản lý, không phải chuỗi bearer token có thể sử dụng để truy cập. Nếu dùng một cơ chế tạo giá trị đối chiếu từ token, phải xem xét tính nhạy cảm, khả năng liên kết và quyền sử dụng của giá trị đó. Không mặc định mọi giá trị băm đều phù hợp để ghi log rộng rãi.

Một session reference trong audit cũng không nên là cookie phiên hoặc bí mật đăng nhập.

## 6. Ví dụ: thu hồi refresh token chưa đồng nghĩa chặn mọi access token

### 6.1. Nguồn cấp token đã lưu trạng thái thu hồi

Ví dụ minh họa với dữ liệu giả:

```json
{
  "eventId": "evt-revoke-201",
  "schemaVersion": 1,
  "eventType": "TOKEN_REVOCATION_STATE_COMMITTED",
  "revocationOperationId": "revoke-op-81",
  "service": "token-service",
  "environment": "production",
  "tenantId": "tenant-an-binh",
  "actor": {
    "type": "user",
    "id": "security-operator-minh"
  },
  "targetSubject": {
    "type": "user",
    "id": "user-lan"
  },
  "tokenType": "refresh_token",
  "grantReference": "grant-ref-712",
  "appliedScope": "refresh-token-family",
  "stateVersion": 18,
  "result": "COMMITTED",
  "reasonCode": "INCIDENT_RESPONSE",
  "reasonReference": "incident-128"
}
```

Sự kiện nói rằng trạng thái thu hồi chuỗi refresh token đã được lưu tại token service theo thiết kế. Nó không nói rằng mọi access token đã cấp hoặc mọi phiên ứng dụng đều không còn dùng được.

Nếu thuật ngữ “family” được dùng, hệ thống phải định nghĩa chính xác những token nào thuộc chuỗi đó và nguồn dữ liệu xác định quan hệ.

### 6.2. Một API xác nhận đã áp dụng thay đổi

```json
{
  "eventId": "evt-revoke-208",
  "schemaVersion": 1,
  "eventType": "TOKEN_REVOCATION_ENFORCEMENT_RESULT",
  "revocationOperationId": "revoke-op-81",
  "service": "contract-api",
  "environment": "production",
  "tenantId": "tenant-an-binh",
  "targetSubject": {
    "type": "user",
    "id": "user-lan"
  },
  "appliedScope": "configured-grant-access-checks",
  "stateVersion": 18,
  "enforcementPoint": "contract-api-authorization",
  "result": "APPLIED"
}
```

Ví dụ giả định API có cơ chế kiểm tra trạng thái grant và đã áp dụng phiên bản tương ứng. Kết quả này chỉ có giá trị trong phạm vi được khai báo.

Không suy ra dịch vụ báo cáo, ứng dụng ngoài hoặc kết nối đang mở cũng đã cập nhật nếu chưa có bằng chứng về những nơi đó.

## 7. Hiểu các cơ chế thu hồi để không ghi sai kết luận

### 7.1. Token tham chiếu hoặc kiểm tra trạng thái trực tuyến

Khi bên nhận truy vấn trạng thái có thẩm quyền, việc thu hồi có thể được phản ánh ở các lần kiểm tra tiếp theo.

Tuy nhiên, cache kết quả, lỗi phụ thuộc hoặc một đường truy cập không kiểm tra trạng thái có thể làm hành vi thực tế khác với thời điểm ghi ở nguồn.

Audit cần biết điểm nào kiểm tra, có giới hạn độ mới nào và khi nào thay đổi đã được áp dụng.

### 7.2. Token tự chứa được xác minh cục bộ

Một token tự chứa có thể vẫn hợp lệ về chữ ký và thời hạn dù tài khoản hoặc grant liên quan đã bị thu hồi ở nguồn.

Muốn chặn trước khi token hết hiệu lực tự nhiên, hệ thống có thể cần cơ chế bổ sung như trạng thái thu hồi, phiên bản quyền hoặc sự kiện cập nhật tại bên nhận. Chi tiết phụ thuộc thiết kế.

Việc ghi token vào một danh sách thu hồi không có tác dụng với một API chưa từng kiểm tra danh sách đó.

### 7.3. Refresh token và lần cấp tiếp theo

Thu hồi refresh token thường hướng đến việc ngăn sử dụng nó trong các lần yêu cầu token mới theo cơ chế hệ thống.

Những access token đã cấp cần được xét riêng. Audit nên thể hiện rõ “ngăn cấp mới bằng credential này” và “chặn token đã phát hành” là hai phạm vi cần bằng chứng khác nhau.

### 7.4. Khóa ký và phạm vi ảnh hưởng lớn

Nếu xử lý sự cố liên quan khóa ký, việc ngừng tin khóa có thể tác động đến nhiều token và nhiều chủ thể.

Thay khóa để ký token mới không tự làm bên nhận từ chối mọi token dưới khóa cũ. Cần theo dõi tập khóa được chấp nhận, cache tại bên nhận và phạm vi loại bỏ niềm tin.

Audit không được ghi “token đã thu hồi toàn bộ” chỉ vì một khóa mới đã được tạo.

## 8. Phân biệt thời điểm ghi nhận và thời điểm có hiệu lực

Một lần thu hồi phân tán có thể có nhiều mốc:

```text
T1: nguồn quản lý nhận yêu cầu
T2: trạng thái thu hồi được commit
T3: sự kiện được phát đi
T4: điểm thực thi A áp dụng
T5: điểm thực thi B áp dụng
T6: quan sát một lần sử dụng tiếp theo bị từ chối
```

T2 không nhất thiết bằng T4 hoặc T5. T6 chứng minh một lần kiểm tra cụ thể đã từ chối, không tự chứng minh mọi đường truy cập đều an toàn.

Các trường thời gian cần có ý nghĩa rõ ràng. Nếu ghi `effectiveAt`, phải định nghĩa nó nói về nguồn trạng thái hay một điểm thực thi. Với nhiều điểm, có thể cần kết quả từng nơi thay vì một dấu thời gian toàn cục thiếu căn cứ.

Đồng hồ và độ trễ truyền có thể ảnh hưởng việc so sánh. Khi cần xác nhận cùng một thay đổi đã được áp dụng, định danh thao tác và phiên bản trạng thái thường hữu ích hơn chỉ so chuỗi thời gian.

Có thể đo độ trễ từ commit đến xác nhận áp dụng tại một điểm, nhưng phải ghi rõ tập điểm nào được đo và những trường hợp còn thiếu dữ liệu. Một giá trị trung bình không cho biết điểm chậm nhất đã hoàn tất.

## 9. Giao dịch, truyền sự kiện và retry

### 9.1. Không phát thành công trước khi trạng thái bền vững

Nếu hệ thống phát audit “đã thu hồi” rồi giao dịch lưu trạng thái rollback, dấu vết sẽ không phản ánh thực tế.

Nguồn phát cần phân biệt yêu cầu, kết quả commit và kết quả truyền. Một cơ chế lưu sự kiện bền vững cùng thay đổi trạng thái có thể hỗ trợ khôi phục việc phát sau khi tiến trình bị ngắt.

### 9.2. Phân biệt nhận sự kiện với áp dụng

Một hàng đợi xác nhận đã nhận thông điệp không có nghĩa điểm thực thi đã cập nhật kiểm tra truy cập.

Ngay cả consumer đã đọc thông điệp cũng có thể gặp lỗi cập nhật cache hoặc trạng thái cục bộ. Audit cần phản ánh mốc có thẩm quyền, không gộp tất cả thành `SUCCESS`.

### 9.3. Chịu được sự kiện trùng và đến muộn

Retry có thể làm một sự kiện được chuyển nhiều lần. Bên nhận cần định danh sự kiện hoặc phiên bản thay đổi để tránh tạo tác động ngoài dự kiến.

Một sự kiện cũ đến muộn không nên làm trạng thái quay về chấp nhận token đã bị thu hồi. Cơ chế cập nhật phải xem xét thứ tự logic hoặc điều kiện phiên bản theo thiết kế.

Audit vẫn cần phân biệt các lần thử chuyển cùng một thay đổi với nhiều thao tác thu hồi độc lập.

### 9.4. Giữ dữ liệu thực thi đủ lâu

Nếu một bản ghi thu hồi bị xóa trong khi token còn có thể được chấp nhận, bên nhận có thể mất căn cứ từ chối.

Thời gian giữ trạng thái phục vụ thực thi cần gắn với thời hạn token, khả năng cấp tiếp, độ lệch và mô hình thu hồi cụ thể. Nó không nhất thiết bằng thời gian lưu audit phục vụ điều tra.

Không dùng việc dọn audit hoặc giới hạn lưu log làm lý do xóa sớm trạng thái bảo mật đang còn cần.

## 10. Phạm vi phiên và kết nối dài hạn

Một token bị thu hồi không tự ngắt một kết nối đã mở nếu ứng dụng không có cơ chế kiểm tra lại hoặc kết thúc kết nối tương ứng.

Với kết nối thời gian thực, tải dữ liệu kéo dài hoặc job nền, cần xác định:

- Quyền được kiểm tra lúc mở, định kỳ hay trước từng tác động?
- Sự kiện thu hồi có kết thúc kết nối không?
- Job đang chạy có dừng, thu hẹp phạm vi hay hoàn tất theo một quyền ủy nhiệm đã định?
- Thao tác kết thúc có được xác nhận tại thành phần sở hữu không?

Audit phải ghi đúng kết quả. “Đã gửi yêu cầu đóng kết nối” khác “kết nối đã được đóng”. “Job bị yêu cầu hủy” khác “không còn tạo thêm kết quả”.

Thu hồi không lấy lại dữ liệu đã được tải trước đó. Khi điều tra, cần xác định các truy cập đã xảy ra trước và trong khoảng truyền thay đổi để đánh giá phạm vi ảnh hưởng.

## 11. Tránh lộ token và thông tin nhạy cảm trong log

Không ghi:

- Chuỗi access token hoặc refresh token.
- Header `Authorization`, cookie phiên hoặc client secret.
- Toàn bộ request đến endpoint thu hồi nếu có chứa token.
- URL, query hoặc body mang credential.
- Toàn bộ JWT đã giải mã chỉ để thuận tiện điều tra.
- Bí mật hoặc dữ liệu xác minh dùng trong quy trình thu hồi.

Việc loại bỏ token khỏi audit chính chưa đủ nếu proxy, tracing hoặc thông báo lỗi vẫn ghi nó.

Một hướng an toàn hơn là dựng sự kiện từ danh sách trường được phép, dùng tham chiếu quản lý không mang quyền truy cập và giới hạn việc liên kết danh tính theo nhu cầu.

Định danh token, grant hoặc phiên có thể vẫn là dữ liệu nhạy cảm dù không phải credential. Chúng cần quyền truy vấn, thời gian lưu và kiểm soát xuất dữ liệu phù hợp.

Ngữ cảnh như địa chỉ IP hoặc user agent chỉ hỗ trợ đối chiếu; không tự chứng minh ai đang cầm token. Các trường do client khai báo cần giới hạn, chuẩn hóa và phân biệt với dữ liệu hệ thống xác minh.

## 12. Token không tìm thấy, đã thu hồi và phản hồi bên ngoài

Một request thu hồi có thể chứa token không tồn tại, đã hết hạn hoặc đã bị thu hồi từ trước.

Hợp đồng API có thể dùng phản hồi bên ngoài không phân biệt một số trường hợp để tránh tiết lộ trạng thái token. Dù vậy, audit nội bộ cần ghi đúng điều có thể xác định:

```text
REQUEST_ACCEPTED
    không tự tương đương
MATCHED_TOKEN_STATE_CHANGED
```

Nếu không xác định được token, không tự gán nó cho một tài khoản lấy từ đầu vào chưa kiểm chứng và không ghi rằng một tài khoản cụ thể đã được thu hồi.

Nếu token đã ở trạng thái thu hồi, một request lặp có thể không tạo thêm thay đổi. Audit có thể ghi `ALREADY_REVOKED` hoặc một kết quả không thay đổi theo mô hình, cùng liên kết đến thao tác hiện tại.

Đây cũng là lý do không đếm số response thành công của endpoint như số token mới bị thu hồi. Hai chỉ số đo những điều khác nhau.

## 13. Quan sát và điều tra hoạt động sau thu hồi

Một lần sử dụng token đã thu hồi là tín hiệu đáng chú ý nhưng cần ngữ cảnh:

- Client có thể vẫn giữ bản token cũ.
- Một request đang truyền có thể đến sau thời điểm thu hồi.
- Một vùng triển khai có thể chưa cập nhật.
- Token có thể bị sao chép và được bên khác sử dụng.
- Một job hoặc tích hợp có thể chưa xử lý đúng kết quả thu hồi.

Sự kiện phát hiện nên liên kết đến thao tác thu hồi, thời điểm và điểm xác minh. Không ghi lại token để chứng minh nó đã được dùng.

Các chỉ số hữu ích gồm:

| Chỉ số | Ý nghĩa cần giữ rõ |
| --- | --- |
| Yêu cầu thu hồi đã nhận | Khối lượng request, chưa phải số thay đổi |
| Thay đổi thu hồi đã commit | Trạng thái được nguồn có thẩm quyền xác nhận |
| Điểm thực thi đã áp dụng | Độ bao phủ trên tập điểm được theo dõi |
| Thay đổi chưa được xác nhận | Backlog hoặc khoảng thiếu bằng chứng |
| Độ trễ áp dụng từng điểm | Khoảng thời gian giữa các mốc đã định |
| Lần sử dụng bị từ chối sau thu hồi | Hành vi được quan sát ở các đường có kiểm tra |
| Kết quả thu hồi một phần hoặc lỗi | Phạm vi còn cần xử lý |

“Không thấy request dùng token cũ” không chứng minh rằng token đã bị chặn. Nó chỉ có nghĩa chưa quan sát được lần sử dụng trong phạm vi dữ liệu đang có.

Quyền đọc và xuất audit cần được giới hạn theo vai trò và tenant. Nếu một khách hàng xem được tham chiếu token và lịch sử hoạt động của tenant khác, hệ thống audit đã tạo ra một đường rò dữ liệu.

## 14. Kiểm thử tính đúng của dấu vết thu hồi

| Tình huống | Bằng chứng cần kiểm tra |
| --- | --- |
| Người dùng tự thu hồi một phiên được phép | Actor và phạm vi được ghi chính xác |
| Quản trị viên thu hồi cho người khác | Người thực hiện thật và tài khoản đích được tách |
| Client yêu cầu phạm vi ngoài thẩm quyền | Không thay đổi trạng thái ngoài quyền |
| Giao dịch ghi trạng thái rollback | Không phát kết quả commit thành công sai |
| Tiến trình dừng sau commit trước khi gửi audit | Có khả năng phát lại từ trạng thái bền vững |
| Hàng đợi đã nhận nhưng điểm thực thi chưa cập nhật | Không coi là đã áp dụng hoàn toàn |
| Một điểm thực thi lỗi | Thấy rõ kết quả một phần và điểm chưa hoàn tất |
| Sự kiện trùng hoặc đến sai thứ tự | Không khôi phục khả năng dùng token đã thu hồi |
| Thu hồi refresh token khi access token còn tồn tại | Audit không khẳng định tất cả access token đã bị chặn |
| Một kết nối cũ vẫn mở | Trạng thái kết thúc kết nối phản ánh đúng thực tế |
| Token không tìm thấy hoặc đã thu hồi | Không tạo thay đổi hoặc gán chủ thể sai |
| Token cũ được trình lại | Sự kiện liên kết đúng mà không ghi credential |
| Kiểm tra log proxy và tracing | Không có token, cookie hoặc client secret |
| Truy vấn audit xuyên tenant | Không trả dữ liệu ngoài phạm vi được cấp |

Nên đối soát audit với trạng thái ở nguồn và hành vi của điểm thực thi. Chỉ kiểm tra rằng “có một dòng log” chưa đủ để chứng minh nội dung dòng đó đúng.

## 15. Áp dụng vào sự cố của Lan

Minh có thẩm quyền yêu cầu thu hồi quyền truy cập của Lan trong An Bình. Nguồn quản lý xác minh yêu cầu và ghi rõ Minh là actor, Lan là tài khoản đích, cùng phạm vi của thao tác.

Nếu bước đầu thu hồi chuỗi refresh token, audit ghi nhận việc ngăn sử dụng chuỗi đó theo cơ chế của token service. Các access token, phiên ứng dụng và kết nối dài hạn được xử lý theo phạm vi riêng.

Khi các điểm thực thi áp dụng thay đổi, chúng phát kết quả liên kết cùng thao tác và phiên bản. Điểm chưa xác nhận vẫn xuất hiện trong trạng thái theo dõi, thay vì bị che bởi một nhãn thành công toàn cục.

Qua chuỗi sự kiện này, người điều tra biết được yêu cầu nào đã được chấp nhận, thay đổi nào đã bền vững, nơi nào đã chặn truy cập và phần nào còn chưa đủ bằng chứng. Đó là cơ sở để audit token revocation hỗ trợ ứng phó sự cố và trách nhiệm giải trình.
