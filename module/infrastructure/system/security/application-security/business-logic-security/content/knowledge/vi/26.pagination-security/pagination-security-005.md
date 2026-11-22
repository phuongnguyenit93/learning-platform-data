# Cross page consistency — Tính nhất quán giữa các trang dữ liệu

## 1. Một lần duyệt danh sách là nhiều lần quan sát hệ thống

Trong chương **Pagination Security** của Business Logic Security, cross page consistency là việc các trang trong cùng một lần duyệt tuân theo một hợp đồng thống nhất về tập đối tượng, thứ tự, phiên bản dữ liệu và phạm vi quyền.

Một request có thể trả đúng dữ liệu tại thời điểm nó chạy nhưng cả chuỗi trang vẫn tạo ra kết quả sai. Người dùng có thể thấy một đơn hai lần, bỏ sót một đơn, cộng giá trị từ nhiều thời điểm hoặc tiếp tục đọc bằng quyền đã bị thu hồi.

Ví dụ, người duyệt mở danh sách đơn đang chờ, đọc trang đầu rồi đọc trang tiếp theo. Trong khoảng đó, một đơn được thêm vào đầu danh sách, một đơn khác được sửa để đổi vị trí và một đơn được bàn giao sang người khác. Nếu API chỉ dùng số trang, tập mà người duyệt thực sự đã xem có thể khác hẳn tập mà giao diện tuyên bố “đã xem tất cả”.

Trong phạm vi module này, vấn đề không dừng ở trải nghiệm danh sách. Nó có thể ảnh hưởng việc phát hiện đơn bất thường, xác nhận giá, tách biệt nhiệm vụ hoặc lựa chọn đối tượng cho một lệnh hàng loạt. Vì vậy, cần định nghĩa rõ mức nhất quán được bảo đảm, rồi kiểm thử các thay đổi có chủ đích giữa các trang.

## 2. Định nghĩa hợp đồng trước khi chọn offset hay cursor

### 2.1. Bốn chiều nhất quán khác nhau

| Chiều | Câu hỏi cần trả lời | Ví dụ lỗi |
| --- | --- | --- |
| Thành viên | Những đối tượng nào thuộc lần duyệt này? | Một đơn mới bất ngờ xuất hiện ở trang sau của báo cáo đã chốt |
| Thứ tự | Đối tượng đứng trước hay sau mốc nào? | Sửa `updatedAt` khiến đơn chưa đọc nhảy lên trước cursor |
| Giá trị | Mỗi đối tượng được đọc ở phiên bản nào? | Trang đầu dùng giá cũ, trang sau dùng giá mới |
| Quyền | Actor được phép đọc gì tại điểm quyết định nào? | Cursor cũ tiếp tục trả đơn đã đổi owner |

Một khóa sort duy nhất chỉ giải quyết một phần của chiều thứ tự. Một cursor hợp lệ không tự giải quyết ba chiều còn lại.

### 2.2. Hai hợp đồng thường gặp

**Danh sách theo dữ liệu hiện hành:** mỗi request xét tập dữ liệu và quyền ở thời điểm đọc của request đó. Có thể không bảo đảm tập thành viên cố định trong cả lần duyệt. API cần nói rõ điều gì có thể thay đổi, đặc biệt khi dữ liệu vào/ra bộ lọc hoặc khóa sort có thể sửa.

**Danh sách theo snapshot:** xác định một tập có thứ tự và các giá trị tại một mốc dữ liệu. Các trang đọc cùng snapshot cho tới khi hết hạn hoặc bị vô hiệu hóa. Quyền tiếp tục đọc snapshot là một quyết định riêng, không mặc nhiên được đóng băng cùng dữ liệu.

Không phải danh sách nào cũng cần snapshot. Một màn hình theo dõi liên tục có thể dùng dữ liệu hiện hành. Một bản đối soát hoặc hồ sơ “đã kiểm tra toàn bộ N đơn” thường cần bảo đảm mạnh hơn.

### 2.3. Oracle cho một snapshot cố định

Gọi S là danh sách có thứ tự đã được chụp. Khi dữ liệu snapshot và quyền đọc nó vẫn hợp lệ, chuỗi trang cần thỏa:

```text
Mọi trang có cùng định danh snapshot và cùng ngữ nghĩa truy vấn.
Mỗi item mang giá trị đã được chụp, không trộn với giá trị live tùy trang.
Các đoạn liên tiếp không trùng item và không bỏ qua item của S.
Ghép tất cả trang theo thứ tự sẽ thu được đúng S.
Metadata tổng hợp được tính từ S, không từ tập live khác.
```

Với danh sách hiện hành, không được áp dụng nguyên bộ oracle này rồi kết luận mọi thay đổi tập thành viên đều là lỗi. Test phải đối chiếu đúng lời hứa của endpoint.

