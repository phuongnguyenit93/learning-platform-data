# Threshold exception: kiểm soát ngoại lệ vượt ngưỡng phê duyệt

## 1. Ngoại lệ vượt ngưỡng là gì?

Trong chương **Approval Limits**, threshold exception là một quyết định cho phép xử lý một trường hợp cụ thể ngoài ngưỡng của luồng thông thường, theo một chính sách ngoại lệ đã được định nghĩa. Nó không phải quyền tùy ý bỏ qua kiểm soát.

Ví dụ: trưởng bộ phận chỉ được duyệt đề nghị mua sắm có tổng giá trị không quá 100 triệu đồng. Một đề nghị 120 triệu cần được chuyển sang cấp có thẩm quyền cao hơn. Nếu có tình huống khẩn cấp được chính sách cho phép, hệ thống có thể hỗ trợ một luồng ngoại lệ với điều kiện riêng.

Cần phân biệt ba việc:

| Tình huống | Bản chất |
| --- | --- |
| Chuyển đề nghị lên cấp có hạn mức cao hơn theo quy trình chuẩn | Chuyển cấp phê duyệt thông thường |
| Áp dụng điều khoản ngoại lệ đã được cho phép cho một trường hợp cụ thể | Ngoại lệ có kiểm soát |
| Gửi force=true hoặc sửa approved=true để bỏ kiểm tra | Bỏ qua quy tắc nghiệp vụ |

Không phải mọi khoản vượt ngưỡng đều cần hoặc được phép dùng ngoại lệ. Nếu đã có luồng chuyển cấp bình thường, hệ thống nên đi theo luồng đó trừ khi một điều khoản ngoại lệ thực sự áp dụng.

Rủi ro bảo mật xuất hiện khi ứng dụng biến “có cơ chế ngoại lệ” thành “có một cờ tắt kiểm tra”. Người dùng có thể giữ nguyên quyền đăng nhập nhưng thao tác với giá, đối tượng, phiên bản hoặc chuỗi phê duyệt để nhận quyền mà họ không được cấp.

Bài học tập trung vào cách mô hình hóa ngoại lệ thành **một quyền nghiệp vụ có phạm vi và vòng đời rõ ràng**, được kiểm tra tại transaction quyết định thực thi.

## 2. Một chính sách giả định để phân tích

Ví dụ dùng đề nghị mua sắm trong một tenant. Các con số chỉ là dữ liệu minh họa của hệ thống.

| Thành phần | Chính sách giả định |
| --- | --- |
| Ngưỡng của luồng bộ phận | Tổng tiền không quá 100.000.000 VND |
| Đúng 100.000.000 VND | Thuộc ngưỡng thông thường, vẫn cần đủ các bước bắt buộc |
| Vượt ngưỡng | Chuyển cấp theo quy trình chuẩn |
| Khi nào được xin ngoại lệ | Trường hợp khẩn cấp thuộc nhóm được chính sách cho phép |
| Trần ngoại lệ | Tổng tiền của đề nghị không quá 250.000.000 VND |
| Người duyệt ngoại lệ | Hai người độc lập thuộc hai nhóm thẩm quyền đã chỉ định |
| Người tạo đề nghị | Không được là một trong hai người duyệt ngoại lệ |
| Phạm vi ngoại lệ | Một đề nghị, một phiên bản, một nội dung đã xác định |
| Thời gian | Có cửa sổ hiệu lực do máy chủ cấp |
| Số lần sử dụng | Một lần tạo quyết định thực thi bền vững |
| Kiểm soát vẫn bắt buộc | Đúng tenant, quyền đối tượng, tách biệt nhiệm vụ, dữ liệu hợp lệ và các điều kiện thực thi khác |

Ở đây, “trần ngoại lệ 250 triệu” là **trần tổng tiền của đề nghị**, không phải phần vượt thêm trên 100 triệu. Đề nghị 300 triệu không được coi là hợp lệ vì phần vượt chỉ là 200 triệu.

Hạn mức phê duyệt cũng không phải ngân sách có sẵn. Một đề nghị được duyệt vẫn có thể bị từ chối thực thi nếu thiếu điều kiện ngân sách hoặc điều kiện nghiệp vụ khác. Ngoại lệ ngưỡng phê duyệt không tự cấp quyền vượt mọi giới hạn.

Đối với sản phẩm thực tế, mỗi loại giới hạn cần được phân loại:

- Có thể chuyển cấp theo quy trình chuẩn.
- Có thể xin ngoại lệ theo điều kiện cụ thể.
- Không được phép override trong luồng này.

Những invariant như không thao tác nhầm tenant, không dùng quyền đã thu hồi và không tạo tác động trùng không nên bị tắt khi xét ngoại lệ.

## 3. Business invariants cần giữ

Gọi:

- A là tổng tiền đã được máy chủ tính theo chính sách.
- T là ngưỡng thông thường của tuyến phê duyệt đang xét.
- E là trần ngoại lệ mà chính sách hiện hành cho phép.
- R là đề nghị cùng phiên bản và nội dung cần xử lý.
- G là bản ghi cấp ngoại lệ cho R.
- t là thời điểm quyết định tiêu thụ ngoại lệ.

Điều kiện ngoại lệ không chỉ là A > T. Một quyết định hợp lệ còn phải bảo đảm:

~~~text
đúng quyền đối tượng
AND đủ điều kiện bắt buộc
AND chính sách cho phép loại ngoại lệ này
AND đủ người duyệt độc lập, đúng thẩm quyền
AND G gắn đúng R và nội dung hiện hành
AND A <= E
AND G chưa bị dùng, thu hồi hoặc hết hạn
AND valid_from <= t < expires_at
~~~

Tại bước thực thi, tuyến cấp quyền phải được phân biệt rõ:

~~~text
được thực thi =
    điều kiện bắt buộc
    AND (
        đủ phê duyệt theo tuyến chuẩn
        OR đủ quyền ngoại lệ theo chính sách
    )
~~~

“Điều kiện bắt buộc” nằm ngoài hai nhánh. Không viết biểu thức khiến có ngoại lệ là bỏ luôn kiểm tra tenant, chủ thể hoặc trạng thái.

Các invariant quan trọng:

| Invariant | Lỗi bị ngăn |
| --- | --- |
| Ngoại lệ thuộc đúng tenant và đề nghị | Dùng mã ngoại lệ của đối tượng khác |
| Nội dung thực thi khớp nội dung đã duyệt | Tăng tiền hoặc đổi người nhận sau phê duyệt |
| Người duyệt có thẩm quyền ngoại lệ riêng | Dùng quyền duyệt thông thường để tự vượt hạn mức |
| Đủ người duyệt độc lập | Một người dùng nhiều tài khoản hoặc vai trò để tự duyệt |
| Một ngoại lệ chỉ gắn với một quyết định thực thi | Retry hoặc request đồng thời dùng lại quyền |
| Tiêu thụ ngoại lệ và ghi quyết định cùng commit | Quyền bị dùng nhưng không có kết quả, hoặc ngược lại |
| Đủ thời hạn và đúng phiên bản chính sách | Dùng quyền cũ sau khi điều kiện đã thay đổi |
| Mọi ngoại lệ có căn cứ và dấu vết | Đường bypass không thể giải thích |
| Luồng ngoại lệ không tự mở rộng phạm vi | Một quyết định tạm thời biến thành quyền quản trị lâu dài |

## 4. Tính ngưỡng đúng trước khi xét ngoại lệ

### 4.1. So sánh đúng tại điểm bằng nhau

Với chính sách ở phần 2:

~~~text
A <= 100.000.000 VND:
    có thể thuộc tuyến bộ phận.

A > 100.000.000 VND:
    tuyến bộ phận không đủ thẩm quyền.

A <= 250.000.000 VND:
    chỉ là một điều kiện về tiền của tuyến ngoại lệ.

A > 250.000.000 VND:
    không được dùng loại ngoại lệ này.
~~~

“Không quá” bao gồm điểm bằng. “Từ mức này trở lên” lại có ranh giới khác. Phải lấy ngữ nghĩa từ chính sách, không đoán dấu so sánh từ tên biến threshold.

| Tổng tiền | Kết luận trong ví dụ |
| --- | --- |
| 99.999.999 VND | Có thể ở tuyến thông thường |
| 100.000.000 VND | Có thể ở tuyến thông thường |
| 100.000.001 VND | Cần tuyến khác, không được trưởng bộ phận tự duyệt |
| 250.000.000 VND | Có thể xét ngoại lệ nếu đủ mọi điều kiện khác |
| 250.000.001 VND | Vượt trần của ngoại lệ này |

### 4.2. Máy chủ quyết định số tiền dùng để so sánh

Không tin totalAmount, unitPrice, discount hoặc approvedAmount do client gửi. Máy chủ phải xác minh các thành phần tạo nên A, chẳng hạn:

- Số lượng và đơn giá được phép dùng.
- Phí và thuế thuộc phạm vi chính sách.
- Chiết khấu hợp lệ.
- Tiền tệ và quy tắc chuyển đổi nếu chính sách có quy đổi.
- Những khoản liên quan phải cộng gộp theo định nghĩa nghiệp vụ.

Nếu ngưỡng tính trên tổng sau phí nhưng UI chỉ kiểm tra giá hàng trước phí, người dùng có thể lọt qua tuyến thấp hơn.

Với ví dụ chỉ dùng VND nguyên đồng, có thể lưu số tiền bằng số nguyên có giới hạn. Không dùng double cho phép so sánh tiền tại ngưỡng. Khi tính tổng bằng long trong Java, cần kiểm soát tràn:

~~~java
long lineTotalVnd = Math.multiplyExact(quantity, unitPriceVnd);
long totalVnd = Math.addExact(lineTotalVnd, feeVnd);
~~~

Đây chỉ là minh họa phép tính an toàn về số nguyên. Vẫn phải kiểm tra quantity, giá, phí và miền giá trị theo chính sách. Nếu phép tính tràn hoặc dữ liệu không hợp lệ, từ chối yêu cầu; không chuyển kết quả sang số âm rồi tiếp tục so ngưỡng.

Nếu có nhiều tiền tệ, không so trực tiếp một số USD với ngưỡng VND. Chính sách phải chỉ rõ đồng tiền chuẩn, nguồn tỷ giá, thời điểm và quy tắc làm tròn. Những dữ liệu ảnh hưởng quyết định đó cần được lưu hoặc ràng buộc vào phiên bản đã duyệt.

## 5. Mô hình ngoại lệ như một grant có giới hạn

Một bản ghi threshold_exception có thể có:

| Nhóm dữ liệu | Ví dụ |
| --- | --- |
| Định danh | tenant_id, exception_id |
| Đối tượng | request_id, request_revision |
| Nội dung | request_digest, approved_total_vnd, currency |
| Loại quyền | exception_type, rule_id |
| Chính sách | policy_version, điều khoản cho phép |
| Căn cứ | reason_code, tham chiếu chứng cứ |
| Người xin | requester_subject_id, actor tạo yêu cầu |
| Phê duyệt | Danh sách quyết định cùng danh tính người duyệt |
| Hiệu lực | valid_from, expires_at |
| Trạng thái | REQUESTED, APPROVED, REJECTED, REVOKED, EXPIRED, CONSUMED |
| Kết quả sử dụng | consumed_at, consumed_by_intent_id |
| Kiểm soát đồng thời | version |

Bản ghi grant khác với vai trò người dùng. Người có quyền duyệt ngoại lệ không tự động có quyền sửa mọi đề nghị, thay nội dung đã duyệt hoặc thực thi cho tenant khác.

Cũng cần phân biệt:

- **Trần của chính sách:** giới hạn tối đa mà loại ngoại lệ có thể cấp.
- **Quyết định cụ thể:** nội dung nào, số tiền nào và trường hợp nào đã được cấp quyền.
- **Thẩm quyền người duyệt:** ai được cấp quyết định đó tại thời điểm cần kiểm tra.

Có thể có trần theo từng người duyệt hoặc từng nhóm. Việc một loại ngoại lệ cho phép tới 250 triệu không chứng minh mọi người trong nhóm đều có quyền duyệt tới mức đó.

Không dùng ghi chú tự do như “sếp đã đồng ý” làm bằng chứng duy nhất. Căn cứ nghiệp vụ cần được lưu có cấu trúc đủ để kiểm tra và kiểm toán, với dữ liệu nhạy cảm được bảo vệ phù hợp.

## 6. Vòng đời và ý nghĩa của CONSUMED

