# Sensitive sort prevention: ngăn lộ dữ liệu qua thứ tự sắp xếp

## 1. Mục tiêu bài học

Trong chương **Sorting Rules** của module **Bảo mật logic nghiệp vụ** (mã dịch vụ: SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY), **sensitive sort prevention** là việc ngăn một truy vấn dùng thuộc tính nhạy cảm để quyết định thứ tự mà caller không được phép quan sát.

Ẩn amount, balance hoặc internalRiskScore khỏi JSON chưa chắc giữ bí mật các thuộc tính đó. Nếu API vẫn cho sort theo chúng, vị trí của từng đối tượng có thể tiết lộ quan hệ lớn–nhỏ, phân nhóm hoặc thay đổi trạng thái nội bộ.

Bài học tập trung vào quyền theo đối tượng/field, hợp đồng sort, pagination, hiệu ứng nghiệp vụ và kiểm thử các tình huống khai thác thứ tự.

Sau bài học, bạn có thể:

- Phân biệt quyền đọc row, xem field và sử dụng field làm khóa sort.
- Nhận diện rò rỉ qua sort key, default, secondary key, cursor và metadata.
- Thiết kế tập khóa sort công khai có ánh xạ server rõ ràng.
- Giữ scope và field policy đúng trên toàn tập ứng viên được sắp xếp.
- Tách việc hiển thị danh sách khỏi quy tắc chọn item để duyệt/chi trả.
- Kiểm thử rằng thay dữ liệu bị che không làm public order đổi ngoài policy.

## 2. Thứ tự cũng là một dạng công bố dữ liệu

Giả sử caller được xem mã hồ sơ A, B và C nhưng không được xem internalRiskScore.

Dữ liệu nội bộ:

~~~text
A: score = 10
B: score = 90
C: score = 20
~~~

Nếu API cho:

~~~text
sortBy=internalRiskScore&direction=ASC
~~~

và trả A, C, B, caller biết tương quan thứ tự của score dù response không có field score.

Đổi direction có thể xác nhận quan hệ đó. Nếu caller còn biết giá trị của một số bản ghi mốc hoặc có các bộ lọc bổ sung, nhiều lần truy vấn có thể giúp suy ra khoảng giá trị.

Một lần sort không tự cho biết chính xác mọi con số. Nhưng nó đã công bố thông tin có ý nghĩa mà policy có thể muốn giữ kín.

### 2.1. Những dữ kiện dễ bị lộ qua sort

| Thuộc tính nội bộ | Thông tin có thể bị suy ra |
|---|---|
| Credit limit/balance | So sánh tương đối giữa khách hàng hoặc tài khoản |
| Fraud/risk score | Thứ tự ưu tiên điều tra hoặc phân loại nội bộ |
| Internal approval threshold | Các nhóm có ngưỡng hoặc quy trình khác nhau |
| Hidden priority | Đối tượng nào đang được ưu tiên phía server |
| Private event time | Thứ tự một loại sự kiện không được công bố |
| Count/aggregate bí mật | Số cảnh báo, tổng nghĩa vụ hoặc độ lớn của tập liên quan |
| Nullable sensitive field | Đối tượng nào có/không có một thông tin nhạy cảm |

Ngay cả null ordering cũng có thể phân chia đối tượng theo một facts mà caller không được biết.

### 2.2. Không chỉ sort do client yêu cầu

Thông tin nhạy cảm có thể nằm trong:

~~~text
sort key tường minh
default sort khi client không gửi
secondary/tertiary key
tie-breaker của pagination
derived key hoặc alias
group order
cursor chứa giá trị khóa
export hoặc một endpoint danh sách khác
~~~

Chặn tên internalRiskScore trong query parameter không đủ nếu default hoặc alias recommended vẫn dùng nguyên score đó.

## 3. Ba loại quyền cần phân biệt

| Quyền | Câu hỏi |
|---|---|
| Row access | Caller được biết/đọc những đối tượng nào? |
| Field disclosure | Caller được biết những thuộc tính nào của từng đối tượng? |
| Sort usage | Caller được dùng thuộc tính nào để tạo thứ tự trong tập đang truy vấn? |

Một caller có thể đọc thông tin cơ bản của nhiều hồ sơ nhưng chỉ được xem amount trong một đơn vị.

Nếu sort cả tập hỗn hợp theo amount, các hồ sơ không được xem amount vẫn bị đặt vào quan hệ so sánh. Việc chỉ redact amount ở những dòng đó không ngăn được rò rỉ thứ tự.

### 3.1. Không có field trong body chưa chứng minh sort được phép

Một sort có thể chỉ cần field trong query/index mà không select nó vào response. Điều đó không làm việc sử dụng field trở nên ít nhạy cảm hơn.

Tương tự, một field có thể được phép hiển thị nhưng sản phẩm vẫn giới hạn sort vì chi phí hoặc hợp đồng truy vấn. Quyền dữ liệu và ngân sách tài nguyên là các chiều khác nhau.

### 3.2. Cấm server sort không thu hồi dữ liệu đã được cấp