## 3. Offset bị dịch chuyển như thế nào?

Giả sử danh sách giảm dần theo thời điểm tạo, kích thước trang là 2:

```text
Ban đầu: A, B, C, D, E, F
Trang 0 với OFFSET 0: A, B
```

### 3.1. Thêm một dòng phía trước gây lặp

Trước khi lấy trang 1, X được thêm vào đầu:

```text
Hiện tại: X, A, B, C, D, E, F
Trang 1 với OFFSET 2: B, C
```

B xuất hiện lần hai. Nếu client cộng giá trị của từng trang mà không phát hiện trùng, tổng có thể sai. Việc loại trùng ở client không chứng minh đã lấy đủ tập ban đầu.

### 3.2. Xóa một dòng phía trước gây bỏ sót

Trở lại dữ liệu ban đầu, sau trang A, B thì A bị xóa:

```text
Hiện tại: B, C, D, E, F
Trang 1 với OFFSET 2: D, E
```

C chưa từng được trả nhưng đã bị bỏ qua. Số lượng trang hoặc việc không có ID trùng không phát hiện được lỗi thiếu này.

### 3.3. Tác động an ninh nghiệp vụ

Nếu một quy trình coi việc client đi hết các trang là bằng chứng đã xem toàn bộ đơn rủi ro, một người có khả năng tạo, sửa hoặc di chuyển dữ liệu có thể tác động tới tập thực tế được xem. Server không nên nhận một cờ `reviewedAll=true` rồi suy ra toàn bộ tập đối tượng đã được kiểm tra đầy đủ.

Tương tự, thao tác duyệt hoặc hủy vẫn phải xác minh đối tượng, phiên bản và trạng thái ở thời điểm thực thi. Một lỗi phân trang không được trở thành đường bỏ qua invariant của lệnh ghi.

## 4. Thứ tự ổn định và keyset giải quyết được đến đâu?

### 4.1. Dùng một thứ tự xác định duy nhất

Nếu nhiều dòng có cùng thời gian tạo, chỉ dùng `ORDER BY created_at DESC` chưa xác định thứ tự giữa chúng. Có thể thêm khóa duy nhất:

```sql
ORDER BY o.created_at DESC, o.id DESC
```