### 6.1. Vòng đời của grant

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED: Gửi yêu cầu ngoại lệ
    REQUESTED --> APPROVED: Đủ quyết định độc lập
    REQUESTED --> REJECTED: Không đủ điều kiện
    REQUESTED --> REVOKED: Rút yêu cầu
    APPROVED --> CONSUMED: Ghi quyết định thực thi
    APPROVED --> REVOKED: Thu hồi trước khi dùng
    APPROVED --> EXPIRED: Hết thời hạn
~~~

REQUESTED chưa cho phép thực thi. APPROVED cũng chưa đủ nếu đã quá expires_at, sai phiên bản hoặc không còn thỏa chính sách được áp dụng.

Trong ví dụ, CONSUMED có nghĩa là ngoại lệ đã được gắn với **một execution intent bền vững**: một quyết định nội bộ cho phép thực thi nội dung bất biến. Nó không nhất thiết có nghĩa thao tác bên ngoài đã hoàn tất.

Điều này cần được thống nhất trước khi xây dựng retry và tích hợp.

### 6.2. Vòng đời đề nghị

Một mô hình có thể là:

~~~text
DRAFT
-> PENDING_REVIEW
-> READY_TO_EXECUTE
-> EXECUTION_PENDING
-> EXECUTED
~~~

Các nhánh REJECTED hoặc CANCELLED có thể tồn tại theo chính sách. Không cho client đặt trực tiếp READY_TO_EXECUTE hoặc EXECUTED.

Ở transaction tạo execution intent:

- Đề nghị chuyển từ READY_TO_EXECUTE sang EXECUTION_PENDING.
- Ngoại lệ được chuyển APPROVED → CONSUMED nếu tuyến đó được sử dụng.
- Execution intent có định danh duy nhất được ghi.
- Kết quả idempotency và outbox liên quan cùng commit.

Trạng thái READY_TO_EXECUTE chỉ là một phần của kiểm tra. Đường thực thi vẫn phải kiểm tra bằng chứng phê duyệt, grant và phiên bản hiện hành. Một trạng thái cũ không thể thay thế toàn bộ điều kiện cấp quyền.

### 6.3. Không tự hoàn nguyên quyền sau lỗi bên ngoài

Nếu đã tiêu thụ grant rồi dịch vụ ngoài timeout, không chuyển lại APPROVED ngay. Timeout có thể xảy ra sau khi dịch vụ ngoài đã thực hiện.

Hệ thống phải tra cứu và đối soát theo execution intent ban đầu. Nếu cần thử lại, dùng cùng định danh nghiệp vụ và idempotency phù hợp. Nếu thất bại đã được xác định và cần một quyết định thay thế, phải có quy trình bảo đảm quyết định cũ không tiếp tục gây tác động.

## 7. Ai được xin và ai được duyệt ngoại lệ?

### 7.1. Kiểm tra quyền theo hành động và đối tượng

Cần tách ít nhất các quyền:

- Tạo hoặc sửa đề nghị.
- Xin ngoại lệ cho một loại quy tắc.
- Duyệt ngoại lệ trong phạm vi được giao.
- Thu hồi grant chưa sử dụng.
- Khởi tạo thực thi.
- Xem chứng cứ và nhật ký.

Mọi quyền đều cần giới hạn tenant, đơn vị, đối tượng và phạm vi tiền thích hợp. Biết exception_id không đồng nghĩa có quyền sử dụng hoặc thu hồi grant.

Mã UUID khó đoán chỉ giúp giảm khả năng đoán mã; nó không thay kiểm tra quan hệ giữa grant, đề nghị và người thực hiện.

### 7.2. Hai bước không nhất thiết là hai người độc lập

Một workflow có hai ô phê duyệt vẫn có thể bị một người hoàn tất nếu:

- Một người có hai tài khoản.
- Cùng người được gán hai vai trò.
- Người xin ngoại lệ đồng thời là người duyệt ở bước sau.
- Người được ủy quyền gián tiếp quay lại duyệt cho chính người ủy quyền theo cách chính sách cấm.

Điều kiện độc lập phải dùng danh tính và quan hệ có thẩm quyền của hệ thống, không chỉ so hai tên tài khoản hoặc hai chuỗi role.

Chính sách cần xác định những xung đột nào bị cấm. Trong ví dụ, người tạo đề nghị không được tham gia hai quyết định duyệt và hai người duyệt phải khác nhau theo danh tính tổ chức.

### 7.3. Thẩm quyền ngoại lệ phải được cấp riêng

Không suy ra quyền duyệt vượt ngưỡng chỉ từ quyền duyệt thông thường. Một trưởng bộ phận không được tự biến hạn mức 100 triệu thành 250 triệu bằng cách chọn exception_type.

Client có thể đề nghị một loại ngoại lệ; máy chủ quyết định loại đó có áp dụng được hay không và ai được duyệt.

Ủy quyền cũng phải có phạm vi, thời hạn và giới hạn phù hợp. Không cho người được ủy quyền cấp lại quyền rộng hơn người ủy quyền hoặc vượt điều kiện độc lập của workflow.

## 8. Ràng buộc ngoại lệ với nội dung đã duyệt

### 8.1. Phiên bản là một phần của quyền

Giả sử ngoại lệ được duyệt cho:

~~~text
request_id: R-42
request_revision: 7
supplier: S-10
total: 120.000.000 VND
items: nội dung đã xác định
~~~

Nếu người tạo đổi nhà cung cấp hoặc tăng tiền lên 200 triệu ở revision 8, grant của revision 7 không được áp dụng dù 200 triệu vẫn dưới trần 250 triệu.

Trần chính sách cho biết hệ thống có thể cấp tới đâu. Nó không chứng minh người duyệt đã chấp nhận mọi nội dung dưới trần đó.

Trong ví dụ, bất kỳ thay đổi nào ảnh hưởng nội dung phê duyệt đều làm mất hiệu lực các quyết định cũ. Kể cả thay đổi giảm tổng tiền cũng cần đi theo quy tắc phiên bản; không tự giả định người duyệt chỉ quan tâm một con số.

### 8.2. Digest do máy chủ tạo

request_digest có thể được tạo từ biểu diễn chuẩn của:

- Tenant, request_id và revision.
- Chủ thể đề nghị, đơn vị và người nhận lợi ích.
- Nhà cung cấp hoặc tài khoản thụ hưởng liên quan.
- Danh sách hàng hóa, số lượng, đơn giá, phí và chiết khấu.
- Tổng tiền, tiền tệ, quy tắc quy đổi được áp dụng.
- Loại ngoại lệ, điều khoản và phiên bản chính sách liên quan.

