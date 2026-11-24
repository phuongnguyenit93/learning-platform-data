# Quota delegation: Ủy quyền hạn mức mà không làm tăng tổng ngân sách

## 1. Quota delegation là gì?

Trong chương **Quota Management**, quota delegation là việc một chủ thể được phép phân bổ một phần hạn mức của mình cho chủ thể khác. Ví dụ, tổ chức có 1.000 lượt xuất báo cáo mỗi tháng, cấp 400 lượt cho nhóm A và 300 lượt cho nhóm B. Nhóm A có thể được phép cấp tiếp một phần cho dự án A1.

Đây là quy tắc nghiệp vụ, không chỉ là một thao tác cập nhật số. Nếu hệ thống cho hai nhóm cùng nhận phần ngân sách cuối, trả lại cả quota đã tiêu khi thu hồi hoặc cho cấp tiếp vượt phạm vi, tổng sử dụng có thể vượt hợp đồng dù mỗi request riêng lẻ trông hợp lệ.

Bài thuộc phạm vi **SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY**: bảo vệ business invariant, state machine, quyền theo đối tượng, transaction và idempotency trước việc bỏ qua phê duyệt, sửa tham số, dùng sai quyền và gửi yêu cầu trùng.

Cần tách ba loại quyền:

| Quyền | Ý nghĩa | Không tự bao gồm |
| --- | --- | --- |
| Sử dụng quota | Thực hiện công việc và tiêu một lượng được phép | Quyền cấp quota cho người khác |
| Quản lý phân bổ | Cấp, tăng hoặc nhận lại ngân sách trong phạm vi | Quyền tạo thêm ngân sách gốc |
| Cấp tiếp quyền quản lý | Cho bên nhận được phép phân bổ xuống dưới | Quyền mở rộng tenant, tài nguyên hoặc thời hạn |

Một nhóm có 400 lượt không mặc nhiên có quyền cấp tiếp 400 lượt. Quyền quản lý và số lượng được quản lý phải được kiểm tra độc lập.

## 2. Chọn mô hình trước khi viết công thức

### 2.1. Mô hình dùng trong bài: dành trước ngân sách

Bài dùng **hard quota tiêu hao theo kỳ**, đo bằng số nguyên lượt xuất báo cáo:

- Mỗi cây thuộc một tenant, một loại tài nguyên, một đơn vị và một kỳ.
- Root có ngân sách do hợp đồng hoặc nghiệp vụ mua thêm hợp lệ cấp.
- Khi cấp cho con, cha dành trước lượng đó; cha không còn dùng nó cho việc khác.
- Mỗi node có tối đa một cha trong cùng cây/kỳ.
- Chỉ node được cho phép mới cấp tiếp; giới hạn độ sâu do máy chủ quy định.
- Không chuyển node sang cha khác trong cùng kỳ ở mô hình ví dụ.
- Tất cả thay đổi được quyết định trên một DB chính theo giao thức transaction thống nhất.

Các lựa chọn này giúp nhìn rõ tính bảo toàn. Chúng là chính sách thiết kế của ví dụ, không phải quy định chung cho mọi hệ thống quota.

### 2.2. Đừng trộn với hạn mức dùng chung

Một mô hình khác chỉ đặt trần cho từng nhóm nhưng vẫn cho mọi nhóm tranh ngân sách chung của tổ chức. Khi đó tổng trần nhóm có thể lớn hơn trần root, nhưng mỗi lần sử dụng phải kiểm tra và tiêu ngân sách chung nguyên tử.

Đó là mô hình khác với dành trước. Không vừa cho cha dùng phần đã cấp cho con, vừa để con chỉ kiểm tra số dư riêng, rồi kỳ vọng tổng không vượt root.

Quota theo số lượt tiêu hao cũng khác giới hạn số công việc chạy đồng thời. Một slot chỉ được thu hồi khi công việc không còn giữ nó theo giao thức thực thi; TTL hết không tự chứng minh công việc ở máy khác đã dừng. Bài không dùng mô hình slot đồng thời.

## 3. Ví dụ cây phân bổ và công thức bảo toàn

### 3.1. Ý nghĩa các đại lượng

Với mỗi node trong một kỳ:

~~~text
B = budget_amount       : ngân sách node đang được giữ
U = used_amount         : lượng đã tiêu trực tiếp tại node
R = reserved_amount     : lượng đang giữ chỗ trực tiếp tại node
D = delegated_amount    : tổng ngân sách đang giữ tại các node con trực tiếp
F = free_amount         : phần node còn tự phân bổ hoặc sử dụng được

F = B - U - R - D
~~~

Invariant:

~~~text
B >= 0, U >= 0, R >= 0, D >= 0
U + R + D <= B
D(parent) = SUM(B(child)) trong cùng cây và kỳ
~~~

`U` là lượng dùng **trực tiếp**, không phải tổng dùng của cả cây con. `D` bao gồm ngân sách con còn giữ cho kỳ đó, kể cả phần con đã tiêu hoặc đang giữ chỗ. Không chỉ cộng những con còn ở trạng thái active.

Việc con tiêu quota không tự làm giảm `D` của cha. Nếu giảm `D` theo phần con vừa tiêu, cha lại có thể cấp phần đã tiêu ấy cho một con khác.

### 3.2. Cây minh họa

~~~mermaid
flowchart TD
    O["Tổ chức: B = 1000"]
    A["Nhóm A: B = 400"]
    B["Nhóm B: B = 300"]
    A1["Dự án A1: B = 120"]
    O --> A
    O --> B
    A --> A1
~~~

Giả sử:

| Node | B | U trực tiếp | R trực tiếp | D cho con | F |
| --- | ---: | ---: | ---: | ---: | ---: |
| Tổ chức | 1.000 | 0 | 0 | 700 | 300 |
| Nhóm A | 400 | 60 | 40 | 120 | 180 |
| Nhóm B | 300 | 0 | 0 | 0 | 300 |
| Dự án A1 | 120 | 50 | 10 | 0 | 60 |

Nhóm A chỉ còn 180 để tự dùng hoặc cấp mới, không phải 300. Phần 120 đã dành cho A1 không thể đồng thời ở ví khả dụng của A.

Tổng lượng đã dùng của nhánh A là 110, gồm 60 trực tiếp ở A và 50 ở A1. Con số 110 phục vụ báo cáo tổng hợp; không ghi đè `U(A)=60` thành 110 rồi vẫn trừ `D(A)=120` trong công thức.

### 3.3. Công thức toàn cây

Nếu không có điều chỉnh hoặc ngân sách gốc mới trong kỳ:

~~~text
B(root)
= SUM(U(node)) + SUM(R(node)) + SUM(F(node))
  trên mọi node trong cây
~~~

Trong bảng trên:

~~~text
1000 = 110 đã dùng + 50 đang giữ + 840 còn tự do trên các node
~~~

Không cộng `D` vào vế phải vì đó là cùng ngân sách đã nằm ở node con. Công thức toàn cây giúp phát hiện cả nhân đôi ngân sách lẫn lỗi tính hai lần.

## 4. Business invariant về phạm vi và thẩm quyền

### 4.1. Quyền được cấp xuống chỉ có thể hẹp hơn

Một delegation phải thỏa mãn:

~~~text
child.tenant = parent.tenant
child.resource_type = parent.resource_type
child.unit = parent.unit
child.period_id = parent.period_id

child.allowed_scope ⊆ parent.allowed_scope
child.valid_from >= parent.valid_from
child.expires_at <= parent.expires_at
child.expires_at <= period.end_at
~~~

Nếu có hạn hợp đồng cứng, thời hạn con cũng không được vượt mốc đó. Hạn kỳ và hạn delegation cần được kiểm tra tại thời điểm chấp nhận thao tác, không chỉ lúc tạo bản ghi.

Quyền cấp tiếp của con không được rộng hơn quyền cha đang được phép chuyển giao. Máy chủ kiểm tra độ sâu và chính sách `can_delegate`; không tin một trường client tự gửi như `admin=true` hoặc `delegation_depth=0`.

Đối với scope phức tạp, “tập con” không chỉ là so chuỗi. Ví dụ quyền trên workspace W không tự bao gồm workspace khác cùng tên; quyền dùng model X không bao gồm model đắt hơn chỉ vì cùng nhóm sản phẩm.

### 4.2. Kiểm tra quyền theo từng đối tượng

Đăng nhập hoặc có role “team admin” không đủ. Cần kiểm tra người gọi có quyền quản lý node nguồn, được phép cấp cho node đích, và các node có quan hệ hợp lệ trong tenant/cây hiện tại.

Nhận quota không tự tạo membership, quyền truy cập dữ liệu hoặc quyền vận hành tài nguyên. Người dùng có 10 lượt export vẫn cần quyền xem dữ liệu mà họ muốn xuất.