Nếu caller được xem đầy đủ một giá trị trên mọi row, họ có thể tự sắp xếp dữ liệu đã nhận ở client.

Kiểm soát trong bài nhằm không dùng thuộc tính chưa được phép để công bố thứ tự, đồng thời giữ hợp đồng tài nguyên. Nó không hứa ngăn mọi suy luận hoặc sắp xếp từ dữ liệu đã được cấp hợp lệ.

### 3.3. Mỗi action có phạm vi riêng

Quyền search/list không tự bao gồm export rộng hoặc chọn thứ tự chi trả.

sortBy trong một màn hình xem danh sách và selection policy của một batch thực hiện nghiệp vụ có thể phải được quản lý khác nhau. Đổi thứ tự hiển thị không được trở thành cách né quy tắc ưu tiên bắt buộc.

## 4. Mô hình nghiệp vụ minh họa

Ví dụ dùng danh sách hồ sơ mua hàng trong một tenant:

~~~text
Public/basic fields theo scope:
  requestId
  publicCode
  createdAt
  displayName

Fields phụ thuộc quyền:
  amountMinor
  budgetOwner

Internal fields:
  internalRiskScore
  reviewWatchFlag
  privateEscalationAt
~~~

Policy mẫu:

- Sort cơ bản chỉ nhận những key được công bố và cấp cho endpoint.
- Risk/watch/private event không được sử dụng để tạo public order.
- amountMinor chỉ sortable khi quyền sort và phạm vi dữ liệu đáp ứng điều kiện.
- Default sort là createdAt với tie-breaker an toàn được chỉ định.
- Các điều kiện tenant/object scope luôn có trong tập dữ liệu.
- Hành động approve/execute dùng policy nghiệp vụ riêng, không tin một thứ tự client tự khai.

Đây là lựa chọn minh họa. Một sản phẩm có thể chủ ý công bố một phần ưu tiên hoặc số liệu, nhưng phải xác định rõ thông tin nào được phép quan sát.

### 4.1. Một nhãn công khai không tự làm khóa nhạy cảm an toàn

Đổi tên riskScore thành recommended hoặc relevance không thay đổi facts quyết định thứ tự.

Nếu sản phẩm thật sự cho công bố một ưu tiên, nên có contract và nguồn dữ liệu phù hợp cho mức công bố đó. Không giấu khóa gốc sau một tên vô hại rồi cho rằng nó không còn tiết lộ.

### 4.2. Redaction không phải phép sửa cuối cùng

Pipeline nguy hiểm:

~~~text
Sort mọi row theo hidden score.
Phân trang.
Bỏ score khỏi response.
~~~

Tại bước bỏ field, thông tin thứ tự đã được chuyển thành vị trí row và boundary của trang.

Cần quyết định sort policy trước khi tạo query/order, không chỉ xử lý serializer.

## 5. Registry sort key theo hợp đồng công khai

Một policy mẫu:

| Public key | Ý nghĩa được phép dùng | Điều kiện |
|---|---|---|
| CREATED_AT | Thời điểm tạo được công bố | Đúng row scope và quyền list |
| PUBLIC_CODE | Mã hồ sơ công khai theo view | Có hợp đồng so sánh/normalization rõ |
| DISPLAY_NAME | Tên hiển thị caller được phép dùng | Không dùng tên từ đối tượng liên quan ngoài scope |
| AMOUNT | Giá trị tiền của hồ sơ | Quyền sort riêng và quyền field đáp ứng toàn query scope theo policy mẫu |
| PUBLIC_PRIORITY_BAND | Nhóm ưu tiên đã được phê chuẩn để công bố | Chỉ dùng band công khai, không thêm hidden score trong cùng band |
| Không có key cho internalRiskScore | Không cấp qua endpoint này | Không tự tạo key từ entity/index |

Các key công khai được ánh xạ bằng code/cấu hình server đã được quản lý. Không lấy danh sách mọi property của entity làm danh sách sort mặc định.

### 5.1. Allowlist theo nghĩa, không chỉ theo tên

Một definition cần mô tả:

~~~text
public key
kiểu so sánh
column/expression do server kiểm soát
join hoặc nguồn dữ liệu liên quan
mức thông tin được công bố
capability và scope cần có
direction/null/collation được hỗ trợ
ngân sách thực thi
~~~

Một key nằm trong registry vẫn có thể sai nếu expression thực tế dùng private risk thay vì giá trị đã được phê chuẩn. Registry cần phản ánh logic thật, không chỉ là tên được đổi.

### 5.2. Không dùng blocklist vài từ nhạy cảm

Chặn riskScore nhưng vẫn cho client chọn arbitrary property path có thể bỏ sót:

~~~text
customer.risk.score
internal_profile.score
reviewFlags.count
calculatedPriority
~~~

Tập key được phép nên đóng theo endpoint/action. Alias tương thích, nếu có, phải ánh xạ về một key canonical trước khi kiểm tra quyền, trùng lặp và cursor.