Máy chủ tạo digest từ dữ liệu chuẩn, không nhận hash của client làm bằng chứng đủ. Các trường ảnh hưởng quyền cần được bao phủ. Hai JSON khác thứ tự field không nên tạo ra sự hiểu nhầm về nội dung nghiệp vụ; cần quy tắc canonicalization rõ ràng.

Digest hỗ trợ ràng buộc nội dung và kiểm toán. Nó không thay quyền đối tượng, khóa hàng, kiểm tra phiên bản hoặc lưu dữ liệu cần thiết.

### 8.3. Chỉnh sửa phải làm mất hiệu lực có kiểm soát

Một luồng sửa nội dung đã trình duyệt có thể:

1. Khóa đề nghị theo giao thức của ứng dụng.
2. Xác minh chưa có execution intent bền vững cho nội dung đó.
3. Tăng revision và ghi nội dung mới.
4. Đánh dấu các quyết định phê duyệt và grant cũ không còn dùng được.
5. Đưa đề nghị trở lại bước xét duyệt phù hợp.
6. Commit toàn bộ thay đổi.

Đường thực thi vẫn phải kiểm tra revision và digest ngay cả khi hệ thống đã đánh dấu grant cũ. Kiểm tra lúc dùng là lớp bảo vệ trước dữ liệu cũ, đường ghi bị bỏ sót hoặc request chạy đồng thời.

## 9. Transaction tại điểm thực thi

### 9.1. Vì sao kiểm tra lúc duyệt chưa đủ?

Một grant có thể hợp lệ khi được duyệt nhưng không còn hợp lệ lúc thực thi:

- Đề nghị đã đổi revision.
- Grant đã bị thu hồi hoặc hết hạn.
- Người duyệt không còn thẩm quyền theo chính sách áp dụng.
- Chính sách đã thay đổi ngưỡng hoặc trần ngoại lệ.
- Một request khác đã tiêu thụ grant.
- Hạn mức tổng hợp hoặc số suất ngoại lệ đã hết.

Vì vậy, thao tác thực thi cần có một điểm quyết định nguyên tử. Không kiểm tra grant ở một request rồi dựa vào cờ frontend cho request sau.

### 9.2. Phạm vi nhất quán của ví dụ

Giả sử dữ liệu đề nghị, chính sách áp dụng, bằng chứng thẩm quyền, grant, quota liên quan, execution intent và idempotency đều được bảo vệ trong cùng một cơ sở dữ liệu.

Một giao thức có thể khóa theo thứ tự nhất quán:

1. Bản ghi idempotency của thao tác.
2. Chính sách và các hàng thẩm quyền cần kiểm tra.
3. Hàng tổng hợp hoặc quota nếu chính sách có.
4. Đề nghị.
5. Grant ngoại lệ cùng các quyết định phê duyệt liên quan.
6. Ghi execution intent và các bản ghi hệ quả.

Các hàng trong cùng nhóm được khóa theo thứ tự khóa ổn định. Mọi luồng sửa, duyệt, thu hồi và thực thi phải tuân theo giao thức chung, không chỉ endpoint thực thi.

Có thể đọc dữ liệu định tuyến trước để biết cần khóa hàng nào, nhưng phải xác minh lại liên kết và phiên bản sau khi có đủ khóa. Nếu tập dữ liệu cần khóa thay đổi, transaction phải xử lý lại theo giao thức, không khóa thêm tùy tiện theo thứ tự ngược.

Một transaction không tự làm mọi điều kiện đã đọc trở nên bất biến. Cần chọn cơ chế khóa, cập nhật có điều kiện hoặc kiểm tra phiên bản phù hợp với từng dữ liệu được dùng để quyết định.

### 9.3. Cập nhật tiêu thụ grant có điều kiện

SQL sau minh họa lớp bảo vệ tại lần ghi, sau khi đã kiểm tra thẩm quyền và các điều kiện bắt buộc dưới cơ chế nhất quán:

~~~sql
UPDATE threshold_exception
SET state = 'CONSUMED',
    consumed_by_intent_id = :intent_id,
    consumed_at = :decision_time,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND exception_id = :exception_id
  AND request_id = :request_id
  AND request_revision = :current_request_revision
  AND request_digest = :current_request_digest
  AND approved_total_vnd = :computed_total_vnd
  AND currency = 'VND'
  AND approved_total_vnd <= :current_exception_cap_vnd
  AND policy_version = :current_policy_version
  AND version = :locked_exception_version
  AND state = 'APPROVED'
  AND valid_from <= :decision_time
  AND :decision_time < expires_at;
~~~

Chỉ tiếp tục nếu đúng một hàng được cập nhật. Số tiền và trần trong tham số do máy chủ xác định, không lấy trực tiếp từ request client.

Câu lệnh này không tự chứng minh đủ hai người duyệt hoặc chính sách cho phép trường hợp khẩn cấp. Những điều kiện đó phải được kiểm tra bằng dữ liệu đáng tin cậy và được bảo vệ trong cùng giao thức.

Trong cùng transaction, cần:

- Ghi execution intent duy nhất theo tenant, đề nghị và revision.
- Chuyển trạng thái đề nghị bằng điều kiện revision và trạng thái hiện hành.
- Ghi nhận quota hoặc tổng hợp theo định nghĩa chính sách.
- Ghi outbox nếu có công việc bên ngoài.
- Hoàn thành bản ghi idempotency.

Nếu bất kỳ bước nào thất bại, rollback toàn bộ. Không commit grant CONSUMED khi chưa có execution intent tương ứng, cũng không commit execution intent dùng ngoại lệ khi grant chưa được tiêu thụ hợp lệ.

Ràng buộc duy nhất của execution intent bảo vệ cả trường hợp hai request dùng hai key hoặc hai exception_id khác nhau cho cùng một phiên bản đề nghị.

### 9.4. Mã giả Java

Đây là cấu trúc minh họa; các API bên dưới là abstraction của ứng dụng, không phải thư viện có sẵn.