OWASP khuyến nghị mặc định từ chối và kiểm tra quyền trên mọi request. Với delegation, các quan hệ cha/con và phạm vi đối tượng phải được kiểm tra tại thao tác thực tế. Xem [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

### 4.3. Không có vòng và không đi tắt qua nhánh khác

Cây không được có cạnh tự trỏ hoặc vòng `A → A1 → A`. Không cho node có nhiều cha nếu mô hình kế toán đang giả định một cha.

Ví dụ chọn không hỗ trợ reparent trong kỳ. Nếu sản phẩm cần chuyển nhánh, phải có nghiệp vụ riêng quyết toán ngân sách, reservation và lịch sử; không sửa `parent_id` bằng một API cập nhật đối tượng thông thường.

Giới hạn độ sâu và số node cũng giúp kiểm soát chi phí kiểm tra/thu hồi. Rate limit chỉ hỗ trợ vận hành, không thay thế điều kiện không có vòng hoặc không vượt ngân sách.

## 5. Dữ liệu và state machine

### 5.1. Các đối tượng tối thiểu

| Đối tượng | Dữ liệu đáng chú ý | Vai trò |
| --- | --- | --- |
| `quota_pool` | Tenant, resource, unit, period, ngân sách root, trạng thái/version | Nguồn ngân sách và guard của cây |
| `quota_bucket` | Pool, chủ thể, cha, B/U/R/D, phạm vi, thời hạn, version | Tài khoản quota của một node |
| `quota_delegation` | Cha/con, phạm vi, policy snapshot, trạng thái | Căn cứ quản lý và nguồn phân bổ |
| `quota_reservation` | Bucket, công việc, lượng, deadline, trạng thái | Dành lượng trước khi thực thi |
| `quota_command` | Key, hash nội dung, loại nghiệp vụ, kết quả | Chống hiệu ứng trùng |
| `quota_ledger` | Cấp, trả, reserve, capture, release, điều chỉnh | Đối soát nguồn gốc lượng |
| `outbox_event` | Event ID, aggregate version, command | Phát thay đổi sau commit |

Bản ghi bucket và cạnh delegation cần cùng chỉ về một quan hệ đã được xác minh; không để hai cấu trúc cha/con mâu thuẫn rồi chọn cấu trúc thuận tiện theo từng API.

`delegated_amount` là số tổng hợp để cập nhật có điều kiện nhanh. Mọi thay đổi `B(child)` phải cập nhật `D(parent)` cùng transaction. Đối soát định kỳ kiểm tra số tổng hợp khớp nguồn chi tiết.

### 5.2. Vòng đời delegation

~~~mermaid
stateDiagram-v2
    [*] --> Requested
    Requested --> Active: Phê duyệt và cấp ngân sách nguyên tử
    Requested --> Rejected: Không đủ điều kiện
    Active --> RevokedDraining: Thu hồi quyền nhận việc mới
    Active --> ExpiredDraining: Đến hạn delegation
    RevokedDraining --> Closed: Quyết toán xong reservation và cây con
    ExpiredDraining --> Closed: Quyết toán xong reservation và cây con
    Rejected --> [*]
    Closed --> [*]
~~~

`REQUESTED` chỉ là ý định, chưa cấp quyền dùng quota. Ví dụ không dành trước ngân sách ở bước yêu cầu; lúc phê duyệt phải kiểm tra lại lượng còn tự do, phạm vi và version hiện hành.

`CLOSED` không có nghĩa ngân sách đã tiêu được xóa khỏi kỳ. Các bản ghi và liên kết kế toán cần được giữ để phần đã dùng vẫn chiếm ngân sách root.

Thời gian có thể khiến delegation hết hiệu lực ngay cả khi cột trạng thái còn `ACTIVE`. Khi kiểm tra một request mới phải kiểm tra các mốc thời gian, không chờ job đổi trạng thái.

### 5.3. Vòng đời reservation

~~~mermaid
stateDiagram-v2
    [*] --> Held
    Held --> Captured: Công việc hợp lệ hoàn tất
    Held --> Released: Hủy giữ chỗ hợp lệ
    Held --> TimedOut: Đến deadline theo chính sách
    Captured --> [*]
    Released --> [*]
    TimedOut --> [*]
~~~

Giữ chỗ lượng q chuyển `F -= q, R += q`. Capture chuyển `R -= q, U += q`. Release chuyển `R -= q, F += q`, không giảm `U`.

Deadline reservation không vượt thời hạn đã chấp nhận của đường delegation và kỳ quota. Mô hình ví dụ cho reservation được chấp nhận trước thu hồi hoàn tất trong phạm vi đã khóa, trước deadline. Thu hồi chặn công việc mới; nó không tự biến reservation đã chấp nhận thành ngân sách tự do.

Nếu sản phẩm cần hủy cả việc đang chạy, phải phối hợp dừng worker và xác nhận kết quả. Không chỉ trả quota theo một timeout trong khi worker vẫn có thể hoàn tất tác động ở hệ thống ngoài.

## 6. Cấp hoặc tăng delegation trong transaction

### 6.1. Một guard chung cho cây

Ví dụ ưu tiên tính đúng bằng một giao thức dễ kiểm chứng:

1. Xác định pool từ dữ liệu máy chủ đã kiểm tra tenant.
2. Khóa hàng `quota_pool`.
3. Khóa các bucket liên quan theo thứ tự ID ổn định.
4. Đọc lại đường tổ tiên, quyền và trạng thái sau khi có khóa.
5. Lấy thời điểm quyết định từ nguồn thời gian có thẩm quyền.
6. Kiểm tra và ghi toàn bộ thay đổi trong cùng transaction.

Mọi writer phải tuân thủ giao thức, kể cả tiêu quota, cấp tiếp, hoàn trả, thu hồi, hết hạn, điều chỉnh và tác vụ quản trị. Khóa pool không tự khóa mọi bucket; nó có tác dụng vì mọi writer đều đi qua guard đó.

PostgreSQL `SELECT ... FOR UPDATE` khóa hàng được chọn và làm writer/locker xung đột phải chờ. Xem [tài liệu khóa hàng PostgreSQL 18](https://www.postgresql.org/docs/18/explicit-locking.html#LOCKING-ROWS).

Đây là baseline có thể giảm thông lượng khi một pool rất nóng. Muốn chia nhỏ khóa hoặc cấp ngân sách sang nhiều vùng cần một giao thức bảo toàn khác được chứng minh, không đơn giản bỏ khóa root nhưng giữ nguyên công thức.

`quota_pool` giữ guard và căn cứ ngân sách hợp đồng; `B(root)` là số kế toán của bucket root. Nếu lưu cả hai giá trị, chúng phải cập nhật nhất quán từ nghiệp vụ cấp ngân sách hợp lệ, không trở thành hai nguồn có thể sửa độc lập.

### 6.2. Luồng cấp cho node con

~~~text
BEGIN trên DB chính
  Khóa pool và các bucket theo giao thức.
  Kiểm tra tenant, actor, quan hệ cha/con và phạm vi.
  Kiểm tra command cũ:
    cùng key, cùng nội dung -> trả lịch sử, không cấp lại;
    cùng key, khác nội dung -> báo xung đột.

  Đọc lại trạng thái, thời hạn và quyền trên toàn đường tổ tiên.
  Kiểm tra phê duyệt còn hiệu lực nếu chính sách yêu cầu.
  Kiểm tra cùng resource/unit/period và không tạo vòng.
  Kiểm tra amount > 0 và amount <= F(parent).

  Tăng D(parent) thêm amount.
  Với node con mới: tạo B(child) = amount, U/R/D của con = 0.
  Với tăng ngân sách: tăng B(child) cùng lượng.
  Ghi/cập nhật cạnh delegation và version.
  Ghi ledger, command, audit, outbox.
COMMIT
~~~

Nếu bước tạo con lỗi sau khi đã tăng `D(parent)`, toàn bộ transaction phải rollback. Không giữ một bên đã ghi rồi hy vọng event sau này sửa bên còn lại.

Luồng phê duyệt cũng phải kiểm tra lại số dư hiện tại. Việc “còn 200 lúc tạo yêu cầu” không chứng minh “còn 200 lúc duyệt”. Một yêu cầu đã được thực thi cần unique hoặc trạng thái terminal để không áp dụng lại bằng một command key khác.

### 6.3. Cập nhật có điều kiện ở node cha

SQL minh họa phần giữ ngân sách cho con:

~~~sql
UPDATE quota_bucket
SET delegated_amount = delegated_amount + :amount,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND pool_id = :pool_id
  AND id = :parent_bucket_id
  AND status = 'ACTIVE'
  AND :amount > 0
  AND budget_amount
      - used_amount
      - reserved_amount
      - delegated_amount >= :amount
RETURNING id, version;
~~~

Placeholder cần bind theo driver. Truy vấn giả định counter đang hợp lệ và các điều kiện về thời gian, tổ tiên, phạm vi, phê duyệt đã được kiểm tra dưới guard.

Mỗi lần cấp mới phải cập nhật đúng một hàng cha. Không có hàng trả về thì không tạo con. Có hàng trả về nhưng tạo/cập nhật con thất bại thì rollback cả hai.

Ràng buộc số học trên một hàng có thể dùng các điều kiện không âm và so sánh trừ dần để tránh cộng tràn kiểu số nguyên:

~~~text
used_amount <= budget_amount
reserved_amount <= budget_amount - used_amount
delegated_amount <= budget_amount - used_amount - reserved_amount
~~~

Các counter cần `NOT NULL`. Với PostgreSQL, `CHECK` không phải cơ chế bảo đảm tổng trên những hàng khác luôn đúng; tài liệu nêu rõ giới hạn của kiểm tra tham chiếu dữ liệu ngoài hàng hiện tại. Xem [PostgreSQL CHECK constraints](https://www.postgresql.org/docs/18/ddl-constraints.html#DDL-CONSTRAINTS-CHECK-CONSTRAINTS).

Vì vậy, invariant `D(parent) = SUM(B(child))` cần giao thức cập nhật nguyên tử, ràng buộc quan hệ và đối soát phù hợp; không được tuyên bố an toàn chỉ vì từng hàng có `CHECK >= 0`.

### 6.4. Nếu dùng Serializable hoặc optimistic locking

PostgreSQL Serializable có thể buộc ứng dụng retry khi phát hiện xung đột tuần tự hóa. Không coi đặt isolation level là loại bỏ trách nhiệm xử lý lỗi. Xem [tài liệu transaction isolation PostgreSQL 18](https://www.postgresql.org/docs/18/transaction-iso.html#XACT-SERIALIZABLE).

Với version/CAS, xung đột phải làm đọc lại toàn bộ căn cứ cần thiết, gồm lượng còn tự do và trạng thái tổ tiên. Không retry mù cùng một quyết định đã được tính trước khi delegation bị thu hồi.

Mọi retry vẫn cần command idempotency. Không thực hiện HTTP hoặc tác động không thể rollback giữa các bước của transaction DB rồi mong transaction retry an toàn.

## 7. Sử dụng quota được ủy quyền

### 7.1. Nhận việc mới phải xét cả đường tổ tiên

Một request tiêu quota tại A1 phải kiểm tra:

- Chủ thể được phép dùng bucket A1 cho công việc này.
- Pool đang nhận việc mới và đúng kỳ.
- A1 và các delegation tổ tiên đều còn hiệu lực.
- Resource, đơn vị, scope và điều kiện nghiệp vụ phù hợp.
- Lượng yêu cầu dương và không vượt `F(A1)`.
- Command/công việc chưa có hiệu ứng tương đương đã được chấp nhận.

Không chỉ kiểm tra A1 đang `ACTIVE`. Nếu A đã bị thu hồi, A1 không được tiếp tục nhận việc mới qua một endpoint khác hoặc bằng token cũ.

Trong mô hình dành trước, không trừ thêm quota root mỗi lần A1 tiêu. Ngân sách đã được giữ trong `D` của các cha. Nếu vừa trừ ngân sách đã dành vừa trừ tổng dùng của con ở cùng công thức, hệ thống tính chi phí hai lần.

### 7.2. Reserve, capture và release

Ví dụ A1 có `B=120, U=50, R=10, D=0`, nên `F=60`.

- Nhận một công việc mới 20 lượt: `R=30, F=40`.
- Công việc đó hoàn tất và capture 20: `U=70, R=10, F=40`.
- Nếu hủy trước khi tiêu và release 20 thay vì capture: `U=50, R=10, F=60`.

Cả ba thao tác không đổi `B(A1)` và không đổi `D(A)=120`.

Capture phải liên kết với reservation thật, đúng bucket, đúng công việc và lượng đã giữ. Client không được gửi một reservation của nhóm khác hoặc một lượng capture lớn hơn phần còn giữ.

Nếu công việc chỉ dùng một phần, cần chính sách capture/release phần còn lại. Bài giả định kết thúc reservation theo kết quả đã được xác minh; không có API tự phục vụ để người gọi tùy ý khai “dùng ít hơn” rồi lấy lại ngân sách.

### 7.3. Kết quả chưa rõ không đồng nghĩa chưa tiêu

Nếu worker timeout sau khi hệ thống ngoài có thể đã nhận công việc, chưa được tự release quota rồi cấp nó cho người khác. Cần tra cứu, đối soát hoặc giữ một trạng thái chưa quyết toán vẫn chiếm `R`.

Để release khi deadline tới, phải có bảo đảm công việc không còn khả năng tạo hiệu ứng ngoài phần đã ghi nhận. Nếu không có bảo đảm đó, deadline dừng nhận/thực thi mới nhưng phần ngân sách chưa rõ vẫn cần được giữ để đối soát.

Quota reservation chỉ là căn cứ về lượng đã dành. Nó không thay thế quyền truy cập dữ liệu hay một khóa an toàn độc lập có thể chặn công việc vì lý do rủi ro.

## 8. Trả lại quota và thu hồi delegation

### 8.1. Chỉ trả phần còn tự do

Để con trả lượng Δ về cha:

~~~text
0 < Δ <= F(child)

B(child) -= Δ
D(parent) -= Δ
~~~

Hai thay đổi cùng transaction. Không tăng `B(parent)`: ngân sách cha vốn đã có, chỉ chuyển từ phần đang dành cho con về phần tự do của cha.

Ví dụ A còn tự do 180. Trả 180 về root:

~~~text
B(A): 400 -> 220
D(root): 700 -> 520
F(root): 300 -> 480

U(A)=60, R(A)=40, D(A)=120 giữ nguyên
~~~

Trả 400 sẽ sai vì phần ngân sách đó đang bảo đảm cho công việc đã tiêu, đang giữ hoặc đã cấp xuống A1.

Sau release reservation tại con, `F(child)` có thể tăng. Phần đó chỉ trở thành `F(parent)` sau một nghiệp vụ trả lại hợp lệ; release không tự cộng ở cả hai cấp.

### 8.2. Thu hồi gồm chặn quyền và quyết toán lượng

Thu hồi nhánh A có thể làm theo hai giai đoạn:

1. Dưới guard, chuyển A sang `REVOKED_DRAINING` và tăng version. Mọi admission mới trong nhánh phải thấy A không còn cho nhận việc.
2. Thu hồi phần tự do theo thứ tự từ lá lên; tiếp tục xử lý reservation đã được chấp nhận theo chính sách, giữ lại phần đã dùng và nghĩa vụ chưa quyết toán.

Trong ví dụ, A1 có thể trả 60 tự do về A:

~~~text
B(A1): 120 -> 60
D(A): 120 -> 60
~~~

Sau khi A đã trả 180 ban đầu, A lại có 60 tự do để trả tiếp về root:

~~~text
B(A): 220 -> 160
D(root): 520 -> 460
F(root): 480 -> 540
~~~

Phần 160 còn ở nhánh A bảo đảm 110 đã dùng và 50 đang giữ. Không được coi cả 160 là có thể tái cấp chỉ vì nhánh đã bị thu hồi.

Khi 50 giữ chỗ kết thúc:

- Nếu capture hợp lệ, lượng đó chuyển thành đã dùng và tiếp tục chiếm ngân sách của kỳ.
- Nếu release được xác minh, lượng trở thành tự do rồi có thể trả lên qua các cạnh.
- Nếu kết quả chưa rõ, tiếp tục giữ nghĩa vụ để tránh tái cấp trùng.

### 8.3. Không xóa lịch sử để tạo số dư

Không tính `D(parent)` bằng cách chỉ lọc delegation đang active. Các node bị thu hồi/đóng nhưng còn ngân sách đã dùng vẫn là một phần của phép bảo toàn trong kỳ.

Không xóa node con hoặc cạnh cha/con làm phần đã dùng biến mất khỏi tổng. Có thể lưu trữ lịch sử sang cấu trúc đối soát khác, nhưng phải giữ được cùng nghĩa vụ ngân sách và không tạo phần tự do mới.

Trong mô hình ví dụ, việc thu hồi không tự hoàn lại `U`. Nếu sản phẩm cho phép hoàn quota đã tiêu vì lỗi dịch vụ, đó là command điều chỉnh riêng, có căn cứ giao dịch gốc, giới hạn lượng được hoàn và phê duyệt nếu cần.

## 9. Hết hạn, đổi kỳ và thay đổi ngân sách root

### 9.1. Mốc thời gian và kỳ quota

Một admission mới cần thỏa mãn:

~~~text
valid_from <= decision_at < expires_at
period.start_at <= decision_at < period.end_at
~~~

Kiểm tra thời gian sau khi đã có khóa cần thiết. Request đến trước hết kỳ nhưng chờ khóa qua mốc không được dùng thời gian nhận request để vượt hạn.

Khi delegation hết hạn, phần tự do có thể được trả về cha nếu chính sách và thời hạn cha còn cho phép sử dụng. Tuy nhiên, phần đã dùng của con vẫn phải được giữ trong kế toán kỳ cũ.

Job trễ không được kéo dài quyền admission. Khi cột vẫn ghi `ACTIVE` nhưng hạn đã qua, request mới vẫn phải bị chặn.

### 9.2. Tạo bucket kỳ mới thay vì đặt lại hàng cũ

Dùng `period_id` ổn định cho mọi bucket, reservation, command và ledger. Khi sang kỳ mới, tạo ngân sách và cây phân bổ mới theo chính sách; không đặt `U=0` trên hàng mà worker kỳ cũ còn tham chiếu.

Kết quả công việc thuộc kỳ nào phải được xác định từ reservation/command được chấp nhận, không từ thời điểm callback tới. Callback trễ không được giảm hoặc tăng số dư của kỳ mới chỉ vì đó là kỳ hiện tại.

Nghĩa vụ chưa quyết toán của kỳ cũ cần được giữ trong kỳ cũ. Nếu có rollover, thực hiện bằng bút toán nguồn/đích có định danh duy nhất và quy tắc rõ về phần nào được chuyển. Không chuyển cả lượng đã dùng hoặc chưa rõ như thể nó là phần chưa tiêu.

### 9.3. Tăng hoặc giảm ngân sách root

Chỉ nguồn có thẩm quyền mới tăng `B(root)`, ví dụ mua thêm đã được xác nhận hoặc quyết định quản trị được phê duyệt. Delegation không phải nguồn mint quota.

Giảm ngân sách root không được làm invariant âm. Nếu ngân sách mới thấp hơn lượng đã dùng, đang giữ và đang cấp cho các nhánh, phải có chính sách riêng: áp dụng kỳ sau, thu hồi phần tự do trước hoặc chặn admission mới rồi đối soát.

Không sửa trực tiếp số giới hạn rồi bỏ qua các nghĩa vụ đã có. Đổi plan cũng không tự xóa lịch sử dùng hoặc tạo lại ngân sách của cùng kỳ.

## 10. Các chuỗi lạm dụng cần nhận diện

| Chuỗi thao tác | Mục đích | Điểm bảo vệ |
| --- | --- | --- |
| Gửi hai delegation song song cùng dùng phần cuối | Cấp vượt ngân sách cha | Guard, cập nhật có điều kiện và transaction |
| Retry cấp quota bằng cùng hoặc khác key | Nhận ngân sách nhiều lần | Command idempotency và unique theo yêu cầu nghiệp vụ |
| Nhận quota rồi tự bật `can_delegate` | Có quyền cấp tiếp trái phép | Máy chủ quyết định quyền quản lý |
| Đổi `parent_id`, tenant hoặc bucket nguồn | Lấy quota từ nhánh khác | Quyền theo đối tượng và quan hệ cây |
| Tạo vòng hoặc nhiều cha | Nhân nguồn ngân sách/né kiểm tra tổ tiên | Ràng buộc topology và giao thức tạo cạnh |
| Đổi resource/unit | Dùng quota rẻ cho công việc đắt | Kiểm tra loại tài nguyên, đơn vị và scope |
| Gửi amount âm, quá lớn hoặc giá trị null | Tăng số dư, tràn số hoặc bỏ qua điều kiện | Kiểu dữ liệu, NOT NULL và kiểm tra số học |
| Thu hồi con sau khi con đã tiêu | Lấy lại cả lượng đã dùng để cấp tiếp | Chỉ trả `F`, giữ nghĩa vụ `U/R/D` |
| Xóa/đóng cạnh để parent bỏ qua nó | Làm biến mất lượng đã dùng | Kế toán theo kỳ, không chỉ lọc active |
| Dùng token cũ sau thu hồi tổ tiên | Tiếp tục nhận việc ở node lá | Xét trạng thái và version đường tổ tiên |
| Timeout worker rồi yêu cầu release | Tái dùng lượng có thể đã tiêu | Đối soát kết quả chưa rõ, không trả sớm |
| Callback kỳ trước vào bucket kỳ mới | Tiêu hoặc hoàn sai kỳ | Reservation/command gắn pool và period gốc |
| Tự tạo rồi tự duyệt ngoại lệ | Vượt giới hạn quản trị | Quyền phê duyệt độc lập nếu chính sách yêu cầu |
| Đổi plan để reset bộ đếm | Có quota mới trong cùng kỳ | Bucket và ledger ổn định theo nguồn cấp |

Kiểm thử các chuỗi này trong môi trường được kiểm soát, với tenant và tài khoản thử nghiệm. JSON hợp lệ, token có chữ ký hoặc role quản trị chung không chứng minh thao tác hợp lệ về ngân sách.

## 11. Idempotency, phê duyệt và xử lý phân tán

### 11.1. Định danh command và nghiệp vụ gốc

Một phạm vi idempotency có thể là:

~~~text
(tenant_id, pool_id, operation_type, idempotency_key)
~~~

Hash nội dung đã chuẩn hóa phải bao gồm node nguồn/đích, lượng, resource, unit, period, scope, thời hạn và tham chiếu phê duyệt có ảnh hưởng nghiệp vụ.

Cùng key khác nội dung phải báo xung đột. Cùng key cùng nội dung đã hoàn tất thì trả kết quả lịch sử sau khi kiểm tra quyền được xem, không chạy lại phép chuyển ngân sách.

Một kết quả delegation cũ đã thành công không chứng minh delegation hiện còn active. Không mở lại nhánh đã thu hồi chỉ vì client retry command tạo nó.

Idempotency key do client chọn không ngăn việc gửi nhiều key mới cho cùng phiếu phân bổ. Cần thêm invariant theo nghiệp vụ gốc, chẳng hạn yêu cầu phê duyệt chỉ được áp dụng một lần hoặc một lần capture cho một reservation.

### 11.2. Phê duyệt cần gắn với căn cứ hiện hành

Nếu khoản cấp lớn cần duyệt, bản phê duyệt phải ghi rõ chủ thể yêu cầu/duyệt, tenant, node nguồn/đích, lượng tối đa, scope, thời hạn và version kỳ vọng.

Khi áp dụng vẫn phải kiểm tra lại:

- Người duyệt có quyền trong phạm vi này.
- Yêu cầu chưa bị hủy, hết hạn hoặc dùng trước đó.
- Node và đường tổ tiên chưa đổi sang trạng thái không hợp lệ.
- Có đủ `F(parent)` tại thời điểm thực thi.
- Không sửa payload sau khi duyệt để cấp cho node khác hoặc tăng lượng.

Không dùng một approval ID như quyền chung cho mọi delegation. Một ngoại lệ tăng root budget cũng phải tách khỏi quyền chỉ phân phối ngân sách đã có.

### 11.3. Event không phải một lần mint ngân sách mới

Ghi ledger, command và outbox cùng transaction local. Consumer có thể nhận event trùng hoặc đảo thứ tự; event ID và version giúp nhận diện, nhưng không được cộng quota thêm một lần mỗi khi nhận thông báo “đã cấp”.

Cache có thể hiển thị cây/ngân sách, nhưng admission và delegation vẫn cần nguồn có thẩm quyền theo mô hình đang chọn. Một event cache đến trễ không được khôi phục quyền cấp tiếp đã bị thu hồi.

Nếu consumer dựng trạng thái từ delta, phải kiểm soát sequence hoặc nạp lại snapshot khi thiếu sự kiện. Không chỉ lấy version lớn nhất rồi giả định mọi thay đổi số lượng đã được áp dụng.

### 11.4. Cấp ngân sách cho vùng hoặc agent hoạt động độc lập

Có thể mở rộng ý tưởng dành trước bằng cách cấp một phần ngân sách riêng cho từng vùng. Khi đó, ngân sách đã chuyển vẫn bị khóa ở phía cha cho đến khi có bằng chứng phần chưa dùng đã được trả hoặc quyết toán.

Mất kết nối không chứng minh agent chưa tiêu ngân sách. Không cấp lại toàn bộ chunk cho agent khác trong khi agent cũ còn có thể tiếp tục dùng nó.

Token/lease có chữ ký cần đi cùng giới hạn lượng, scope, kỳ, thời hạn, định danh duy nhất và cơ chế kiểm soát tiêu dùng ở nơi thực thi. Chữ ký không ngăn cùng một token được tiêu nhiều lần nếu các nơi nhận không phối hợp hoặc không được cấp ngân sách tách biệt.

Fencing/version có tác dụng khi nơi thực hiện tác động thật sự kiểm tra nó. Nếu một agent mất kết nối vẫn có thể tạo tác động mà không kiểm tra thế hệ hiện hành, chỉ tăng version ở trung tâm không đủ cho phép tái cấp ngân sách an toàn.

Mô hình nhiều vùng cần quy tắc rõ cho thu hồi, hết lease, đồng hồ và công việc chưa rõ kết quả. Không tuyên bố có hard quota toàn cục chỉ vì mỗi vùng giữ một counter local.

## 12. Minh họa Java: kiểm tra số lượng trước khi lập kế hoạch cấp

Mã sau chỉ tính phần số học cho một delegation mới. Nó không xử lý quyền, kỳ, topology, khóa DB hoặc commit:

~~~java
public final class QuotaDelegationMath {
    public record Balance(
            long budget,
            long used,
            long reserved,
            long delegated) {

        public Balance {
            if (budget < 0 || used < 0 || reserved < 0 || delegated < 0) {
                throw new IllegalArgumentException("Negative quota");
            }

            // So sánh trừ dần; không cộng các counter trước khi kiểm tra.
            if (used > budget
                    || reserved > budget - used
                    || delegated > budget - used - reserved) {
                throw new IllegalArgumentException("Inconsistent quota");
            }
        }

        public long free() {
            return budget - used - reserved - delegated;
        }
    }

    public record NewDelegationPlan(
            long parentDelegatedAfter,
            long childBudget) {}

    public static NewDelegationPlan planNewDelegation(
            Balance parent, long amount) {
        if (parent == null) {
            throw new IllegalArgumentException("Missing parent");
        }
        if (amount <= 0 || amount > parent.free()) {
            throw new IllegalArgumentException("Insufficient free quota");
        }

        return new NewDelegationPlan(
                Math.addExact(parent.delegated(), amount),
                amount);
    }
}
~~~

Với `Balance(400, 60, 40, 120)`, `free()` là 180:

- Cấp 180 tạo kế hoạch `parentDelegatedAfter=300` và `childBudget=180`.
- Cấp 181 phải bị từ chối.
- Amount âm hoặc bằng 0 phải bị từ chối.
- Counter không nhất quán không được âm thầm làm tròn hoặc ép về 0.

Trong dịch vụ thật, đọc balance dưới giao thức transaction, kiểm tra toàn bộ ngữ cảnh, rồi ghi cả cha và con nguyên tử. Không tính kế hoạch từ response cache hoặc payload client và cập nhật nhiều endpoint độc lập.

Nếu quota có phần lẻ, cần kiểu thập phân cố định và quy tắc chuyển đơn vị/làm tròn. Không dùng phép quy đổi không nhất quán khiến cấp xuống một đơn vị rồi trả lên thành nhiều hơn một đơn vị.

## 13. Kiểm thử invariant và tình huống tấn công

### 13.1. Ma trận kiểm thử nghiệp vụ

| Nhóm | Kịch bản | Kết quả cần chứng minh |
| --- | --- | --- |
| Cấp phát | Cấp đúng bằng `F(parent)` | Cha còn F=0, con nhận đúng lượng |
| Vượt giới hạn | Cấp F+1 | Không đổi bất kỳ counter hoặc cạnh nào |
| Số học | Amount 0, âm, null, rất lớn | Không cộng ngược hoặc tràn số |
| Phạm vi | Khác tenant/resource/unit/period | Từ chối, không rò hoặc chuyển ngân sách |
| Scope | Con đề nghị quyền rộng hơn cha | Không mở rộng phạm vi |
| Cấp tiếp | Bên nhận không có `can_delegate` | Không tạo được con mới |
| Topology | Tự trỏ, tạo vòng, thêm cha thứ hai | Không phá mô hình cây |
| Phê duyệt | Sửa lượng/node sau duyệt | Không áp dụng nội dung ngoài căn cứ |
| Trạng thái | Tổ tiên revoked nhưng node lá active | Không nhận công việc mới |
| Thời hạn | Đúng deadline hoặc hết kỳ | Không admission mới |
| Sử dụng | Con capture lượng đã reserve | U tăng, R giảm, D của cha không đổi |
| Trả lại | Con có U/R/D và đề nghị trả toàn B | Chỉ cho trả phần tự do |
| Thu hồi | Thu hồi nhánh đã dùng và có giữ chỗ | Không tái cấp phần nghĩa vụ còn lại |
| Xóa lịch sử | Đóng delegation đã tiêu quota | Parent không tự có thêm F |
| Callback trễ | Kết quả kỳ cũ tới sau reset | Quyết toán đúng kỳ gốc |
| Retry | Mất response sau commit | Không cấp hoặc trả lượng lần nữa |
| Khác key | Cùng yêu cầu nghiệp vụ, nhiều key | Invariant nghiệp vụ ngăn hiệu ứng trùng |
| Rollback | Lỗi sau tăng D trước tạo con | Cả cha/con/ledger/command rollback |
| Worker mơ hồ | Timeout nhưng có thể đã tạo tác động | Không release lượng chưa được xác minh |
| Thay đổi root | Giảm dưới nghĩa vụ hiện tại | Không làm invariant âm hoặc xóa lịch sử |

Kiểm tra số liệu sau commit/rollback, không chỉ mã HTTP. Cần đối chiếu B/U/R/D/F, cạnh cha/con, reservation, ledger, command và event.

### 13.2. Kiểm thử đồng thời có điều phối

Dùng hai kết nối DB và điểm đồng bộ trong bộ kiểm thử:

1. Cha chỉ còn F=100.
2. Hai request khác key cùng đề nghị cấp 80.
3. Buộc chúng tranh guard/bước cập nhật thay vì chạy nối tiếp tình cờ.
4. Xác nhận chỉ một request được cấp; request còn lại phải đọc lại và bị từ chối hoặc retry có kết quả hợp lệ.
5. Tổng D chỉ tăng 80, không tăng 160.

Kiểm tra thêm:

- Cấp con và parent tự reserve cùng phần cuối.
- Trả lại từ con và con reserve cùng phần tự do.
- Thu hồi tổ tiên và admission mới tại node lá.
- Hai lần capture hoặc release cùng reservation.
- Thu hồi và sweep cùng một nhánh.
- Chuyển kỳ và callback của reservation cũ.

Kỳ vọng phải được viết theo điểm phân xử. Nếu admission đã được chấp nhận trước thu hồi dưới guard, reservation có thể tiếp tục theo chính sách. Nếu thu hồi commit trước, admission mới phải bị chặn.

### 13.3. Kiểm thử theo chuỗi và đối soát toàn cây

Sinh chuỗi:

~~~text
cấp ngân sách root
→ cấp cho A
→ A cấp cho A1
→ A1 reserve
→ retry delegation
→ A1 capture hoặc release
→ thu hồi A
→ trả phần tự do từ lá lên
→ callback trễ
→ sang kỳ mới
~~~

Sau mỗi bước, kiểm tra:

~~~text
F(node) >= 0
D(parent) = SUM(B(child))
không vòng, không liên kết chéo tenant/pool/period
B(root) = SUM(U) + SUM(R) + SUM(F)
~~~

Nếu có top-up hoặc điều chỉnh, mở rộng đối soát bằng bút toán nguồn hợp lệ. Mọi ngân sách tăng phải truy được về một căn cứ, không chỉ xuất hiện do một trạng thái chuyển từ active sang closed.

Các code/SQL và giả mã trong bài là minh họa thiết kế, chưa phải một bộ triển khai tích hợp hoàn chỉnh.

## 14. Vận hành, audit và sửa chữa dữ liệu

Audit delegation nên trả lời được ai chuyển lượng nào, từ nguồn nào tới đâu và dựa vào quyền/phê duyệt nào:

- Tenant, pool, period, resource và unit.
- Actor, node nguồn/đích, đường tổ tiên và phiên bản liên quan.
- Lượng yêu cầu, lượng đã áp dụng, B/U/R/D trước và sau.
- Command ID, idempotency key đã xử lý phù hợp và tham chiếu nghiệp vụ gốc.
- Phê duyệt, policy snapshot, thời điểm quyết định và hạn có hiệu lực.
- Ledger, reservation, công việc và event liên quan.

Không ghi token hoặc dữ liệu nhạy cảm không cần thiết vào log. Client không được cung cấp các trường audit như người phê duyệt hoặc version thực tế để máy chủ tin trực tiếp.

Các chỉ số vận hành hữu ích:

| Chỉ số | Điều cần quan sát |
| --- | --- |
| Sai lệch D so với tổng B con | Lỗi cập nhật hoặc đường ghi bỏ giao thức |
| F âm hoặc tổng nghĩa vụ vượt root | Vi phạm bảo toàn cần xử lý |
| Nhánh revoked còn admission mới | Kiểm tra tổ tiên hoặc cache có vấn đề |
| Reservation quá hạn/chưa rõ kết quả | Ngân sách bị giữ và rủi ro trả sớm |
| Thời gian chờ guard, deadlock/retry | Chi phí đồng thời của thiết kế |
| Command trùng/xung đột | Lỗi retry hoặc hành vi lạm dụng |
| Độ trễ thu hồi/sweep/outbox | Hiệu quả điều phối và đối soát |

Đối soát giúp phát hiện sai lệch, nhưng không thay thế transaction chặn vượt quota tại thời điểm ghi. Một lỗi chỉ được sửa bằng job đêm vẫn có thể bị khai thác trong ngày.

Công cụ sửa chữa cần chạy command có quyền, idempotency và ledger. Không đặt U/R/D về 0 hoặc xóa cạnh để làm số liệu trông cân bằng. Khi chưa xác định được lượng đã tiêu thật, giữ nghĩa vụ chưa rõ và hạn chế admission theo chính sách cho tới khi có căn cứ quyết toán.

Delegation an toàn giữ được hai điều đồng thời: quyền cấp xuống không rộng hơn thẩm quyền nguồn, và mọi phần ngân sách luôn có đúng một vị trí kế toán trong cùng kỳ, kể cả khi request lặp, worker trễ hoặc cả nhánh bị thu hồi.