Không cần hỗ trợ mọi path mà ORM/search engine có thể hiểu.

### 5.3. Quyền phải bao phủ cả tập ứng viên

Giả sử actor được xem amount ở branch-a nhưng chỉ xem thông tin cơ bản ở branch-b. Query đang bao gồm cả hai branch.

Policy mẫu không cho sort toàn query theo AMOUNT. Không chỉ kiểm tra quyền amount của dòng đầu hoặc trang hiện tại, vì thứ tự đã dùng giá trị của các row khác trước khi chia trang.

Có thể yêu cầu thu hẹp query về một phạm vi đủ quyền hoặc từ chối sort theo hợp đồng. Không âm thầm bỏ các row hợp lệ chỉ để tránh kiểm tra mà không công bố semantics.

Nếu không xác định được scope/field permission cần thiết, không fallback thành cho sort trên mọi dữ liệu.

## 6. Kiểm soát toàn bộ chuỗi khóa

### 6.1. Secondary key cũng cần được phép

Caller gửi:

~~~json
{
  "sort": [
    {
      "key": "CREATED_AT",
      "direction": "DESC"
    },
    {
      "key": "internalRiskScore",
      "direction": "DESC"
    }
  ]
}
~~~

Khóa thứ hai có thể làm lộ risk giữa các hồ sơ cùng createdAt. Chỉ validate phần tử đầu không đủ.

Các khóa tự thêm ở server cũng phải được xem xét như khóa caller yêu cầu.

### 6.2. Tie-breaker an toàn và ổn định

Một order có thể là:

~~~text
createdAt DESC, public requestId DESC
~~~

nếu cả hai thuộc tính được phép quan sát/sử dụng và requestId là khóa duy nhất phù hợp.

Không dùng hidden risk, private timestamp hoặc internal flag làm tie-breaker chỉ vì chúng thuận tiện.

Tie-breaker giúp có thứ tự xác định khi khóa chính bằng nhau. Nó không tự tạo snapshot bất biến khi dữ liệu/permissions thay đổi giữa nhiều request.

### 6.3. Default phải được đánh giá như sort được yêu cầu

Không có sort parameter không có nghĩa được dùng bất kỳ order nội bộ nào.

Default cho một endpoint đọc thông thường không được âm thầm dùng internalPriority. Nếu endpoint chủ ý trả một thứ tự ưu tiên có điều kiện, phải cấp và mô tả mức công bố đó.

Invalid key nên được xử lý theo hợp đồng, ví dụ từ chối rõ ràng. Không coi invalid input như missing rồi rơi vào một default rộng/nhạy cảm khác.

### 6.4. Giới hạn số key và semantics

Có thể giới hạn số key caller yêu cầu, ví dụ tối đa hai key trước các tie-breaker server được phê chuẩn. Con số là policy sản phẩm, không phải bảo đảm an toàn chung.

Từ chối key canonical trùng hoặc các direction mâu thuẫn theo hợp đồng. Không để parser lấy khóa đầu còn backend lấy khóa cuối.

Null ordering, collation hoặc locale nếu được lựa chọn cũng phải nằm trong tập server cho phép. Không nhận raw SQL/function/collation string từ client.

## 7. Java minh họa compiler sort

Mã dưới đây là phác thảo, không phải thư viện hay ứng dụng độc lập. Actor/query scope đã được kiểm chứng; input có giới hạn cấu trúc.

~~~java
CompiledSort compileSort(
        Actor actor,
        AuthorizedQueryScope scope,
        SortCommand command) {

    sortLimits.requireAllowedUserKeyCount(
            command.requestedKeys().size());

    var inputs = command.requestedKeys().isEmpty()
            ? defaults.forEndpoint(actor, scope)
            : command.requestedKeys();

    var keys = new ArrayList<CompiledSortKey>();
    var seen = new HashSet<CanonicalSortKey>();

    for (var input : inputs) {
        var definition = sortRegistry.requirePublicKey(
                input.key());
        var direction = directions.decodeStrict(
                input.direction());

        sortPolicy.requireAllowedForWholeScope(
                actor, scope, definition, direction);

        if (!seen.add(definition.canonicalKey())) {
            throw new DuplicateSortKey();
        }

        keys.add(new CompiledSortKey(
                definition.serverExpression(),
                direction,
                definition.approvedNullOrdering(),
                definition.approvedComparison()));
    }

    tieBreakers.appendApprovedUniqueKeys(
            actor, scope, keys, seen);

    return new CompiledSort(
            List.copyOf(keys),
            scope.reference(),
            scope.permissionVersion(),
            sortPolicy.version());
}
~~~

### 7.1. Những phần phải có thẩm quyền

serverExpression do registry cung cấp, không lấy từ input. Nó phải là column/expression đã được đánh giá về dữ liệu và chi phí.

requireAllowedForWholeScope kiểm tra quyền sử dụng key cho tập query hiện tại theo contract, không chỉ quyền đọc chung của actor.

appendApprovedUniqueKeys không được là một chỗ khác tự nối internalRiskScore. Các khóa được thêm cũng cần kiểm tra và ghi nhận.