~~~java
ExecutionResult execute(AuthContext auth, ExecuteCommand cmd) {
    String fingerprint = fingerprint(
        cmd.requestId(), cmd.requestRevision(), cmd.exceptionId()
    );

    return tx.required(connection -> {
        IdempotencyDecision key = idem.acquire(
            connection, auth, "EXECUTE_PURCHASE_REQUEST",
            cmd.idempotencyKey(), fingerprint
        );

        if (key.hasResult()) {
            authorization.checkResultAccess(auth, key.originalResult());
            return key.originalResult();
        }

        ExecutionContext context = workflow.lockDecisionContext(
            connection, auth, cmd.requestId(), cmd.exceptionId()
        );

        PurchaseRequest request = context.request();
        authorization.requireExecutionPermission(auth, request);
        request.requireRevision(cmd.requestRevision());
        request.requireReadyToExecute();

        context.requireMandatoryControls();
        long totalVnd = pricing.recomputeAndVerify(context);

        RouteDecision route = approvalEngine.requireAuthorizedRoute(
            context, totalVnd
        );

        Instant decisionTime = timeSource.nowAfterLocks(connection);

        if (route.usesException()) {
            route.grant().requireActiveAt(decisionTime);
            route.grant().requireExactBinding(request, totalVnd);
        }

        String intentId = ids.newExecutionIntentId();
        intents.insertUnique(connection, intentId, request, route);

        if (route.usesException()) {
            exceptions.consumeExactlyOnce(
                connection, route.grant(), request,
                context.currentPolicy(), totalVnd,
                decisionTime, intentId
            );
        }

        usage.recordDecisionIfAllowed(
            connection, context, totalVnd, route
        );
        requests.markExecutionPending(connection, request, intentId);
        outbox.enqueueExecution(connection, intentId);

        ExecutionResult result = ExecutionResult.pending(intentId);
        return idem.complete(connection, key, result);
    });
}
~~~

Hợp đồng của các abstraction:

- Mọi thao tác dữ liệu bên trong dùng cùng connection và transaction.
- tx.required chỉ đưa kết quả thành công ra ngoài sau commit.
- lockDecisionContext thực hiện giao thức khóa và đọc lại dữ liệu hiện hành, không chỉ gom các bản sao từ cache.
- requireMandatoryControls không bị bỏ qua khi route là ngoại lệ.
- approvalEngine kiểm tra tuyến chuẩn hoặc tuyến ngoại lệ từ chính sách, quyền và bằng chứng đã xác minh; client không được tự chọn một tuyến yếu hơn.
- pricing xác minh số tiền và nội dung khớp phiên bản được duyệt. Giá thay đổi không được tự dùng grant cũ.
- consumeExactlyOnce và markExecutionPending kiểm tra số hàng cập nhật. Xung đột làm rollback.
- usage chỉ ghi nhận những hạn mức tổng hợp được chính sách định nghĩa; nếu vượt, cả transaction rollback.
- nowAfterLocks đọc thời gian quyết định sau khi đã chờ khóa theo nguồn chuẩn được chọn.
- Không gọi một dịch vụ bên ngoài chậm trong lúc đang giữ các khóa này.

Ví dụ trả EXECUTION_PENDING vì mới có quyết định nội bộ bền vững. Không trả “đã thanh toán” hoặc “đã hoàn tất mua sắm” khi hệ thống bên ngoài chưa xác nhận điều đó.

## 10. Hạn mức cộng gộp và hành vi chia nhỏ

### 10.1. Phải xác định ngưỡng áp dụng cho đơn vị nào

Chính sách “100 triệu mỗi đề nghị” khác “100 triệu cho một nhu cầu mua” hoặc “100 triệu cho một đơn vị trong ngày”.

Nếu chính sách thực sự độc lập theo từng đề nghị, hai đề nghị 60 triệu không tự động vi phạm chỉ từ con số 100 triệu. Muốn cấm chia nhỏ để né cấp duyệt, yêu cầu nghiệp vụ phải định nghĩa phạm vi cộng gộp.

Ví dụ phạm vi có thể là:

- Cùng một nhu cầu mua đã được hệ thống định danh.
- Cùng một hợp đồng hoặc đợt mua sắm.
- Cùng đơn vị và loại chi phí trong một kỳ.
- Một nhóm đề nghị liên quan được xác định theo chính sách.

Không cho client tự đặt group_id mới để biến cùng một nhu cầu thành nhiều nhóm độc lập. Các trường nhóm phải có nguồn đáng tin cậy hoặc cần quy trình xác minh.

### 10.2. Kiểm tra tổng hợp cũng cần nguyên tử

Giả sử chính sách bổ sung tính ngưỡng theo cùng một nhu cầu mua. Đã có 60 triệu được cam kết, hai request mới mỗi request 30 triệu cùng chạy.

Nếu cả hai cùng đọc tổng cũ là 60 triệu và tự kết luận tổng mới là 90 triệu, hệ thống có thể cam kết 120 triệu qua tuyến thấp.

Cần khóa hoặc cập nhật có điều kiện trên hàng tổng hợp theo đúng phạm vi, trong cùng transaction tạo quyết định. Tổng hợp nên tính các execution intent đang có hiệu lực theo định nghĩa chính sách, kể cả việc chưa hoàn tất bên ngoài nếu chúng đã là cam kết chiếm hạn mức.

Không chỉ cộng những tác động đã hoàn thành nếu các quyết định đang chờ vẫn có thể cùng hoàn thành sau đó.

Khi hủy hoặc giải phóng một cam kết, chỉ giảm tổng hợp khi chính sách cho phép và đã bảo đảm quyết định đó không còn gây tác động. Retry hủy không được giảm số tổng hợp hai lần.

### 10.3. Phát hiện hành vi và invariant không giống nhau

Quan sát các đề nghị gần ngưỡng, cùng nhà cung cấp và thời gian gần nhau giúp phát hiện dấu hiệu chia nhỏ. Đó có thể là tín hiệu chuyển kiểm tra hoặc điều tra, nhưng không tự chứng minh mọi giao dịch là cùng một nhu cầu.

Nếu chưa thể xác định nhóm một cách chắc chắn, phải nói rõ giới hạn của cơ chế và thiết kế bước xác minh phù hợp. Không coi một phép lọc theo IP hoặc một chuỗi mô tả giống nhau là invariant chắc chắn.

Cũng có thể giới hạn số suất hoặc tổng giá trị ngoại lệ theo đơn vị trong kỳ. Đây là quota riêng, không đồng nhất với trần tiền của từng grant. Quota đó cần được kiểm tra và cập nhật trong cùng ranh giới nhất quán.