PostgreSQL lưu ý rằng `LIMIT`/`OFFSET` cần một thứ tự có thể dự đoán để chọn các phần của kết quả một cách xác định. Xem [PostgreSQL — LIMIT and OFFSET](https://www.postgresql.org/docs/18/queries-limit.html).

Tie-breaker phải có ngữ nghĩa so sánh phù hợp với database. Nếu key có null, chiều sort khác nhau hoặc kiểu dữ liệu đặc biệt, điều kiện tiếp tục cũng phải phản ánh đúng cách sắp xếp đó.

### 4.2. Keyset tiếp tục từ giá trị, không từ số dòng đã bỏ qua

Với `created_at` và `id` không null, cùng sort giảm dần, một truy vấn tiếp tục có dạng:

```sql
SELECT o.id, o.reference, o.status, o.created_at, o.version
FROM purchase_order o
WHERE o.tenant_id = :trusted_tenant
  AND o.owner_id = :trusted_actor
  AND o.deleted = false
  AND o.status = :requested_status
  AND (
    o.created_at < :last_created_at
    OR (o.created_at = :last_created_at AND o.id < :last_id)
  )
ORDER BY o.created_at DESC, o.id DESC
LIMIT :size_plus_one;
```

Với ví dụ A, B rồi thêm X phía trước, mốc B giúp trang tiếp theo tìm các dòng phía sau B thay vì bỏ qua hai dòng đầu của danh sách mới. Điều này tránh kiểu dịch chuyển offset đã minh họa.

Tuy nhiên, keyset không tự bảo đảm đọc đúng một tập cố định:

- Một dòng mới được thêm với khóa nằm sau mốc vẫn có thể xuất hiện ở trang sau.
- Một dòng chưa đọc bị xóa hoặc không còn khớp bộ lọc sẽ biến mất.
- Một dòng chưa đọc đổi khóa sort để nhảy lên trước mốc có thể bị bỏ qua.
- Một dòng đã đọc đổi khóa để nhảy xuống sau mốc có thể xuất hiện lại.
- Giá trị như số tiền hoặc trạng thái có thể đổi dù khóa sort không đổi.

Chọn khóa bất biến giúp giảm nguy cơ di chuyển, nhưng không cố định thành viên hay giá trị của cả lần duyệt.

### 4.3. High-water mark không đồng nghĩa snapshot

Một thiết kế có thể ghi lại khóa lớn nhất hoặc mốc thời gian bắt đầu, rồi chỉ lấy dữ liệu dưới mốc đó. Nó giúp chặn một số bản ghi mới nằm phía trên biên, nhưng không giữ lại dòng đã xóa hoặc giá trị trước khi sửa.

`created_at <= startedAt` cũng không chứng minh “đã tồn tại và được nhìn thấy khi bắt đầu”. Dữ liệu có thể được backdate, hoặc một transaction tạo trước mốc nhưng commit sau lần đọc đầu. Tương tự, giá trị sequence lớn nhất không phải một phiên bản commit toàn cục của tập dữ liệu.

Vì vậy, cần mô tả chính xác biên high-water hạn chế điều gì. Không gắn nhãn snapshot đầy đủ chỉ vì cursor chứa thời gian bắt đầu.

## 5. Snapshot cần giữ thành viên và giá trị nào?

### 5.1. Chỉ lưu danh sách ID chưa giữ được nội dung lịch sử

Giả sử snapshot lưu thứ tự A, B, C, D nhưng mỗi trang lại tải các entity hiện hành. Tập ID có thể ổn định, còn giá hoặc trạng thái vẫn thay đổi. Client đang đọc một danh sách cố định với nội dung live, không phải một bản chụp đầy đủ.

Nếu hợp đồng yêu cầu giá trị tại thời điểm chụp, cần một trong các khả năng:

- Lưu projection cần hiển thị vào một snapshot bất biến.
- Lưu tham chiếu tới những phiên bản lịch sử mà hệ thống có thể đọc lại đúng.
- Dùng cơ chế snapshot/PIT của kho dữ liệu với vòng đời và giới hạn đã được kiểm soát.

Lưu `orderVersion = 7` chỉ hữu ích để đọc lại nội dung V7 nếu kho dữ liệu thực sự giữ được V7. Một field version phục vụ optimistic locking không tự lưu lịch sử entity.

### 5.2. Mô hình snapshot lưu phía server

Một mô hình minh họa cho đơn mua hàng:

```text
ListSnapshot
  snapshotId
  tenantId, actorId, endpointKind
  normalizedQueryFingerprint, sortVersion
  capturedAt, expiresAt
  authorizationRevision
  itemCount
  state: BUILDING | READY | EXPIRED

ListSnapshotItem
  snapshotId, ordinal
  orderId, sourceVersion
  reference, status, amount, currency
  các field projection được phép chụp
```

Có thể đặt ràng buộc duy nhất cho `(snapshotId, ordinal)` và `(snapshotId, orderId)` nếu mỗi đơn chỉ được xuất hiện một lần. `ordinal` xác định vị trí trong bản chụp, không được tái tính theo dữ liệu live ở mỗi trang.

`sourceVersion` giúp nhận biết đối tượng được quan sát ở phiên bản nào. Nó không phải giấy cho phép áp dụng lệnh ở phiên bản đó sau khi dữ liệu đã thay đổi.

### 5.3. Giữ snapshot bất biến sau khi công bố

Không sửa nội dung item READY để “cập nhật cho mới” rồi giữ nguyên snapshot ID. Nếu dữ liệu cần được làm mới, tạo một lần duyệt khác theo hợp đồng.

Cần phân biệt rõ snapshot dữ liệu và dữ liệu vận hành như thời điểm truy cập cuối, trạng thái hết hạn hoặc audit. Những metadata vận hành đó có thể thay đổi mà không làm projection lịch sử trở thành dữ liệu live.

## 6. Chụp nhất quán ngay từ bước tạo snapshot

### 6.1. Đừng xây snapshot bằng các trang live không được bảo vệ

Nếu worker đọc 1.000 dòng đầu, commit, rồi đọc 1.000 dòng tiếp theo từ tập đang thay đổi, nó có thể đã thu được một tập trùng hoặc thiếu trước khi snapshot READY. Việc lưu kết quả ấy vào bảng bất biến chỉ đóng băng một tập sai.

Với một snapshot nhỏ trong cùng database, luồng tạo có thể là:

1. Xác thực actor, tenant và quyền tạo loại danh sách đó.
2. Chuẩn hóa bộ lọc, sort và phạm vi projection được phép.
3. Mở transaction có mức nhất quán phù hợp để chụp dữ liệu nguồn và revision quyền liên quan.
4. Tạo metadata BUILDING và đọc tập hợp lệ theo thứ tự xác định, với giới hạn số dòng/chi phí.
5. Lưu projection cùng ordinal, số lượng và mốc mô tả lần chụp.
6. Chuyển READY trong cùng ranh giới commit phù hợp.
7. Chỉ sau khi commit thành công mới cung cấp handle/cursor dùng để đọc snapshot.

Nếu quá giới hạn, rollback hoặc chuyển sang quy trình export được thiết kế riêng. Không âm thầm cắt mất dữ liệu rồi báo đã chụp đầy đủ.

### 6.2. Isolation trong database không tự kéo dài qua nhiều request

Trong PostgreSQL Read Committed, các câu SELECT kế tiếp có thể thấy các commit khác nhau. Repeatable Read giữ một snapshot cho transaction tương ứng. Hai request HTTP mở hai transaction riêng không tự dùng chung snapshot, dù cùng khai báo Repeatable Read hoặc Serializable. Xem [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/18/transaction-iso.html).

Do đó, `@Transactional` trên phương thức lấy từng trang không đủ để giữ toàn bộ lần duyệt đứng yên. Nó chỉ là một công cụ cho phạm vi transaction thực sự được mở.

PostgreSQL có cơ chế export/import snapshot, nhưng snapshot chỉ còn khả dụng để import khi transaction đã export nó vẫn mở. Chi tiết nằm trong [PostgreSQL — Snapshot Synchronization Functions](https://www.postgresql.org/docs/18/functions-admin.html#FUNCTIONS-SNAPSHOT-SYNCHRONIZATION).

Đối với luồng người dùng có thể dừng nhiều phút giữa các trang, không nên mặc nhiên giữ transaction/connection mở suốt phiên duyệt. Cần cân nhắc bản chụp vật hóa, kho dữ liệu hỗ trợ snapshot có vòng đời phù hợp hoặc hợp đồng live rõ ràng.

### 6.3. Nhiều nguồn dữ liệu cần mốc riêng được phối hợp

Một snapshot SQL không tự đóng băng giá từ API khác hoặc trạng thái từ search index. Nếu response ghép nhiều nguồn, phải xác định dữ liệu nào được chụp, cách lưu giá trị đã dùng và ý nghĩa của mốc thời gian.

Trong Elasticsearch, tài liệu phân trang mô tả việc refresh giữa các lần `search_after` có thể làm kết quả không nhất quán, và PIT giúp giữ trạng thái index cho chuỗi truy vấn. Xem [Elasticsearch — Paginate search results](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/paginate-search-results).

PIT của index không tự là snapshot của database nghiệp vụ. Nếu lấy ID từ PIT rồi tải giá live từ SQL, cần mô tả đó là hai lớp quan sát khác nhau hoặc lưu lại projection nhất quán theo thiết kế.

## 7. Snapshot dữ liệu không đóng băng quyền đọc

### 7.1. Chọn chính sách khi quyền thay đổi

Giả sử Lan tạo snapshot chứa đơn O-101, sau đó đơn được bàn giao cho Minh. Có ít nhất hai hướng thiết kế rõ ràng:

| Hướng | Hành vi khi phạm vi đọc thay đổi | Điều cần giữ |
| --- | --- | --- |
| Tiếp tục với quyền hiện hành | Loại hoặc xử lý đối tượng không còn được phép theo hợp đồng | Metadata, cursor và khả năng thiếu item phải có ngữ nghĩa phù hợp |
| Vô hiệu hóa lần duyệt | Yêu cầu tạo snapshot mới | Không trả tiếp dữ liệu cũ hoặc âm thầm chuyển sang tập mới |

Trong ví dụ snapshot nghiêm ngặt của bài, ứng dụng chọn **vô hiệu hóa lần duyệt nếu phạm vi quyền liên quan thay đổi**. Khi còn hợp lệ, các trang giữ nguyên S. Khi không còn hợp lệ, request kết thúc bằng lỗi yêu cầu bắt đầu lại, không lọc bớt tùy trang nhưng vẫn quảng bá tổng cũ như chưa có gì xảy ra.

Một hệ thống có thể cho phép xem báo cáo lịch sử bằng quyền riêng. Khả năng đó phải được cấp rõ ràng; không suy ra từ việc người gọi từng có cursor hợp lệ.

### 7.2. Revision quyền phải phản ánh đủ đầu vào của policy

Ví dụ có thể lưu `authorizationRevision` trong snapshot và kiểm tra lại khi đọc. Để cách này có giá trị, mọi thay đổi ảnh hưởng quyền liên quan phải cập nhật revision đúng cơ chế nhất quán:

```text
membership hoặc trạng thái tài khoản
owner, grant, quan hệ phân công
vai trò và policy
quyền xem từng field
trạng thái/xóa mềm nếu các thuộc tính đó chi phối quyền đọc
```

Một revision chỉ tăng khi sửa role không phát hiện được đơn đổi owner. Revision quyền cũng khác revision dữ liệu: thêm một đơn mới không nhất thiết làm thay đổi quyền đọc các item đã chụp, còn đổi owner của item cũ có thể làm snapshot không còn được tiếp tục.

Có thể dùng revision tenant tăng bảo thủ để đơn giản hóa, nhưng nó có thể làm nhiều snapshot bị vô hiệu hóa thường xuyên. Phân nhỏ phạm vi revision là một lựa chọn tối ưu, với điều kiện vẫn bao phủ đủ quan hệ quyền.

Nếu không thể chứng minh revision bao phủ đầy đủ policy, cần kiểm tra lại quyền bằng cơ chế khác hoặc không công bố bảo đảm tương ứng. Không dùng một số version tùy ý như bằng chứng toàn bộ quyền vẫn giữ nguyên.

### 7.3. Xác định điểm quyết định của request

Việc kiểm tra quyền và lấy trang cần theo một điểm quan sát/cơ chế phối hợp đã định nghĩa. Ví dụ cùng đọc revision và metadata trong một transaction nhất quán ở đầu request. Một thay đổi quyền commit sau điểm đó được xử lý theo chính sách đồng thời đã công bố; không hứa thu hồi dữ liệu đã gửi trước đó.

Cache quyền và trạng thái job phải tuân theo cùng cam kết. Một TTL dài hơn thời gian thu hồi được yêu cầu không tự đáp ứng cam kết chỉ vì token chưa hết hạn.

## 8. Token, metadata và cache phải giữ cùng một lần duyệt

### 8.1. Ràng buộc ý nghĩa truy vấn

Token tiếp tục của thiết kế snapshot có thể tham chiếu tới:

```text
snapshotId
vị trí sau ordinal cuối đã trả
phiên bản định dạng token
định danh/băm của truy vấn và sort
thời hạn và các ràng buộc ngữ cảnh cần thiết
```

Server giữ metadata actor, tenant và phạm vi quyền của snapshot. Trên mỗi request, phải đối chiếu người gọi hiện tại với phạm vi đó và kiểm tra quyền tiếp tục đọc.

Google AIP-158 nêu rõ page token chỉ mô tả vị trí tiếp tục và không cấp quyền truy cập tài nguyên. Xem [AIP-158 — Pagination](https://google.aip.dev/158).

Không thay trạng thái bộ lọc hoặc sort giữa chừng rồi tiếp tục dùng cùng mốc mà không có quy tắc rõ. Bộ lọc cần được chuẩn hóa theo ngữ nghĩa trước khi tính fingerprint; hai chuỗi URL khác cách sắp tham số có thể biểu diễn cùng truy vấn.

### 8.2. Token hỏng hoặc hết hạn không được khởi động lại ngầm

Nếu cursor sai, snapshot hết hạn hoặc query không khớp, trả lỗi đúng hợp đồng. Không tự bỏ cursor rồi trả trang đầu live: client có thể nối trang đầu mới vào các trang cũ và tạo kết quả trùng, thiếu hoặc trộn giá trị.

Tương tự, khi client retry cùng một token còn hợp lệ trên snapshot bất biến và quyền không đổi, nó phải nhận cùng đoạn dữ liệu có cùng ý nghĩa. Cursor nên biểu diễn vị trí, không âm thầm bị “tiêu thụ” để retry nhảy sang trang khác trong API đọc này.

Các chuỗi token trả lại có thể khác về nonce hoặc cách mã hóa. Điều cần so sánh trong test là snapshot, vị trí và dữ liệu, không nhất thiết là từng byte token.

### 8.3. Metadata và cache không được trộn snapshot

`totalElements`, tổng tiền hoặc phân bố trạng thái cần lấy từ cùng snapshot/projection theo hợp đồng. Không dùng count live cho một trang snapshot rồi trình bày như cùng thời điểm.

Cache key phải phân biệt ít nhất những yếu tố làm đổi kết quả: snapshot hoặc chế độ live, tenant, actor/phạm vi quyền, query, sort và vị trí đọc. Cache không được phục vụ lại dữ liệu từ snapshot đã bị vô hiệu hóa chỉ vì mục cache chưa hết TTL.

Nếu sản phẩm cho phép đổi page size giữa các request, ordinal vẫn phải tiếp tục từ dòng cuối đã trả và size phải nằm trong giới hạn. Nếu sản phẩm chọn cố định size trong một lần duyệt, hãy ràng buộc và kiểm tra nó. Cả hai đều cần hợp đồng rõ, thay vì để mỗi lớp tự diễn giải.

## 9. Minh họa Java: đọc trang từ snapshot bất biến

Đoạn mã sau minh họa phần đọc tiếp sau khi snapshot đã được tạo và commit. Các kiểu domain, repository, cursor codec và policy là thành phần cần tự hiện thực; đây không phải một lớp có thể chép vào mọi dự án rồi chạy ngay.

```java
@Transactional(
    readOnly = true,
    isolation = Isolation.REPEATABLE_READ,
    propagation = Propagation.REQUIRES_NEW
)
public SnapshotPage nextPage(
        ListOrdersQuery request, String token, int size) {
    if (size < 1 || size > 100) {
        throw new InvalidPageRequestException();
    }

    Actor actor = currentActor.requireActiveTenantActor();
    Cursor cursor = cursorCodec.verifyAndDecode(token, clock.instant());
    ListSnapshot snapshot = snapshots.find(cursor.snapshotId())
        .orElseThrow(SnapshotUnavailableException::new);

    authorization.requireSnapshotReader(actor, snapshot);
    snapshot.requireReadyAndUnexpired(clock.instant());

    NormalizedQuery query = queryNormalizer.normalize(request);
    snapshot.requireQuery(query.fingerprint());
    cursor.requireMatches(snapshot, query);
    cursor.requirePositionBetween(0, snapshot.itemCount());

    long currentRevision = authorization.requireCurrentReadScope(actor).revision();
    if (currentRevision != snapshot.authorizationRevision()) {
        throw new RestartListingRequiredException();
    }

    List<SnapshotItem> window = items.findAfterOrdinal(
        snapshot.id(), cursor.afterOrdinal(), size + 1);
    boolean hasNext = window.size() > size;
    List<SnapshotItem> returned = List.copyOf(
        window.subList(0, Math.min(size, window.size())));

    String nextToken = null;
    if (hasNext) {
        long after = returned.get(returned.size() - 1).ordinal();
        nextToken = cursorCodec.encodeNext(snapshot, query, after);
    }

    return new SnapshotPage(
        snapshot.id(),
        snapshot.capturedAt(),
        snapshot.itemCount(),
        returned.stream().map(SnapshotItem::view).toList(),
        nextToken
    );
}
```

Truy vấn item có thể dựa trên ordinal đã cố định:

```sql
SELECT ordinal, order_id, source_version,
       reference, status, amount, currency
FROM list_snapshot_item
WHERE snapshot_id = :authorized_snapshot_id
  AND ordinal > :after_ordinal
ORDER BY ordinal ASC
LIMIT :size_plus_one;
```

Những điều kiện để ví dụ bảo đảm đúng hợp đồng:

1. Mọi field cần hiển thị đã được chụp; `view()` trả DTO bất biến từ snapshot item, không tải lại entity live.
2. Header READY, item và tổng đã được công bố nhất quán. Item của snapshot READY không bị sửa/xóa từng phần trong thời gian còn phục vụ.
3. `requireSnapshotReader` kiểm tra actor, tenant và quyền dùng loại danh sách trước khi trả metadata ra response. ID khó đoán không thay thế kiểm tra này.
4. `requireCurrentReadScope` thực sự kiểm tra quyền hiện hành và revision bao phủ đủ đầu vào policy như phần trước. Ví dụ giả định trạng thái cần thiết được đọc/phối hợp nhất quán với transaction này.
5. `cursorCodec` giới hạn kích thước input, kiểm tra định dạng, tính toàn vẹn hoặc tham chiếu server-side và thời hạn. Không tin các field actor/tenant do token chưa xác minh khai báo.
6. Dòng dư chỉ dùng xác định còn dữ liệu. Token tiếp theo đi từ ordinal của dòng cuối đã trả, tránh bỏ qua dòng dư.
7. Lỗi hết hạn, sai query hoặc đổi quyền được ánh xạ thành lỗi API rõ ràng; không bắt exception rồi chuyển sang truy vấn live.

Các thuộc tính `isolation` và `propagation` thuộc annotation của Spring. Phương thức phải được gọi qua cơ chế transaction thực tế; self-invocation trong proxy mode không tự kích hoạt interceptor. Xem [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html).

Transaction đọc này giúp giữ điểm quan sát của request, không phải nguồn tạo ra snapshot dữ liệu xuyên request. Bảo đảm xuyên trang đến từ dữ liệu snapshot bất biến đã được tạo trước đó và giao thức tiếp tục được kiểm tra.

## 10. Không dùng lần duyệt làm bằng chứng cho lệnh ghi

Một snapshot danh sách đơn đang chờ có thể giữ trạng thái lịch sử PENDING của O-101 dù đơn hiện hành đã được duyệt. Điều đó đúng với báo cáo tại thời điểm chụp nếu quyền đọc lịch sử vẫn hợp lệ. Nó không cho phép duyệt O-101 lần nữa.

Khi người dùng gửi lệnh từ các item đã xem, server cần kiểm tra lại:

- Quyền thực hiện action trên đối tượng hiện hành.
- Tenant, owner, phân công và quy tắc không tự duyệt.
- Trạng thái và phiên bản được phép chuyển.
- Giá/hạn mức có thẩm quyền và invariant toàn nhóm nếu là batch.
- Idempotency của lệnh và tác động phụ khi gửi lại.

Nếu yêu cầu là “duyệt đúng tập đã xem”, có thể gắn lệnh với manifest chứa ID và phiên bản nguồn. Khi một phiên bản không còn phù hợp, xử lý xung đột theo hợp đồng. Không âm thầm thay thế bằng dữ liệu live khác rồi vẫn ghi rằng người duyệt đã chấp thuận đúng nội dung cũ.

Việc đi hết cursor cũng không chứng minh một người đã đọc hoặc hiểu nội dung. Nếu cần bằng chứng phê duyệt, đó là một quyết định nghiệp vụ riêng có chủ thể, phạm vi và dữ liệu được chấp thuận.

## 11. Kiểm thử với thay đổi được điều phối giữa các trang

### 11.1. Tạo oracle từ dữ liệu fixture

Với snapshot nghiêm ngặt, chuẩn bị tập S có ID, thứ tự, phiên bản và projection xác định. Oracle không được tính bằng chính hàm pagination đang được kiểm tra.

Các assertion nền:

```text
mọi page có cùng snapshotId và capturedAt theo hợp đồng
ID mỗi page đúng thứ tự, không trùng giữa các đoạn liên tiếp
ghép hết page bằng đúng S khi snapshot và quyền còn hợp lệ
giá trị từng item bằng projection đã chụp
count và tổng hợp khớp dữ liệu snapshot
request đọc không tạo quyết định duyệt hoặc tác động nghiệp vụ mới
```

Đối với danh sách live, viết oracle riêng cho bảo đảm thực sự có. Ví dụ keyset trên khóa bất biến có thể kiểm tra tránh lặp do thêm dòng phía trước, nhưng không tuyên bố nó giữ lại dòng đã bị xóa hoặc mọi giá trị cũ.

### 11.2. Ma trận tình huống

| Tình huống giữa hai trang | Điều cần chứng minh |
| --- | --- |
| Thêm dòng mới trước mốc | Live keyset không bị lặp kiểu offset; snapshot không nhận thêm thành viên |
| Thêm dòng backdate sau mốc | Phân biệt giới hạn high-water/keyset với snapshot thực sự |
| Xóa dòng trước offset | Test bắt được việc bỏ sót do offset nếu endpoint đã hứa duyệt đủ tập cố định |
| Sửa khóa sort của dòng chưa đọc | Không công bố bảo đảm mạnh hơn thuật toán; snapshot giữ ordinal |
| Sửa giá/trạng thái nhưng quyền đọc snapshot còn nguyên | Snapshot trả projection cũ thống nhất, không trộn giá trị live |
| Thay đổi làm mất quyền đọc | Hành vi đúng chính sách: vô hiệu hóa hoặc xử lý hiện hành đã định nghĩa |
| Nhiều dòng có cùng thời gian | Tie-breaker tạo thứ tự duy nhất trên dữ liệu tĩnh |
| Đổi filter/sort với token cũ | Bị xử lý theo hợp đồng, không âm thầm nối hai tập |
| Retry cùng token hợp lệ | Cùng đoạn dữ liệu có cùng ý nghĩa khi snapshot/quyền không đổi |
| Token hết hạn | Lỗi rõ ràng, không fallback sang trang đầu live |
| Cache trang cũ rồi tạo snapshot mới | Không trộn page/metadata của hai snapshot |
| Dùng token của actor/tenant khác | Không được cấp phạm vi của người tạo token |
| Lỗi khi chụp trước READY | Không phục vụ snapshot thiếu item hoặc tổng sai |
| Worker export chạy nhiều chunk | Các chunk dùng đúng cơ chế snapshot, không tự quay về các trang live |

Với thao tác xóa, xác định trước chính sách đọc lịch sử. Nếu xóa làm mất quyền theo policy thì test phải yêu cầu vô hiệu hóa. Không vừa yêu cầu trả bản sao lịch sử vừa yêu cầu thu hồi ngay cùng bản sao đó mà không có quy tắc ưu tiên.

### 11.3. Điều phối thay đổi thay vì đoán thời gian

Một kịch bản tích hợp có thể chạy như sau:

```text
Tạo fixture và commit.
Bắt đầu lần duyệt, lấy trang đầu và lưu token.
Chờ test harness xác nhận trang đầu đã hoàn tất.
Trong transaction khác: thêm/sửa/xóa hoặc đổi quyền; commit.
Dùng đúng token để lấy trang tiếp theo.
Đọc kết quả và dữ liệu bằng giao dịch/nguồn quan sát độc lập phù hợp.
Đối chiếu với oracle của chế độ live hoặc snapshot.
```

Không dùng `Thread.sleep()` rồi kết luận rằng một race nhất định đã xảy ra. Với thay đổi trong lúc tạo snapshot, dùng barrier/latch hoặc fault injection tại điểm được kiểm soát để biết transaction nào đã commit trước mốc chụp.

Test persistence cần database và luồng truy vấn thật phù hợp mục tiêu. Mock trả sẵn một danh sách bất biến không chứng minh isolation, cursor hoặc cache của ứng dụng đúng.

## 12. Vận hành và đọc kết quả đúng mức bảo đảm

### 12.1. Giới hạn tài nguyên của snapshot

Đặt giới hạn số snapshot đang hoạt động theo actor/tenant, số item, kích thước projection, TTL và chi phí tạo. Snapshot có thể chứa dữ liệu nhạy cảm, nên quyền đọc và cơ chế xóa phải được áp dụng cho cả nơi lưu snapshot lẫn file export nếu có.

Dọn dẹp cần theo giao thức rõ ràng: snapshot hết hạn bị từ chối nhất quán, không để header READY còn sống nhưng item đã bị xóa một phần rồi trả một trang rỗng như kết thúc hợp lệ. Với thao tác dọn đồng thời, dùng cơ chế phối hợp phù hợp để request đang phục vụ không quan sát trạng thái dở.

Không ghi toàn bộ token, projection nhạy cảm hoặc thông tin đơn bị cấm vào log. Có thể ghi snapshot ID, fingerprint truy vấn, vị trí, số lượng trả và mã lý do kết thúc theo chính sách audit.

### 12.2. Báo cáo nên chỉ rõ chế độ và điểm quan sát

```text
Case: UPDATE-UNSEEN-ORDER-BETWEEN-PAGES
Mode: materialized snapshot, quyền thay đổi thì yêu cầu restart
Snapshot: S-17, state READY
Initial set: A, B, C, D
Page size: 2
Page 1: A, B
Mutation: sửa amount của C; quyền đọc lịch sử không đổi; commit
Expected page 2: C, D với projection đã chụp trong S-17
Observed: C dùng amount hiện hành, D dùng amount đã chụp
Result: FAIL — cùng snapshot nhưng trộn nguồn giá trị
```

Báo cáo một lỗi offset trong chế độ live không nên tự gán thành vi phạm snapshot nếu endpoint chưa có cam kết đó. Ngược lại, một endpoint được dùng cho đối soát không thể chỉ đổi tên thành cursor để coi vấn đề bỏ sót hoặc trộn phiên bản đã được giải quyết.

Trong CI, tách test dữ liệu tĩnh, test thay đổi dữ liệu, test đổi quyền và test cache/hạ tầng. Mỗi nhóm xác minh một lời hứa cụ thể; assertion đúng ở một nhóm không thay thế các nhóm khác.

## 13. Bài tập thực hành

Một API liệt kê đơn đang chờ có thiết kế:

```text
- ORDER BY updatedAt DESC, pageSize = 20.
- Token chỉ chứa số trang tiếp theo và startedAt.
- Mỗi request mở transaction Repeatable Read riêng.
- totalElements được lấy từ cache live theo tenant.
- Khi token hết hạn, server tự trả trang đầu.
- Client cộng tổng tiền từ các trang rồi gửi reviewedAll=true.
```

Hãy thực hiện các bước thiết kế sau:

1. Chọn rõ đây là danh sách live hay danh sách snapshot phục vụ kiểm tra một tập cố định.
2. Tạo lịch xen kẽ thêm, xóa và sửa `updatedAt` để chỉ ra khả năng lặp hoặc thiếu.
3. Giải thích vì sao `startedAt` và Repeatable Read riêng từng request chưa giữ được cùng tập/giá trị.
4. Thiết kế cursor và metadata cùng một ngữ nghĩa truy vấn, không khởi động lại ngầm khi lỗi.
5. Chọn cách xử lý khi một đơn đổi owner sau trang đầu và xác định đủ đầu vào cần theo dõi để thực hiện lựa chọn đó.
6. Nếu cần snapshot, chỉ rõ cách chụp thành viên, giá trị, ordinal và tổng trước khi công bố READY.
7. Thiết kế lại lệnh xác nhận/duyệt để kiểm tra quyền, phiên bản và trạng thái hiện hành, thay vì tin cờ `reviewedAll`.

Tính nhất quán giữa các trang được bảo đảm khi ứng dụng giữ đúng hợp đồng về tập dữ liệu, thứ tự, giá trị và quyền cho toàn bộ lần duyệt, đồng thời phát hiện rõ lúc không thể tiếp tục giữ hợp đồng đó.