Các helper phải dùng validation bắt buộc, không dùng Java assert cho bảo mật.

### 7.2. Parameter binding không thay allowlist identifier

Bind parameter phù hợp cho các giá trị như tenant, filter và boundary của cursor. Không thể xem một raw tên field/expression người dùng gửi là an toàn chỉ vì các value khác đã bind.

Không nối input direction hoặc property path tùy ý vào ORDER BY. Compiler ánh xạ từ các giá trị hữu hạn được phép sang cấu trúc query do server kiểm soát.

Một key hợp lệ về cú pháp SQL nhưng nhạy cảm vẫn phải bị policy chặn. Chống injection và chống disclosure là hai kiểm soát khác nhau.

### 7.3. Error không cần liệt kê mọi field nội bộ

Có thể trả một code như SORT_NOT_ALLOWED hoặc SORT_SCOPE_NOT_SUPPORTED theo hợp đồng.

Không tiết lộ field bí mật tồn tại, tên bảng/join hoặc chi tiết “khóa này chứa mức rủi ro của khách hàng X” để giải thích.

Nếu trả danh sách allowed keys cho UI, danh sách đó cũng phải theo quyền/endpoint và chỉ là một ảnh chụp; lúc command/query đến vẫn cần kiểm tra.

## 8. Derived key và coarse bucket không tự giải quyết disclosure

### 8.1. Đổi tên không đổi thông tin

Một expression đơn điệu của score có thể giữ nguyên thứ tự score. Trả vị trí thay vì giá trị vẫn có thể làm lộ quan hệ.

Một key hash hoặc mã biến đổi cũng cần được đánh giá theo thông tin mà order/thay đổi order công bố. Nó không trở thành an toàn chỉ vì caller không đọc được biểu thức gốc.

### 8.2. Bucket là một lựa chọn công bố có chủ đích

Sản phẩm có thể cho biết PUBLIC_PRIORITY_BAND như LOW/NORMAL/HIGH theo chính sách.

Nếu cho sort theo band, cần chấp nhận và mô tả rằng caller có thể quan sát mức phân nhóm tương ứng. Trong cùng band, dùng các tie-breaker đã được phép, chẳng hạn createdAt/requestId, thay vì score gốc.

Không gọi đó là “đã ẩn hoàn toàn risk” nếu thứ tự vẫn sắp chi tiết theo risk bên trong nhóm.

### 8.3. Aggregate/group order cũng có thể nhạy cảm

Sắp khách hàng theo tổng nghĩa vụ, số cảnh báo hoặc số giao dịch bị chặn có thể tiết lộ dữ liệu liên quan dù các record con không được trả.

Quyền xem profile cha không tự cấp quyền dùng mọi aggregate của con làm sort. Cần policy cho đúng thông tin tổng hợp và phạm vi, bao gồm các phép suy ra từ nhóm nhỏ hoặc truy vấn lặp nếu có yêu cầu bảo vệ.

## 9. Query phải giữ scope trước kết quả order/page về mặt logic

### 9.1. Không sort/top-k trên tập rộng rồi lọc quyền

Pipeline nguy hiểm:

~~~text
Lấy top 20 trên toàn tập theo một khóa.
Bỏ row ngoài quyền ở application.
Trả phần còn lại và metadata của tập rộng.
~~~

Số dòng thiếu, boundary hoặc count có thể phản ánh các row ngoài scope. Nếu khóa cũng nhạy cảm, rò rỉ còn lớn hơn.

Cần query logic:

~~~text
tập được phép đọc
    → điều kiện tìm/lọc được chấp nhận
    → sort đã được cấp
    → pagination/output theo hợp đồng
~~~

Thứ tự vật lý của optimizer không nhất thiết giống vị trí các clause trong câu SQL. Điều cần bảo đảm là semantics của query và dữ liệu công bố.

### 9.2. Không dùng field nhạy cảm chỉ vì không SELECT nó

~~~sql
SELECT request_id, public_code
FROM purchase_request
WHERE tenant_id = :verified_tenant_id
ORDER BY internal_risk_score DESC;
~~~

Không có score trong projection nhưng order vẫn phụ thuộc score. Query này không phù hợp cho view bị cấm sử dụng risk làm tiêu chí quan sát.

Tương tự với hidden join/aggregate, null ordering hoặc subquery.

### 9.3. Scope phải đến từ nguồn có thẩm quyền

Client có thể đề nghị branch filter, nhưng không tự xác định allowedBranchIds.

Nếu scope rỗng, không bỏ điều kiện scope để sort toàn bảng. Nếu sort không được phép trong scope hiện tại, không chạy query rộng rồi cố redact sau.

Count, facets, ranking explanation và export cũng phải tuân theo policy dữ liệu của chúng.

## 10. Cursor không được trở thành bản sao khóa bí mật

### 10.1. Base64 hoặc chữ ký không che nội dung

Một cursor chứa:

~~~json
{
  "lastRiskScore": 91,
  "lastResourceId": "request-88"
}
~~~