## 11. Chính sách và thẩm quyền thay đổi sau phê duyệt

### 11.1. Chọn quy tắc hiệu lực rõ ràng

Có hai cách tiếp cận thường gặp:

| Cách áp dụng | Điều phải quy định |
| --- | --- |
| Kiểm tra lại chính sách và thẩm quyền hiện hành trước khi dùng | Thay đổi nào làm grant cũ phải duyệt lại |
| Tôn trọng quyết định đã cấp theo phiên bản cũ trong phạm vi cho phép | Trường hợp nào vẫn được bảo lưu và trường hợp nào bắt buộc thu hồi |

Không chọn ngầm bằng cách bỏ kiểm tra version.

Ví dụ trong bài dùng cách thận trọng: trước khi tiêu thụ, policy_version phải khớp chính sách hiện hành và người duyệt vẫn phải đủ thẩm quyền theo quy tắc được chọn. Nếu không khớp, dừng và yêu cầu xét lại thay vì tự nâng grant sang chính sách mới.

Nếu trần ngoại lệ bị hạ từ 250 triệu xuống 150 triệu, grant 200 triệu không được tự tiếp tục theo ví dụ này.

### 11.2. Thu hồi quyền và tiêu thụ grant phải có thứ tự rõ

Nếu người duyệt bị thu hồi thẩm quyền đồng thời với việc dùng grant, hệ thống cần một cơ chế quyết định thứ tự. Trong mô hình cùng DB, có thể bảo vệ hàng thẩm quyền hoặc revision liên quan theo cùng giao thức với transaction tiêu thụ.

Chỉ gọi một hàm kiểm tra role rồi dùng kết quả đó nhiều phút sau không chứng minh quyền còn hiệu lực tại điểm quyết định.

Nếu IAM hoặc chính sách nằm ở hệ thống khác, không giả định một lần HTTP check sẽ commit nguyên tử với DB nghiệp vụ. Cần giao thức phù hợp với mức bảo đảm đã chọn, chẳng hạn bằng chứng có phiên bản và phạm vi, quy tắc thu hồi, hoặc cơ chế điều phối khác. Khi không xác minh đủ điều kiện bắt buộc, không mặc định cho qua.

### 11.3. Không sửa lịch sử để hợp thức hóa

Quyết định đã cấp cần giữ người duyệt, thời điểm, nội dung và phiên bản chính sách gốc. Nếu phải xét lại, tạo quyết định mới hoặc phiên bản mới có liên kết lịch sử.

Không đổi tên người duyệt, cập nhật policy_version cũ thành mới hoặc sửa số tiền trong bản ghi phê duyệt để làm grant “có vẻ hợp lệ”.

## 12. Hết hạn, thu hồi và tích hợp bên ngoài

### 12.1. Thời hạn giới hạn lúc nào?

Trong ví dụ, grant phải còn hiệu lực tại thời điểm tạo execution intent:

~~~text
valid_from <= decision_time < expires_at
~~~

Đúng tại expires_at là hết hạn. Thời gian do nguồn chuẩn phía máy chủ quyết định sau khi có đủ khóa.

Nếu intent đã commit hợp lệ trước hạn, consumer có thể xử lý hệ quả sau đó theo chính sách. Grant không được tiêu thụ lần hai. Nếu sản phẩm yêu cầu tái kiểm tra trước tác động bên ngoài, phải mô hình hóa thêm quy tắc đó và cách hủy an toàn.

Không để một dịch vụ hiểu expires_at là hạn bắt đầu, dịch vụ khác hiểu là hạn hoàn tất mà không có hợp đồng chung.

### 12.2. Thu hồi trước và sau CONSUMED

Trước CONSUMED, thu hồi có thể chuyển APPROVED → REVOKED bằng transaction cạnh tranh với tiêu thụ. Chỉ một thứ tự quyết định được chấp nhận: thu hồi thắng thì không tạo intent; tiêu thụ thắng thì grant đã gắn với intent.

Sau CONSUMED, việc sửa trạng thái grant không tự đảo ngược tác động bên ngoài. Cần quy trình hủy intent, ngăn tác vụ chưa gửi hoặc xử lý bù theo trạng thái thực tế.

Không tuyên bố “đã thu hồi nên chắc chắn chưa chi” khi một yêu cầu có thể đang ở phía dịch vụ khác.

### 12.3. Outbox và idempotency

Trong cùng transaction local, có thể ghi:

~~~text
grant CONSUMED
+ request EXECUTION_PENDING
+ execution intent
+ outbox event
+ idempotency result
~~~

Sau commit, worker phát hoặc xử lý outbox. Worker có thể chạy lại, nên định danh intent phải được dùng nhất quán khi tương tác với bên ngoài.

Outbox không tự bảo đảm nơi nhận chỉ thực hiện một lần. Cần idempotency phía nhận hoặc cơ chế xác nhận, tra cứu và đối soát phù hợp.

Nếu client mất phản hồi sau commit, gửi lại cùng key phải nhận intent cũ. Nếu gửi key mới, ràng buộc duy nhất của đề nghị và trạng thái grant vẫn phải ngăn tác động mới.

Một grant đã CONSUMED không được phát lại như một quyền cấp mới. Hệ thống chỉ trả lại kết quả đã tạo cho người có quyền xem.

## 13. Những mẫu bypass cần nhận diện

| Thiết kế dễ sai | Cách invariant bị phá | Hướng xử lý |
| --- | --- | --- |
| Request có skipApproval hoặc force | Client tự tắt điều kiện | Máy chủ suy ra tuyến từ chính sách |
| Có role APPROVER là duyệt mọi mức | Quyền thông thường biến thành quyền ngoại lệ | Tách thẩm quyền, phạm vi và trần |
| Duyệt bằng exception_id đơn lẻ | Dùng grant của đề nghị khác | Kiểm tra tenant, request, revision và nội dung |
| Grant chỉ ghi “tối đa 250 triệu” | Đổi đối tượng hoặc giá trong phạm vi trần | Ràng buộc quyết định cụ thể với nội dung đã duyệt |
| Chỉ so tổng từ client | Sửa giá hoặc bỏ phí để vào tuyến thấp | Tính và xác minh phía máy chủ |
| Hai bước duyệt cùng một người | Không còn kiểm tra độc lập | Kiểm tra danh tính và quan hệ xung đột |
| Duyệt rồi cho sửa không tăng revision | Phê duyệt cũ phủ lên dữ liệu mới | Phiên bản hóa và mất hiệu lực quyết định cũ |
| Kiểm tra grant rồi commit tác động ở nơi khác | Hai request cùng dùng quyền | Transaction tiêu thụ cùng quyết định bền vững |
| Timeout thì trả grant về APPROVED | Tác động cũ vẫn có thể thành công | Đối soát intent và retry cùng định danh |
| Tin worker đã đổi EXPIRED | Worker chậm kéo dài quyền | Kiểm tra thời gian ngay tại lúc dùng |
| Sửa hạn mức người dùng để duyệt một trường hợp | Ngoại lệ biến thành quyền lâu dài | Grant có phạm vi cho một quyết định |
| Cộng gộp bằng truy vấn không bảo vệ đồng thời | Nhiều yêu cầu cùng vượt tổng | Khóa hoặc cập nhật nguyên tử hàng tổng hợp |