có thể lộ trực tiếp score nếu chỉ được encode hoặc ký.

Chữ ký bảo vệ tính toàn vẹn theo giao thức, không tự tạo tính bí mật. Một cursor có mã hóa/opaque cũng không sửa được việc order ngoài response đang làm lộ tương quan score.

Thiết kế phải giải quyết cả khóa sort được phép lẫn dữ liệu cursor.

### 10.2. Chỉ dùng boundary đã được phép hoặc trạng thái opaque phù hợp

Với sort an toàn createdAt DESC, requestId DESC, boundary có thể dựa vào các giá trị được phép của chính representation.

Ví dụ query trang tiếp theo, giả định hai field không null và semantics so sánh đã được xác định:

~~~sql
SELECT r.request_id, r.public_code, r.created_at
FROM purchase_request r
WHERE r.tenant_id = :verified_tenant_id
  AND r.branch_id IN (:authorized_branch_ids)
  AND (
       r.created_at < :last_created_at
    OR (
         r.created_at = :last_created_at
         AND r.request_id < :last_request_id
       )
  )
ORDER BY r.created_at DESC, r.request_id DESC
LIMIT :page_size;
~~~

Đây là ví dụ khái niệm; cú pháp giới hạn/binding và semantics kiểu dữ liệu cần phù hợp backend thực tế. Các ràng buộc object scope khác vẫn cần được thêm nếu policy yêu cầu.

Không lấy boundary rời rạc do client tự khai làm bằng chứng quyền. Cursor cần được kiểm chứng theo hợp đồng.

### 10.3. Ràng buộc cursor với query và view

Các phụ thuộc có thể gồm:

~~~text
tenant
caller hoặc phạm vi view được cấp
query/filter canonical
toàn bộ sort keys/directions/null/comparison policy
result snapshot hoặc version nếu có
permission/projection/sort policy version
purpose và thời hạn
~~~

Cursor của một operator được sort AMOUNT không được dùng để mở cùng thứ tự/field cho người chỉ đọc thông tin cơ bản.

Khi query hoặc quyền thay đổi, có thể yêu cầu bắt đầu lại theo policy. Không fallback sang một sort khác mà vẫn giả vờ đang tiếp tục cùng tập.

### 10.4. Tie-breaker không phải snapshot isolation

Một khóa duy nhất ở cuối giúp order xác định trên tập không đổi. Nó không bảo đảm mọi trang luôn phản ánh một snapshot nếu dữ liệu đang thêm, xóa hoặc thay giá trị sort.

Nếu nghiệp vụ cần một tập ổn định cho báo cáo/quyết định, cần cơ chế snapshot hoặc manifest phù hợp. Với quyền hiện tại, vẫn phải thực thi policy đọc tương ứng.

Đừng dùng hidden timestamp/score để “làm pagination ổn định” khi caller không được quan sát khóa đó.

### 10.5. Field scope phải áp dụng trên toàn truy vấn

Không kiểm tra quyền AMOUNT của các row đã được chọn vào page rồi coi sort là hợp lệ. Các row ngoài trang cũng có thể ảnh hưởng vị trí và boundary.

Một policy có thể cho sort amount sau khi query được thu hẹp rõ ràng về branch đủ quyền. Việc thu hẹp phải được kiểm chứng và mô tả, không là lọc âm thầm ngoài hợp đồng.

## 11. Sort hiển thị khác quy tắc chọn việc để thực hiện

### 11.1. Chọn top-k có thể tạo hiệu ứng nghiệp vụ

Ví dụ endpoint “xử lý 10 hồ sơ tiếp theo” có thể dùng order để quyết định item nào được approve/execute.

Nếu quy tắc nghiệp vụ yêu cầu xử lý theo ưu tiên hoặc tuổi hồ sơ, không để caller truyền một sort tùy ý rồi thay chính sách lựa chọn.

Quyền đọc/sort một field không tự cấp quyền dùng field đó để điều khiển luồng chi trả hoặc bỏ qua hồ sơ bắt buộc.

### 11.2. Server quyết định selection policy bắt buộc

Một luồng có thể là:

~~~text
Xác minh quyền action và tenant.
Xác định tập item đủ điều kiện.
Áp selection policy có thẩm quyền.
Claim/khóa/version những item được chọn.
Kiểm tra lại quyền và state cần thiết.
Thực hiện transaction/operation theo hợp đồng.
~~~

UI có thể hiển thị một thứ tự khác mà vẫn không thay selection policy của worker.

Nếu cho phép caller chọn mode ưu tiên, các mode phải là lựa chọn nghiệp vụ được cấp, không raw ORDER BY.

### 11.3. Endpoint selection cũng có thể công bố thứ tự gián tiếp

Nếu caller kích hoạt “next” và nhìn toàn bộ item được chọn, họ có thể quan sát tác động của selection policy nội bộ.

Tách endpoint không tự loại bỏ disclosure. Cần kiểm soát action, output và mức thông tin caller được biết.