Một “đường khẩn cấp” vẫn là một workflow nghiệp vụ. Nó cần điều kiện vào, người chịu trách nhiệm, phạm vi quyền, điểm tiêu thụ và lịch sử. Không nên tồn tại dưới dạng endpoint quản trị nhận một cờ để chuyển thẳng đề nghị sang EXECUTED.

## 14. Kiểm thử các tình huống tấn công logic

### 14.1. Ma trận theo chính sách ví dụ

Các trường hợp tuyến thông thường giả sử những điều kiện khác đã đầy đủ. Các trường hợp ngoại lệ phải được kiểm tra theo đúng tuyến ngoại lệ, không nhầm với tuyến chuẩn của cấp cao hơn.

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| Tổng 100.000.000 VND | Không bị phân loại vượt ngưỡng bộ phận |
| Tổng 100.000.001 VND, chỉ có duyệt bộ phận | Không thực thi; thẩm quyền đó chưa đủ |
| Tổng 250.000.000 VND, đủ grant và điều kiện | Có thể tiêu thụ ngoại lệ |
| Tổng 250.000.001 VND trên tuyến ngoại lệ này | Bị từ chối vì vượt trần |
| Có đủ duyệt chuẩn của cấp cao hơn | Không bắt buộc dùng ngoại lệ nếu chính sách không yêu cầu |
| Client sửa totalAmount hoặc force | Không làm thay đổi tuyến hoặc bỏ kiểm tra |
| Sai tenant, request hoặc subject | Không dùng được grant ngoài phạm vi |
| Chỉ có một trong hai người duyệt | Không tạo quyền ngoại lệ đủ điều kiện |
| Một người dùng hai tài khoản để duyệt | Bị chặn nếu cùng danh tính theo chính sách độc lập |
| Người tạo cũng là người duyệt | Bị từ chối theo quy tắc tách biệt nhiệm vụ |
| Người duyệt vượt trần của chính mình | Không tạo được quyết định hợp lệ |
| Đổi nhà cung cấp sau khi duyệt | Grant phiên bản cũ không dùng được |
| Tăng hoặc giảm tiền sau khi duyệt | Áp dụng đúng quy tắc revision của ví dụ |
| Request dùng hash tự tạo | Không thay thế digest do máy chủ xác minh |
| Grant APPROVED nhưng quá hạn | Không tiêu thụ được dù worker chưa chạy |
| Tiêu thụ đúng tại expires_at | Bị từ chối |
| Grant đã REVOKED hoặc CONSUMED | Không cấp thêm quyền |
| Hai request cùng grant, cùng key | Một kết quả tạo intent, request còn lại phát lại |
| Hai request cùng grant, khác key | Tối đa một intent có hiệu lực |
| Hai grant cho cùng revision đề nghị | Ràng buộc intent ngăn thực thi hai lần |
| Lỗi sau cập nhật CONSUMED, trước ghi intent hoặc commit | Rollback toàn bộ |
| Commit thành công nhưng mất phản hồi | Retry trả intent cũ |
| Retry sau rollback gặp policy mới | Kiểm tra lại dữ liệu và chính sách hiện hành |
| Trần bị hạ hoặc người duyệt mất quyền trước khi dùng | Dừng theo chính sách hiện hành của ví dụ |
| Thu hồi đua với tiêu thụ | Một thứ tự hợp lệ, không vừa thu hồi thành công vừa cấp intent trái quy tắc |
| Cùng nhóm cộng gộp có nhiều request đồng thời | Không vượt tổng qua tuyến thấp nếu có chính sách cộng gộp |
| Dịch vụ ngoài timeout | Không tự mở lại grant để gây tác động lần hai |
| Worker outbox nhận trùng | Không tạo tác động nghiệp vụ mới ngoài intent |

### 14.2. Kiểm thử ranh giới không chỉ có số tiền

Ngoài T − 1, T, T + 1 và E − 1, E, E + 1 theo đơn vị chuẩn, còn cần kiểm tra:

- Revision trước và sau một lần sửa nội dung.
- Trước hạn, đúng hạn và sau hạn.
- Quyền còn hiệu lực và quyền vừa bị thu hồi.
- Một người, hai người và hai tài khoản của cùng người.
- Grant chưa dùng, đang cạnh tranh và đã tiêu thụ.
- Policy_version cũ và hiện hành.
- Kết quả đã commit và kết quả của transaction bị rollback.

Với tiền tệ có đơn vị nhỏ hoặc quy đổi, dùng đơn vị chuẩn thật của chính sách thay vì mặc định sai số một đồng.

### 14.3. Kiểm thử đồng thời trên dữ liệu thật

Các kịch bản transaction nên chạy bằng nhiều connection trên hệ quản trị mục tiêu. Có thể điều phối:

1. Transaction A giữ grant và đề nghị trước khi tiêu thụ.
2. Transaction B cố thực thi hoặc thu hồi cùng đối tượng.
3. Cho A commit hoặc rollback theo từng kịch bản.
4. Cho B tiếp tục rồi quan sát quyết định đã được đọc lại.
5. Truy vấn dữ liệu đã commit để kiểm tra invariant.

Dùng barrier, latch hoặc cơ chế điều phối phù hợp; không chỉ gửi vài request tuần tự hoặc sleep ngẫu nhiên.

Sau kiểm thử, cần khẳng định:

~~~text
Một revision đề nghị có tối đa một execution intent hữu hiệu.

Mỗi grant CONSUMED trỏ đến đúng intent đã commit.