Worker có thể dùng một thứ tự nội bộ hợp lệ với thẩm quyền dịch vụ. Không tái sử dụng query đó làm default public list chỉ vì có sẵn.

### 11.4. Per-item authorization vẫn cần thiết

Một sort/selection được phép không biến các item đã chọn thành được duyệt vô điều kiện.

Mỗi item vẫn cần state, revision, scope, hạn mức, phân tách nhiệm vụ và bảo vệ chống trùng tương ứng. Khi có batch/ngoại tác, phải quản lý transaction và operation theo hợp đồng.

## 12. Chi phí, cache và các đường output khác

### 12.1. Sort field công khai vẫn có thể rất đắt

Sort trên expression, join hoặc tập lớn có thể tiêu thụ nhiều tài nguyên dù pageSize nhỏ.

Allowlist dữ liệu nên đi cùng giới hạn số key, query/filter, page depth, deadline, concurrency và khả năng hỗ trợ của index/backend.

Không kết luận cứ field có index là mọi tổ hợp scope/sort đều rẻ. Cần đánh giá dữ liệu và kế hoạch đại diện trên backend được chọn.

### 12.2. Cache phải giữ toàn bộ semantics của order

Các phụ thuộc có thể gồm:

~~~text
tenant và row/field scope
actor/permission version nếu cần
query/filter
canonical sort chain và direction
null/comparison/projection policy
pagination/snapshot
~~~

Cache key chỉ có tên key đầu tiên có thể trộn các secondary key hoặc direction khác nhau. Cache theo role cũng có thể trộn hai người có object scope khác nhau.

Nếu quyền sort hoặc field thay đổi, dữ liệu/cursor cache phải xử lý theo cam kết thu hồi. Không phục vụ lại một page cũ có order nhạy cảm trái quyền hiện tại.

### 12.3. Metadata không được giữ phụ thuộc bí mật ngoài policy

Nếu public representation không được thay theo hidden score, không dựng ETag, sortValues hoặc ranking explanation từ score rồi trả cho client.

Một internal version chứa thay đổi private có thể không phù hợp làm public version của view. Cần xác định metadata nào được phép công bố và dựa trên dữ liệu nào.

Không trả raw query plan/expression hoặc lastSortValues cho người không được xem, kể cả trong lỗi cursor.

### 12.4. Export và notification dùng policy tương ứng

UI sort an toàn không bù được file export còn sắp/đính kèm hidden score hoặc cột nội bộ.

Export cần row/field/sort scope riêng theo quyền được cấp. Nếu rộng hơn view thường, điều đó phải có chủ đích và kiểm tra lúc tạo/tải theo hợp đồng.

Thông báo “top hồ sơ” hoặc danh sách đề xuất cũng có thể công bố rank. Không chuyển một thứ tự bị cấm ở API sang email/file rồi coi không còn là disclosure.

## 13. Audit quyết định sort

Có thể ghi:

~~~text
actor/tenant và action
endpoint/query reference
requested public keys
canonical keys thực sự được áp dụng
default/tie-breaker được thêm
scope và policy version liên quan
cursor/snapshot reference
execution outcome/cost class cần thiết
~~~

Không log nguyên dữ liệu nhạy cảm hoặc cursor bí mật theo mặc định. Danh sách allowed keys ở client và sort thực tế ở backend cần có thể đối chiếu khi điều tra.

Một nhãn “sort=default” không đủ nếu default thay đổi hoặc phụ thuộc một rule nội bộ nhạy cảm.

Các tín hiệu như thử nhiều alias/key bị cấm, đổi ASC/DESC liên tục, reuse cursor rộng quyền hoặc dùng export sau khi sort bị chặn cần được xem xét trong ngữ cảnh, không tự chứng minh một cuộc tấn công.

## 14. Kiểm thử thông tin được công bố qua order

### 14.1. Fixture cần buộc xuất hiện tie

Chuẩn bị ba request caller được xem:

~~~text
R1, R2, R3:
  cùng createdAt công khai
  requestId công khai, duy nhất
  display fields cố định

Internal risk:
  R1 = 10
  R2 = 90
  R3 = 20
~~~

Giữ policy mẫu: default là createdAt DESC và requestId DESC theo semantics ID đã xác định; risk không được dùng.

Fixture cùng createdAt giúp phát hiện một tie-breaker bí mật. Nếu tất cả timestamp đều khác nhau, test có thể không bao giờ chạm secondary key nguy hiểm.

Thêm request ở tenant/scope khác và một actor có field permission khác để kiểm tra biên.

### 14.2. Ma trận tình huống

| Tình huống | Điều phải kiểm chứng |
|---|---|
| Yêu cầu sort CREATED_AT hợp lệ | Đúng contract và scope; tie-breaker được phép |
| Yêu cầu internalRiskScore trực tiếp | Không chạy sort nhạy cảm |
| Dùng alias/nested path/expression khác | Không vượt registry/policy bằng cách đổi cách viết |
| Key đầu hợp lệ, key thứ hai bị cấm | Không chỉ validate phần tử đầu |
| Không gửi sort | Default không dùng field nhạy cảm |
| Invalid sort key | Không rơi vào default nhạy cảm hoặc fallback rộng |
| Hai key alias cùng canonical field | Trùng/mâu thuẫn được xử lý rõ ràng |
| ASC/DESC hoặc null/collation không hỗ trợ | Không đưa raw cấu trúc vào query |
| AMOUNT trong scope hỗn hợp quyền field | Không sort các row mà amount chưa được phép sử dụng |
| Thu hẹp rõ về scope đủ quyền | Có thể cho sort theo contract, không chặn nhầm mọi trường hợp |
| Nullable hidden flag | Không lộ nhóm null/non-null qua order |
| Bucket công khai, risk nội bộ thay đổi trong bucket | Không có hidden tie-breaker làm đổi order |
| Cursor chứa raw hidden sort value | Không công bố qua body/token/log lỗi |
| Cursor của view/actor rộng hơn | Không dùng làm quyền xem/order mới |
| Quyền đổi sau khi cache/cursor được tạo | Xử lý đúng cam kết hiệu lực |
| Sort/top-k rồi mới lọc quyền | Test phát hiện row count/boundary/metadata sai scope |
| Export/notification dùng default riêng | Không công bố một rank bị cấm ở API chính |
| Endpoint select-next nhận raw sort | Không thay selection policy bắt buộc ngoài quyền |
| Page size nhỏ với sort expression đắt | Execution budget vẫn được áp dụng |
| Read request bị từ chối sort | Không tạo job/hiệu ứng nghiệp vụ hoặc rò query plan |
| Redaction field khỏi JSON | Vẫn kiểm tra rằng order/secondary key không dùng field đó |

### 14.3. Thay private facts, giữ public facts

Chạy một query hợp lệ và ghi public view. Sau đó thay risk score của R1–R3 mà không đổi các facts được công bố và quyền caller.

Chạy lại cùng query.

Theo policy mẫu, thứ tự, boundary trang và public metadata không được thay chỉ vì risk đổi. Nếu có khác biệt, tìm:

~~~text
default sort bí mật
secondary key
derived expression/alias
global/private result version được trả ra
sortValues hoặc cursor payload
cache/ranking logic phụ thuộc risk
~~~

So sánh theo hợp đồng, chỉ loại các biến động công khai hợp lệ như request ID. Đối với cursor có nonce ngẫu nhiên, không buộc byte token giống nhau; kiểm tra semantics/binding và dữ liệu được chứa/công bố.

Test này không chứng minh đã loại mọi side channel thời gian, nhưng rất hữu ích để phát hiện phụ thuộc dữ liệu trái policy.

### 14.4. Kiểm thử hai mức bucket

Nếu PUBLIC_PRIORITY_BAND được policy cho công bố:

~~~text
Case A:
  giữ nguyên band;
  chỉ đổi score nội bộ bên trong band.
  Public order không được đổi vì score.

Case B:
  thay band bằng một thay đổi được phép công bố.
  Order có thể đổi theo đúng sort band.
~~~

Không làm mất chức năng hợp lệ chỉ để mọi output bất biến. Cần kiểm tra đúng ranh giới thông tin được chủ ý công bố.

### 14.5. Kiểm thử quyền field trên scope hỗn hợp

Actor đọc được hồ sơ của branch-a và branch-b, nhưng chỉ được dùng amount cho branch-a theo policy mẫu.

Thử:

~~~text
Query cả hai branch + AMOUNT:
    không được sort toàn tập theo amount.

Query chỉ branch-a sau kiểm chứng + AMOUNT:
    có thể hợp lệ nếu capability còn đúng.

Query branch-a + AMOUNT + hidden risk:
    vẫn bị chặn ở khóa không được phép.
~~~

Không xác định quyền chỉ từ các row tình cờ rơi vào trang đầu. Các trang sau hoặc boundary còn có thể chịu ảnh hưởng của dữ liệu không được cấp.

### 14.6. Kiểm thử row scope và metadata

Thêm hoặc đổi các request ngoài scope trong storage/index. Chúng không được đi vào danh sách, count hoặc boundary trái hợp đồng.

Đặc biệt kiểm tra query lấy top-k trên tập rộng rồi lọc ở application. Số dòng trên trang hoặc total có thể thay đổi dù caller không được biết các row bổ sung.

Kiểm tra cả HEAD/metadata, file export và endpoint report nếu chúng công bố representation hoặc rank liên quan.

### 14.7. Kiểm thử trên query backend thật

Unit test registry giúp phát hiện key bị cấm. Cần thêm integration test để đối chiếu ORDER BY/DSL thực tế và kết quả.

Kiểm tra:

- Field expression đúng ánh xạ công khai.
- Direction/null/comparison theo contract.
- Tie-breaker đúng và duy nhất theo yêu cầu.
- Tenant/object scope được thực thi.
- Cursor dùng đúng chuỗi khóa và semantics.
- Không có một lớp repository tự nối order khác.

Mock một compiler trả sẵn danh sách an toàn không phát hiện được default ở persistence/query layer.