Mỗi intent đi theo tuyến ngoại lệ có đúng grant,
đúng nội dung và bằng chứng cấp quyền tương ứng.

Không có thay đổi riêng lẻ còn sót sau rollback.

Quota và tổng hợp khớp các quyết định đang được tính theo chính sách.
~~~

Khi đối soát nhiều bảng, cần một ảnh chụp nhất quán hoặc cơ chế đồng bộ phù hợp. Không đọc các phần ở hai phía của một commit rồi kết luận dữ liệu bị lệch.

Mock repository có thể kiểm tra đường rẽ của service, nhưng không chứng minh khóa, ràng buộc duy nhất và rollback đang bảo vệ dữ liệu thật.

## 15. Audit và phát hiện lạm dụng

Nhật ký một quyết định ngoại lệ nên cho biết:

- Ai xin, ai duyệt và ai khởi tạo thực thi.
- Tenant, đề nghị, revision và digest.
- Ngưỡng thông thường, trần ngoại lệ và tổng tiền đã dùng để xét.
- Tiền tệ, dữ liệu quy đổi hoặc quy tắc làm tròn liên quan.
- Loại ngoại lệ, điều khoản, reason_code và phiên bản chính sách.
- Các điều kiện độc lập và thẩm quyền đã được kiểm tra.
- Thời điểm cấp, hết hạn, thu hồi hoặc tiêu thụ.
- Intent, idempotency và sự kiện tích hợp liên quan.

Lưu dữ liệu có quyền truy cập và chính sách lưu trữ phù hợp. Không ghi token xác thực, khóa bí mật hoặc toàn bộ dữ liệu nhạy cảm vào log.

Các tín hiệu đáng quan sát:

- Tần suất ngoại lệ tăng đột ngột theo đơn vị hoặc nhóm người duyệt.
- Nhiều giá trị sát ngưỡng hoặc sát trần ngoại lệ.
- Đề nghị bị sửa ngay sau khi duyệt.
- Nhiều lần thử dùng grant sai tenant, sai request hoặc sai revision.
- Tỷ lệ thu hồi, hết hạn và tiêu thụ.
- Những cặp người duyệt xuất hiện bất thường.
- Nhiều intent bị retry hoặc có trạng thái tích hợp chưa đối soát.
- Sai lệch giữa grant đã dùng và intent tương ứng.

Tín hiệu gần ngưỡng không tự chứng minh gian lận. Nó giúp chọn trường hợp cần kiểm tra và đánh giá chính sách.

Không dùng từng exception_id hoặc request_id làm nhãn metric có số lượng giá trị không giới hạn. Dùng metric tổng hợp cho vận hành và log được kiểm soát để điều tra đối tượng cụ thể.

Audit phải giữ được lịch sử gốc. Người có quyền thay đổi chính sách không nên có một đường im lặng sửa lại quyết định cũ để che giấu một lần vượt ngưỡng.

## 16. Tự phân tích tình huống

Đề nghị R có revision 7, tổng 120 triệu VND và grant G đã đủ hai quyết định ngoại lệ độc lập.

| Thao tác tiếp theo | Cách xử lý đúng theo ví dụ |
| --- | --- |
| Người tạo tăng tiền lên 200 triệu, vẫn dưới trần 250 triệu | Không dùng G cũ; nội dung được duyệt đã thay đổi |
| Một request khác dùng G cho đề nghị S cùng số tiền | Từ chối vì sai đối tượng |
| Người duyệt ngoại lệ mất thẩm quyền trước khi G được dùng | Dừng và xét lại theo chính sách hiện hành đã chọn |
| Client gửi cùng request với key mới sau commit | Không tạo intent mới; ràng buộc nghiệp vụ vẫn bảo vệ |
| Worker bên ngoài timeout sau khi intent đã commit | Tra cứu và đối soát intent, không tự mở lại G |
| Hai đề nghị 60 triệu được tạo cho cùng nhu cầu | Xét chính sách cộng gộp nếu có; không tự suy ra từ ngưỡng mỗi phiếu |
| Quản trị viên muốn duyệt trường hợp 300 triệu bằng G | Từ chối vì vượt trần của loại ngoại lệ này; phải dùng quy trình được phép khác |
| Muốn hủy sau khi G đã CONSUMED | Xử lý vòng đời intent và tác động thực tế, không chỉ đổi grant sang REVOKED |

Điểm cần giải thích trong mỗi trường hợp là quyền đã cấp cho **nội dung nào** và **quyết định nào**, chứ không chỉ người dùng có một role mang tên APPROVER hay không.

## 17. Checklist áp dụng

- Ngưỡng áp dụng theo đề nghị, nhu cầu, đơn vị hay kỳ nào?
- Điểm bằng ngưỡng và bằng trần được xử lý đúng ngôn ngữ chính sách chưa?
- Có phân biệt chuyển cấp chuẩn với ngoại lệ không?
- Điều kiện nào không được override trong luồng ngoại lệ?
- Số tiền, tiền tệ và thành phần tổng có do máy chủ xác minh không?
- Ai được xin, duyệt, thu hồi và sử dụng grant?
- Tính độc lập có kiểm tra danh tính và quan hệ xung đột không?
- Grant có gắn đúng tenant, request, revision, nội dung và số tiền không?
- Thay đổi sau duyệt có làm mất hiệu lực quyết định cũ đúng cách không?
- Chính sách và thẩm quyền được kiểm tra theo phiên bản nào tại lúc dùng?
- Tiêu thụ grant, tạo intent, cập nhật đề nghị và idempotency có cùng transaction không?
- Có ràng buộc duy nhất ngăn hai intent cho cùng nội dung không?
- Nếu có cộng gộp hoặc quota, các yêu cầu đồng thời có cùng bị kiểm soát không?
- Hết hạn, thu hồi và retry có giữ nguyên invariant dùng một lần không?
- Lỗi bên ngoài có được đối soát mà không tự mở lại quyền đã tiêu thụ không?
- Audit có chứng minh được căn cứ, người duyệt và nội dung của từng ngoại lệ không?

Một ngoại lệ an toàn là một quyết định được cấp trong phạm vi hẹp và được kiểm tra lại tại điểm sử dụng. Nó cho phép giải quyết một trường hợp được chính sách chấp nhận, đồng thời giữ nguyên quyền theo đối tượng, nội dung đã duyệt và tính nhất quán của toàn bộ workflow.