## 15. Tình huống thực hành: đã giấu score nhưng vẫn sort trong bucket

Một API trả các hồ sơ ở cùng priority band công khai, không có internalRiskScore trong response.

Product cho phép sort band rồi createdAt. Repository lại dùng:

~~~text
ORDER BY public_band DESC,
         internal_risk_score DESC,
         created_at DESC
~~~

Trong cùng band, caller vẫn thấy hồ sơ nào có risk cao hơn. Mã hóa cursor không làm mất thứ tự đã công bố.

Cần sửa:

1. Xác định thông tin band nào được phê chuẩn công bố.
2. Chỉ dùng band đó làm khóa thứ nhất.
3. Dùng createdAt và một public unique tie-breaker phù hợp cho phần còn lại.
4. Loại risk gốc khỏi cả query order, cursor và metadata/debug.
5. Kiểm thử thay score nhưng giữ band/public facts không làm order đổi.
6. Rà soát export, alias, cache và default khác dùng chung repository.

Nếu nghiệp vụ thật sự cần reviewer được thấy thứ tự risk chi tiết, phải cấp một view/action có chủ đích cho đúng người và scope. Không mở nó cho mọi reader qua một key recommended.

### 15.1. Chỉ chặn parameter có thể bỏ sót default

Caller không cần biết tên field nếu API tự trả “ưu tiên nhất” theo một khóa riêng tư.

Default cũng là quyết định công bố và phải xuất hiện trong specification, audit và test. Không coi việc client không gửi sort như bằng chứng client không quan sát thông tin nhạy cảm.

### 15.2. Selection output cũng cần được đánh giá

Nếu một endpoint “xử lý tiếp” dùng risk nội bộ và trả toàn bộ danh sách theo đúng thứ tự chọn, nó có thể tạo một oracle tương tự public sort.

Quy tắc thực thi nội bộ có thể hợp lệ, nhưng caller của endpoint phải có thẩm quyền action/output tương ứng. Không dùng một chức năng có side effect để vô tình mở rank vốn bị cấm ở endpoint đọc.

## 16. Giữ policy và triển khai đồng bộ

Một thay đổi thêm field vào entity không được tự làm field đó sortable. Một alias mới hoặc một default mới cũng cần được đánh giá dữ liệu, scope, cursor và chi phí.

Có thể lưu registry cạnh metadata endpoint và tạo tài liệu/kiểm tra độ bao phủ. Tuy nhiên, test chỉ đọc lại registry không chứng minh expression trong registry đúng ngữ nghĩa bảo mật.

Giữ các ca độc lập từ policy, như:

~~~text
reader không quan sát risk order
mọi sort key trong chain đều được kiểm tra
hidden score không làm đổi order của public view
amount sort không vượt field scope
cursor/export không mang khóa bí mật
~~~

Nếu quyền thay đổi giữa compile và execute, cần xử lý theo cam kết nhất quán/thu hồi đã chọn. Đừng tuyên bố kiểm tra quyền “hiện tại tức thời” nếu kiến trúc thực tế chỉ có một snapshot ở đầu request.

## 17. Khung đặc tả sensitive sort prevention

~~~text
Endpoint/action và tập row:
Public sort keys:
Expression/nguồn dữ liệu thực sự của mỗi key:
Thông tin so sánh được phép công bố:
Capability và field/scope coverage cần có:

Default và mọi secondary/tie-breaker:
Direction, null và comparison/collation policy:
Derived/bucket/aggregate sort nếu có:
Raw property path/expression được xử lý thế nào:

Query/pagination/cursor binding:
Dữ liệu nào xuất hiện trong cursor/metadata:
Cache, export, report và notification:
Selection policy cho action top-k nếu liên quan:
Execution budget và concurrency:

Audit và test thay private facts:
Test mixed scope, alias, defaults và backend query:
~~~

## 18. Câu hỏi tự kiểm tra

1. Field nào bị ẩn trong JSON nhưng vẫn có thể dùng làm sort?
2. Default hoặc tie-breaker có phụ thuộc score/flag/time riêng tư không?
3. Một actor có quyền amount trên một số row có được sort cả scope theo amount không?
4. Alias recommended/publicPriority thực sự được tính từ những facts nào?
5. Trong cùng bucket công khai, key nào quyết định thứ tự?
6. Cursor có chứa giá trị bí mật dù được encode/ký không?
7. Các row ngoài scope có ảnh hưởng top-k/count/boundary trước khi lọc không?
8. Export hoặc endpoint chọn việc tiếp theo có mở lại thứ tự bị cấm không?
9. Thay private facts mà giữ public facts có làm public representation đổi trái policy không?
10. Field mới trong entity hoặc query layer có tự trở thành sortable mà không qua hợp đồng API không?

Nguyên tắc cần giữ là **thứ tự quan sát được cũng phải nằm trong phạm vi thông tin caller được phép biết**. Registry, query, tie-breaker, cursor và các đường output đều phải bảo vệ cùng ranh giới đó.
