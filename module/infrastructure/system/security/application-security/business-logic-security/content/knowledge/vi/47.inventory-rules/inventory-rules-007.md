# Kiểm toán biến động tồn kho (Inventory movement audit)

Một hệ thống có thể xác thực đúng người dùng và vẫn bị lạm dụng nếu cho phép xuất hàng hai lần cho cùng một lệnh, giữ hàng của kho khác hoặc sửa trực tiếp số dư mà không để lại căn cứ. Kiểm toán biến động tồn kho giúp trả lời: **Tồn kho đã thay đổi thế nào, do nghiệp vụ nào, ai thực hiện và thay đổi đó có hợp lệ không?**

Trong chương **Inventory Rules**, chủ đề này liên kết các quy tắc tồn kho với quyền theo đối tượng, state machine, transaction và idempotency. Đây là một phần của bảo mật logic nghiệp vụ: bảo vệ quá trình thay đổi hàng hóa và khả năng giải trình của hệ thống, thay vì chỉ ghi lại các yêu cầu HTTP.

Sau bài học, bạn có thể:

- Xác định những bất biến cần giữ giữa số dư tồn kho và sổ biến động.
- Thiết kế bản ghi biến động đủ để truy nguyên một nghiệp vụ mà không tin dữ liệu do client tự khai.
- Đặt cập nhật số dư, ghi biến động và chống xử lý trùng vào cùng ranh giới transaction.
- Kiểm tra quyền, trạng thái, phê duyệt và điều kiện bù trừ trước khi thay đổi tồn kho.
- Đối soát và xây dựng các tình huống kiểm thử lạm dụng logic tồn kho.

## 1. Phân biệt số dư, sổ biến động và log kỹ thuật

**Số dư tồn kho** cho biết trạng thái hiện tại của một đối tượng tồn kho. **Sổ biến động** ghi lại các thay đổi nghiệp vụ đã được chấp nhận. **Log kỹ thuật** hỗ trợ tìm lỗi thực thi, chẳng hạn một API đã được gọi, truy vấn bị timeout hoặc consumer xử lý thất bại.

| Thành phần | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| Số dư | Hiện còn bao nhiêu hàng và bao nhiêu đã được giữ? | SKU-A ở kho W1: có 12, giữ 7 |
| Sổ biến động | Thay đổi nào tạo nên số dư hiện tại? | Giữ thêm 4 đơn vị cho đơn O-C |
| Dấu vết phê duyệt | Ai cho phép một thay đổi đặc biệt? | Quản lý duyệt điều chỉnh thiếu 2 đơn vị |
| Log kỹ thuật | Yêu cầu được thực thi như thế nào? | Request timeout sau khi database đã commit |

Một dòng `POST /inventory/adjust returned 200` không chứng minh được lượng điều chỉnh, số dư trước và sau, căn cứ hay quyền phê duyệt. Ngược lại, một request bị từ chối không nên xuất hiện như một biến động tồn kho thành công.

Có thể ghi nhận lần thử thất bại trong luồng sự kiện bảo mật riêng. Luồng đó phải phân biệt rõ `DENIED`, `FAILED` và `COMMITTED`; không được đưa sự kiện thất bại vào phép cộng tính tồn kho.

## 2. Chốt mô hình tồn kho trước khi thiết kế audit

### 2.1. Khóa đối tượng và đơn vị tính

Trong ví dụ của bài học, một đối tượng tồn kho được xác định bởi:

```text
InventoryKey = (tenant_id, warehouse_id, sku_id)
```

Nếu nghiệp vụ quản lý theo lô, hạn sử dụng, chủ sở hữu, trạng thái chất lượng hoặc số serial, các chiều đó phải xuất hiện trong mô hình khóa hoặc mô hình phân bổ tương ứng. Không cộng gộp hàng cách ly vào hàng có thể bán chỉ vì cùng SKU.

Các phép tính dưới đây dùng số nguyên theo đơn vị cơ sở. Nếu sản phẩm được đo theo khối lượng hoặc thể tích, dùng kiểu số thập phân chính xác và quy tắc làm tròn thống nhất. Không dùng số thực dấu phẩy động để quyết định đủ hàng.

### 2.2. Ba đại lượng cần phân biệt

Với mỗi `InventoryKey`, đặt:

```text
H = on_hand       // số lượng đang được quản lý trong ngăn tồn kho này
R = reserved      // phần đã được giữ cho các cam kết còn hiệu lực
A = available     // phần có thể tiếp tục phân bổ

A = H - R
H >= 0
R >= 0
R <= H
```

Đây là chính sách của mô hình minh họa: chỉ giữ hàng đang có và không cho tồn kho âm. Hệ thống cho phép backorder phải mô hình hóa nhu cầu chưa được đáp ứng riêng; không tự bỏ kiểm tra `R <= H` rồi vẫn coi `available` là lượng hàng có thể giao ngay.

`on_hand` ở đây là số lượng thuộc ngăn đang xét. Hàng đang vận chuyển giữa hai kho sẽ được mô hình hóa riêng ở phần chuyển kho.

### 2.3. Không phải biến động nào cũng làm thay đổi hàng vật lý

| Nghiệp vụ | Delta H | Delta R | Delta A | Điều kiện điển hình |
| --- | ---: | ---: | ---: | --- |
| Nhập hàng `RECEIPT` | +q | 0 | +q | Có căn cứ nhập hợp lệ và chưa ghi nhận trùng |
| Giữ hàng `RESERVE` | 0 | +q | -q | Đơn hợp lệ, còn đủ hàng có thể phân bổ |
| Nhả giữ `RELEASE` | 0 | -q | +q | Đúng reservation còn hiệu lực, chưa nhả hoặc xuất hết |
| Xuất hàng đã giữ `ISSUE_RESERVED` | -q | -q | 0 | Có allocation tương ứng, được phép xuất |
| Điều chỉnh tăng `ADJUST_UP` | +q | 0 | +q | Đúng thẩm quyền và có căn cứ |
| Điều chỉnh giảm `ADJUST_DOWN` | -q | 0 | -q | Không vi phạm phần đã giữ; có phê duyệt nếu cần |

Bảng giả định `q > 0`. API nên nhận số lượng dương cùng loại thao tác, rồi server suy ra dấu của delta. Không để người gọi dùng `q = -5` để biến một thao tác xuất thành nhập.

Nhả giữ hàng không làm tăng `on_hand`. Xuất hàng đã giữ phải giảm cả `on_hand` lẫn `reserved`; chỉ giảm một trong hai sẽ làm sai số lượng có thể phân bổ hoặc để lại reservation không còn hàng bảo đảm.

## 3. Những bất biến mà sổ biến động phải bảo vệ

### 3.1. Số dư bằng tổng các biến động được chấp nhận

Nếu sổ bắt đầu từ trạng thái rỗng và có bản ghi mở đầu cho lượng hàng ban đầu:

```text
H hiện tại = SUM(delta_on_hand)
R hiện tại = SUM(delta_reserved)
```

Nếu đối soát từ một checkpoint tại version `v0`:

```text
H(v) = H(v0) + SUM(delta_on_hand của các entry có v0 < version <= v)
R(v) = R(v0) + SUM(delta_reserved của các entry có v0 < version <= v)
```

Checkpoint phải gắn với vị trí cụ thể trong sổ và được tạo nhất quán với số dư. Một timestamp do client gửi không phải ranh giới đối soát đáng tin cậy: giao dịch có thể đến muộn, các máy có thể lệch giờ và nhiều entry có thể cùng timestamp.

### 3.2. Mỗi entry phải nối tiếp trạng thái trước đó

Với mỗi đối tượng tồn kho:

```text
after_on_hand  = before_on_hand  + delta_on_hand
after_reserved = before_reserved + delta_reserved

before của entry tiếp theo = after của entry trước
balance_version của entry tiếp theo = balance_version trước + 1
```

Trong thiết kế minh họa, version thuộc **từng khóa tồn kho**, bắt đầu từ 0 và tăng trong cùng transaction cập nhật số dư. Mỗi operation chỉ tạo một entry đã tổng hợp cho mỗi khóa nó tác động. Vì vậy có thể đặt ràng buộc duy nhất trên:

```text
(tenant_id, warehouse_id, sku_id, balance_version)
```

Không dùng sequence toàn hệ thống để suy luận rằng mỗi kho phải có dãy version liên tục. Cũng không dùng sequence cấp ngoài transaction làm bằng chứng rằng một khoảng trống chắc chắn tương ứng với entry bị xóa: một số cơ chế sequence vẫn tiêu thụ giá trị khi giao dịch rollback.

Các trường `before` và `after` hữu ích cho điều tra nhưng cũng là dữ liệu do phần mềm ghi. Chúng phải được tạo từ số dư đã khóa và kiểm tra với delta; bản thân việc có đủ cột không bảo đảm dữ liệu đúng.

### 3.3. Mỗi hiệu ứng nghiệp vụ chỉ được áp dụng một lần

Cần phân biệt hai loại trùng:

- **Trùng yêu cầu:** client gửi lại cùng một command vì timeout. Khóa idempotency giúp trả lại kết quả đã commit.
- **Trùng hiệu ứng nghiệp vụ:** client thay khóa idempotency rồi yêu cầu xuất lại cùng phần hàng của cùng chứng từ. Hệ thống vẫn phải phát hiện bằng định danh hiệu ứng nghiệp vụ và trạng thái chứng từ.

Một `idempotency_key` mới không tạo ra quyền xuất thêm hàng. Với nghiệp vụ xuất từng phần, định danh hiệu ứng có thể dựa trên chứng từ xuất, dòng chứng từ, lần xuất được cấp hợp lệ và loại hiệu ứng. Không đặt unique chỉ trên mã đơn nếu đơn được phép xuất nhiều lần; cũng không tin một mã lần xuất tùy ý do client tự tạo.

Ngoài tính duy nhất của từng hiệu ứng, tổng lượng giữ, xuất, nhả hoặc hoàn trả phải nằm trong lượng còn được phép của đối tượng nghiệp vụ. Đây là kiểm tra trạng thái và tổng lượng, không thể thay hoàn toàn bằng một unique constraint.

### 3.4. Bất biến phải được kiểm tra trong cùng ranh giới nhất quán

Hai request đều đọc `available = 5` rồi mỗi request giữ 4 sẽ gây vượt tồn nếu chúng cùng quyết định trên dữ liệu cũ.

Có thể dùng khóa hàng hoặc cập nhật có điều kiện kèm kiểm tra số hàng bị ảnh hưởng. Điều kiện đủ hàng, thay đổi số dư, thay đổi reservation và ghi entry phải cùng tham gia cơ chế cạnh tranh đó. Chỉ kiểm tra trước khi mở transaction không đủ.

## 4. Thiết kế một bản ghi biến động có thể truy nguyên

Nên tách **operation** đại diện cho một nghiệp vụ khỏi **movement entry** đại diện cho tác động lên một khóa tồn kho. Chuyển kho có thể là một operation tạo nhiều entry liên quan.

### 4.1. Dữ liệu ở cấp operation

| Nhóm | Trường gợi ý | Ý nghĩa |
| --- | --- | --- |
| Định danh | `tenant_id`, `operation_id`, `operation_type` | Xác định phạm vi và nghiệp vụ |
| Chống trùng | `caller_id`, `idempotency_key`, `request_fingerprint` | Ràng buộc một key với đúng nội dung yêu cầu |
| Căn cứ | `source_type`, `source_id`, `source_line_id`, `effect_key` | Liên kết tới hiệu ứng nghiệp vụ cụ thể |
| Chủ thể | `initiated_by`, `executed_by` | Phân biệt người khởi tạo với service thực thi |
| Quyết định | `reason_code`, `approval_id`, `policy_version` khi cần | Giải thích vì sao thay đổi được chấp nhận |
| Truy vết | `correlation_id`, `causation_id` | Nối luồng xử lý và nguyên nhân trực tiếp |
| Kết quả | `completed_at`, `result` | Lưu kết quả nghiệp vụ dùng cho replay |

`policy_version` hữu ích nếu hệ thống cần giải thích một quyết định được đưa ra theo bộ quy tắc nào. Không cần lưu nguyên toàn bộ cấu hình hoặc dữ liệu nhạy cảm vào từng bản ghi.

Phạm vi unique của idempotency phải được quy định rõ, ví dụ:

```text
UNIQUE (tenant_id, caller_id, idempotency_key)
UNIQUE (tenant_id, effect_key)
```

Phạm vi thứ hai chỉ phù hợp khi `effect_key` đã mô tả đúng một hiệu ứng duy nhất. Fingerprint được server tính từ nội dung nghiệp vụ đã chuẩn hóa: loại thao tác, kho, SKU, số lượng, căn cứ và các tham số ảnh hưởng kết quả. Không hash tùy tiện chuỗi JSON thô rồi để thứ tự field hoặc cách biểu diễn số quyết định hai yêu cầu có giống nhau hay không.

### 4.2. Dữ liệu ở cấp entry

| Trường | Yêu cầu |
| --- | --- |
| `movement_id`, `operation_id` | Định danh entry và liên kết operation đã tạo ra nó |
| Khóa tồn kho đầy đủ | Luôn bao gồm tenant và các chiều quản lý cần thiết |
| `movement_type` | Loại thay đổi theo danh mục server kiểm soát |
| `delta_on_hand`, `delta_reserved` | Dấu và lượng thay đổi được tính theo loại nghiệp vụ |
| `before_on_hand`, `after_on_hand` | Trạng thái hàng trước và sau |
| `before_reserved`, `after_reserved` | Trạng thái giữ hàng trước và sau |
| `balance_version` | Thứ tự thay đổi của đúng đối tượng tồn kho |
| `recorded_at` | Thời điểm server/database ghi nhận |
| `effective_at` nếu cần | Thời điểm hiệu lực nghiệp vụ, phân biệt với thời điểm ghi |
| `reversal_of` nếu có | Liên kết entry gốc khi thực hiện bù trừ |

Nếu lưu `effective_at` để xử lý chứng từ đến muộn, không chèn lại version vào giữa lịch sử đã commit. Quy tắc tính báo cáo theo ngày hiệu lực phải tách khỏi thứ tự ghi nhận và phải nêu rõ cách xử lý kỳ đã khóa sổ.

Các khóa ngoại liên quan tới tenant phải bảo đảm không thể liên kết một entry của tenant A với operation hoặc chứng từ của tenant B. Quyền theo đối tượng vẫn cần được kiểm tra; khóa ngoại không thay thế authorization.

### 4.3. Dữ liệu nào không được lấy nguyên từ client?

Client có thể gửi ý định nghiệp vụ, chẳng hạn yêu cầu giữ 4 sản phẩm cho một dòng đơn. Server phải tự xác định hoặc xác minh:

- Tenant, người thao tác và quyền trên kho, SKU, đơn hàng.
- Trạng thái chứng từ và lượng còn được phép thực hiện.
- Delta, số dư trước/sau và version mới.
- Bằng chứng phê duyệt còn hiệu lực, đúng nội dung và đúng đối tượng.
- Định danh hiệu ứng và quan hệ với reservation hoặc allocation.

Một field như `approved: true`, `actor_id: admin` hay `before_on_hand: 100` trong request không phải bằng chứng đáng tin cậy.

## 5. Ghi số dư và movement trong cùng transaction

### 5.1. Luồng giữ hàng minh họa

Đoạn dưới là **mã giả**, nhấn mạnh thứ tự quyết định và ranh giới transaction, không phải API Java có thể chạy trực tiếp.

```text
reserve(authenticatedContext, command):
    principal = authenticate(authenticatedContext)
    validatePositiveQuantityAndBounds(command.quantity)
    scope = resolveAuthorizedTenantAndCaller(principal)
    authorizeObjects(principal, command.order, command.warehouse, command.sku)
    fingerprint = canonicalBusinessFingerprint(scope, command)

    result = transaction:
        claim = claimIdempotency(scope, command.key, fingerprint)

        if claim.alreadyCommitted:
            require claim.fingerprint == fingerprint
            require principal may access this operation and its result
            return claim.savedResult

        orderLine = lockOrderLine(command.orderLine)
        reservation = lockOrCreateReservationFor(orderLine, command.inventoryKey)
        balance = lockInventoryBalance(command.inventoryKey)

        require orderLine allows reservation
        require quantity <= orderLine.remainingReservableQuantity
        require balance.onHand - balance.reserved >= quantity
        require related objects belong to scope.tenant

        effect = claimAuthorizedBusinessEffect(orderLine, command)
        require effect has not already been applied

        before = snapshot(balance)
        balance.reserved += quantity
        balance.version += 1
        reservation.remainingQuantity += quantity

        appendMovement(
            type = RESERVE,
            deltaOnHand = 0,
            deltaReserved = quantity,
            before = before,
            after = balance,
            version = balance.version,
            actor = principal,
            effect = effect
        )

        result = buildBusinessResult(effect, balance.version)
        completeOperationWithSavedResult(result)
        appendOutboxEventIfNeeded(effect, balance.version)

    return result after successful commit
```

Việc tạo reservation chưa tồn tại phải có khóa duy nhất và cách xử lý cạnh tranh phù hợp. Với nhiều dòng đơn hoặc nhiều khóa tồn kho, mọi luồng liên quan phải dùng cùng thứ tự khóa để giảm nguy cơ deadlock.

Các điều kiện trạng thái có thể thay đổi đồng thời, như hủy đơn hoặc sửa lượng được phép giữ, phải được bảo vệ bằng cùng cơ chế khóa/version. Nếu quyền hoặc phê duyệt có thể bị thu hồi trong quá trình xử lý và nghiệp vụ yêu cầu thu hồi có hiệu lực ngay, thiết kế cũng phải có điểm kiểm tra nhất quán cho thay đổi đó.

### 5.2. Điều gì phải rollback cùng nhau?

Nếu không ghi được entry, transaction phải rollback cả số dư, reservation, dấu chống trùng và outbox tương ứng. Nếu transaction rollback, không trả kết quả như đã giữ hàng thành công.

Ngược lại, nếu commit thành công nhưng response bị mất, lần retry phải trả lại kết quả đã lưu. Không tự động tạo một thao tác nhả giữ chỉ vì tầng HTTP bị timeout: timeout không cho biết database đã commit hay chưa.

Ràng buộc duy nhất trong database giúp phân xử hai request đồng thời cùng key. Hàm `claimIdempotency` phải xử lý đúng transaction và cơ chế conflict của database được chọn. Không bắt một lỗi unique rồi tiếp tục dùng transaction đã bị database đánh dấu hỏng.

Nếu cùng key nhưng fingerprint khác, trả lỗi xung đột theo hợp đồng API; không coi đó là retry hợp lệ. Nếu dùng key khác cho cùng hiệu ứng, kiểm tra `effect_key` và trạng thái nghiệp vụ vẫn phải chặn áp dụng lần hai. Cách trả lại kết quả cũ hoặc trả xung đột cho trường hợp này cần thống nhất trong hợp đồng nghiệp vụ.

Không giữ khóa database trong lúc gọi một dịch vụ bên ngoài chậm. Nếu cần phê duyệt từ dịch vụ khác, lưu một trạng thái chờ và chỉ áp dụng biến động sau khi có quyết định hợp lệ, được gắn với đúng nội dung cần phê duyệt.

### 5.3. Vai trò của ràng buộc dữ liệu

Ở mức database, nên có các ràng buộc phù hợp với mô hình:

```text
CHECK on_hand >= 0
CHECK reserved >= 0
CHECK reserved <= on_hand
UNIQUE inventory_key + balance_version trong movement
UNIQUE idempotency_scope + idempotency_key
UNIQUE tenant_id + effect_key
FOREIGN KEY movement -> operation trong cùng tenant
```

Những dòng này mô tả ý tưởng ràng buộc, không phải một đoạn DDL hoàn chỉnh. Các quy tắc liên quan nhiều hàng, như tổng reservation còn hiệu lực bằng `reserved`, vẫn cần transaction và cơ chế cạnh tranh đúng; một `CHECK` trên hàng số dư không kiểm tra được toàn bộ lịch sử hoặc tất cả reservation.

## 6. Đọc một chuỗi biến động cụ thể

Giả sử SKU-A tại kho W1 có số dư đã đối soát ở version 20:

```text
H = 12
R = 3, gồm O-A giữ 2 và O-B giữ 1
A = 9
```

Các operation tiếp theo diễn ra tuần tự:

| Version | Nghiệp vụ | Delta H | Delta R | H sau | R sau | A sau |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 21 | Giữ 4 cho O-C | 0 | +4 | 12 | 7 | 5 |
| 22 | Xuất đủ 4 đã giữ của O-C | -4 | -4 | 8 | 3 | 5 |
| 23 | Hủy giữ 1 của O-B | 0 | -1 | 8 | 2 | 6 |
| 24 | Điều chỉnh thiếu 2 sau kiểm kê, đã được duyệt | -2 | 0 | 6 | 2 | 4 |

Các điểm cần đọc được từ sổ:

- Version 22 phải trỏ tới allocation đã tạo cho O-C; không được tùy ý giảm reservation của đơn khác.
- O-C đã được xuất hết, nên retry xuất phải replay hoặc bị từ chối, không tạo thêm version giảm tồn.
- Version 23 chỉ nhả phần còn giữ của O-B; gọi lại bằng key khác cũng không được nhả thêm.
- Version 24 hợp lệ về lượng vì sau điều chỉnh vẫn còn đủ 2 đơn vị bảo đảm cho O-A. Nó vẫn cần đúng quyền, căn cứ và phê duyệt theo chính sách.

Nếu đề nghị điều chỉnh giảm 7 ở trạng thái trước version 24, kết quả dự kiến là `H = 1`, `R = 2`, vi phạm bất biến. Hệ thống cần từ chối hoặc đi qua quy trình giải quyết thiếu hàng và phân bổ lại đã được định nghĩa. Không âm thầm xóa reservation để làm cho phép điều chỉnh vượt qua kiểm tra.

## 7. Chuyển kho: audit phải theo đúng mô hình vận chuyển

### 7.1. Chuyển tức thời trong cùng hệ thống dữ liệu

Nếu nghiệp vụ thật sự coi chuyển kho là một thao tác tức thời, chuyển `q` từ A sang B tạo các entry liên quan:

```text
Kho A: delta_on_hand = -q
Kho B: delta_on_hand = +q
Tổng delta_on_hand của operation = 0
```

Hai entry, hai số dư và trạng thái chứng từ chuyển phải commit cùng nhau. Mỗi kho có version riêng; không yêu cầu version của hai kho bằng nhau. Khóa các đối tượng theo thứ tự ổn định để giảm deadlock.

Kho nguồn cũng phải thỏa điều kiện phân bổ. Không lấy hàng đã được giữ cho đơn khác để hoàn tất chuyển kho, trừ khi có quy trình chuyển allocation hợp lệ đi kèm.

### 7.2. Chuyển có thời gian vận chuyển

Nếu hàng rời A hôm nay và đến B ngày mai, cần một ngăn `in_transit` hoặc đối tượng tương đương:

```text
Lúc gửi:  A giảm q, in_transit tăng q
Lúc nhận: in_transit giảm q, B tăng q

H_A + H_B + in_transit được bảo toàn
nếu không có nghiệp vụ mất hàng hoặc điều chỉnh riêng
```

Không áp điều kiện tổng delta của riêng `H_A + H_B` bằng 0 cho từng bước gửi hoặc nhận: hai bước tác động khác nhau lên hàng đang vận chuyển.

Chứng từ có thể đi qua các trạng thái như:

```text
DRAFT -> APPROVED -> DISPATCHED -> RECEIVED
                         |
                         +-> EXCEPTION_RESOLUTION
```

Việc nhận từng phần cần theo dõi lượng đã gửi, đã nhận và còn đang vận chuyển. Retry sự kiện nhận không được cộng tồn kho lần nữa. Hủy một chứng từ đã gửi phải đi qua nghiệp vụ hoàn hoặc xử lý ngoại lệ; chỉ đổi trạng thái thành `CANCELLED` không đưa hàng quay lại kho nguồn.

Nếu hai kho thuộc các dịch vụ/database khác nhau, không giả định có transaction cục bộ bao phủ cả hai. Cần mô hình trạng thái, thông điệp bền vững, chống trùng và bước bù trừ phù hợp với từng chặng. Audit phải cho thấy trạng thái đang chờ để người vận hành phân biệt độ trễ với thất thoát.

## 8. Quyền, phê duyệt và sửa sai

### 8.1. Kiểm tra hành động trên đúng đối tượng

Quyền chung `inventory:write` thường chưa đủ. Một quyết định cần xét ít nhất người thao tác có được thực hiện **hành động này**, trên **kho này**, trong **tenant này**, đối với **chứng từ này** và ở **trạng thái này** hay không.

| Vai trò minh họa | Có thể được phép | Điều kiện hoặc giới hạn |
| --- | --- | --- |
| Nhân viên kho | Nhập/xuất theo chứng từ | Chỉ kho được phân công, đúng lượng còn lại |
| Dịch vụ đơn hàng | Giữ/nhả hàng | Đúng tenant, đúng đơn và reservation |
| Người yêu cầu điều chỉnh | Tạo đề nghị | Có lý do và bằng chứng kiểm kê |
| Người phê duyệt | Duyệt điều chỉnh theo hạn mức | Đúng phạm vi và điều kiện tách biệt trách nhiệm |
| Kiểm toán viên | Xem, đối soát, xuất báo cáo | Dữ liệu trong phạm vi được cấp, không sửa movement |

Với điều chỉnh vượt ngưỡng, chính sách có thể yêu cầu người duyệt khác người đề nghị. Approval phải gắn với nội dung cụ thể: kho, SKU, lượng, chiều thay đổi và lý do. Sửa số lượng sau khi duyệt phải làm approval cũ mất hiệu lực hoặc cần phê duyệt lại theo quy định.

### 8.2. Không sửa lịch sử để che một sai sót

Một movement đã commit nên được giữ bất biến đối với các luồng ứng dụng thông thường. Nếu nhập nhầm, tạo operation sửa sai hoặc bù trừ có liên kết tới bản ghi gốc, lý do và chủ thể chịu trách nhiệm.

Đảo dấu delta chỉ đúng khi thỏa các điều kiện nghiệp vụ hiện tại. Ví dụ, đã nhập 10 rồi xuất 8 thì không thể tự động trừ 10 để hủy phiếu nhập nếu việc đó làm tồn kho âm hoặc ảnh hưởng hàng đã phân bổ.

Với bù trừ toàn phần một lần, có thể ràng buộc duy nhất quan hệ đảo giao dịch. Với bù trừ từng phần, phải kiểm tra tổng lượng đã bù không vượt phần được phép của entry gốc trong cùng cơ chế cạnh tranh. Một `reversal_of` có giá trị không tự chứng minh rằng lượng bù là hợp lệ.

Bản ghi giải thích cần đủ để người điều tra hiểu thay đổi nào sửa cho thay đổi nào. Không sửa `actor`, `reason` hoặc `quantity` của entry cũ để làm lịch sử khớp với kết quả mong muốn.

## 9. Bảo vệ tính toàn vẹn và khả năng cung cấp audit

### 9.1. Append-only là chính sách cần được thực thi

Phân quyền database nên ngăn tài khoản ứng dụng thông thường sửa hoặc xóa movement đã ghi. Có thể dùng stored procedure, trigger, quyền theo bảng và quy trình bảo trì được kiểm soát tùy kiến trúc. Nếu cần bảo đảm mọi thay đổi số dư đều đi qua đường ghi chuẩn, cũng phải giới hạn quyền cập nhật trực tiếp bảng số dư.

Chỉ cấm sửa bảng movement vẫn chưa ngăn được một đường ghi khác sửa số dư mà không tạo entry. Đối soát và kiểm soát quyền ghi phải hỗ trợ lẫn nhau.

Append-only ở cấp ứng dụng không bảo vệ tuyệt đối trước tài khoản quản trị database hoặc hạ tầng bị chiếm quyền. Nếu yêu cầu điều tra cần mức tin cậy cao hơn, có thể đưa bản sao audit sang nơi lưu trữ tách quyền quản trị, có chính sách lưu giữ và chống sửa phù hợp.

Chuỗi hash giúp phát hiện một số thay đổi nếu có checkpoint hoặc điểm neo tin cậy bên ngoài. Nếu kẻ sửa dữ liệu có thể tính lại cả chuỗi và thay checkpoint, chuỗi hash nội bộ không tự chứng minh được tính toàn vẹn. Nó cũng không chứng minh rằng mọi biến động hàng vật lý đã được nhập vào hệ thống.

### 9.2. Audit không được phụ thuộc vào thành công của log hoặc message broker

Một thiết kế dễ tạo khoảng trống:

```text
1. Commit số dư vào database.
2. Gửi message chứa movement.
3. Consumer ghi sổ audit.
```

Nếu tiến trình chết giữa bước 1 và 2, số dư đã đổi nhưng không có dấu vết bền vững để phục hồi việc gửi. Nếu consumer ghi trùng, báo cáo audit lại có thể đếm hai lần.

Với thiết kế của bài học, movement là dữ liệu bền vững được ghi cùng transaction với số dư. Nếu cần xuất bản sự kiện, ghi thêm **transactional outbox** trong cùng transaction, sau đó relay gửi ra ngoài.

Outbox không tự làm cho delivery chỉ xảy ra một lần. Consumer cần khóa chống trùng theo định danh sự kiện và cập nhật projection cùng dấu đã xử lý trong một transaction cục bộ. Không dùng `correlation_id` làm khóa chống trùng vì một luồng có thể tạo nhiều sự kiện hợp lệ.

Báo cáo trên projection hoặc replica có thể chậm hơn nguồn chính. Trước khi kết luận thiếu movement, cần xác định ranh giới dữ liệu và độ trễ của nơi đọc.

### 9.3. Giữ đủ thông tin mà không mở rộng lộ lọt dữ liệu

Không ghi token, thông tin xác thực, bí mật hoặc toàn bộ request body vào movement. Dùng định danh tham chiếu và các trường nghiệp vụ cần thiết. Chuẩn hóa `reason_code`, giới hạn độ dài ghi chú và xử lý ghi chú như dữ liệu khi hiển thị.

API tra cứu audit phải kiểm tra tenant, kho và phạm vi quyền. Việc đoán được `operation_id` hoặc `movement_id` không được mở quyền đọc lịch sử của đơn vị khác. Endpoint export cũng phải áp dụng các điều kiện đó.

Chính sách lưu giữ, backup và phục hồi phải bảo toàn liên kết giữa sổ, checkpoint và số dư. Nếu đã lưu trữ lịch sử cũ sang kho khác, truy vấn đối soát phải dùng checkpoint đã xác minh; không cộng phần lịch sử còn lại rồi so với toàn bộ số dư.

## 10. Đối soát: từ phát hiện lệch số đến điều tra nguyên nhân

### 10.1. Truy vấn đối chiếu số dư với toàn bộ sổ

SQL dưới đây minh họa theo cú pháp PostgreSQL, với các giả định:

- `inventory_movement` chứa đầy đủ lịch sử từ trạng thái 0, gồm cả entry mở đầu nếu có hàng ban đầu.
- Mỗi khóa tồn kho có đúng một entry cho mỗi version, version bắt đầu từ 1 và không bị bỏ qua khi commit.
- `inventory_balance.version` bắt đầu từ 0 và tăng cùng entry tương ứng.
- Các cột định danh và số dư liên quan không nhận `NULL`; một hàng số dư mới ở version 0 được phép chưa có entry.

```sql
WITH ledger AS (
    SELECT tenant_id,
           warehouse_id,
           sku_id,
           SUM(delta_on_hand) AS total_on_hand,
           SUM(delta_reserved) AS total_reserved,
           MAX(balance_version) AS last_version,
           COUNT(*) AS entry_count
    FROM inventory_movement
    GROUP BY tenant_id, warehouse_id, sku_id
)
SELECT COALESCE(b.tenant_id, l.tenant_id) AS tenant_id,
       COALESCE(b.warehouse_id, l.warehouse_id) AS warehouse_id,
       COALESCE(b.sku_id, l.sku_id) AS sku_id,
       b.on_hand AS stored_on_hand,
       COALESCE(l.total_on_hand, 0) AS ledger_on_hand,
       b.reserved AS stored_reserved,
       COALESCE(l.total_reserved, 0) AS ledger_reserved,
       b.version AS stored_version,
       COALESCE(l.last_version, 0) AS ledger_version
FROM inventory_balance b
FULL OUTER JOIN ledger l
  ON b.tenant_id = l.tenant_id
 AND b.warehouse_id = l.warehouse_id
 AND b.sku_id = l.sku_id
WHERE b.tenant_id IS NULL
   OR b.on_hand <> COALESCE(l.total_on_hand, 0)
   OR b.reserved <> COALESCE(l.total_reserved, 0)
   OR b.version <> COALESCE(l.last_version, 0)
   OR COALESCE(l.entry_count, 0) <> COALESCE(l.last_version, 0);
```

`FULL OUTER JOIN` còn giúp thấy một khóa có movement nhưng thiếu hàng số dư. Điều kiện đếm entry chỉ có ý nghĩa cùng giả định version liên tục và ràng buộc duy nhất đã nêu. Nếu có thêm lô hoặc trạng thái hàng trong khóa, phải thêm đầy đủ vào `GROUP BY` và điều kiện nối.

Đọc số dư và sổ tại cùng một snapshot nhất quán. Nếu đối soát nhiều truy vấn hoặc nhiều phân vùng, dùng cơ chế snapshot hoặc checkpoint thích hợp; ghép các lần đọc ở các thời điểm khác nhau có thể tạo sai lệch giả.

Truy vấn này phát hiện một nhóm bất nhất nội bộ. Nó không xác nhận hàng vật lý có thật, không kiểm tra được mọi quyền và cũng không phát hiện việc một bên sửa cả số dư lẫn sổ theo cùng một cách.

### 10.2. Các lớp đối soát bổ sung

| Lớp kiểm tra | Ví dụ sai lệch |
| --- | --- |
| Chuỗi trạng thái | `before` không bằng `after` của entry trước |
| Số dư và reservation | `reserved = 8` nhưng các reservation còn hiệu lực cộng lại là 6 |
| Chứng từ và hiệu ứng | Xuất kho không có phiếu xuất hợp lệ hoặc vượt lượng được duyệt |
| Chuyển kho | Đã nhận nhiều hơn lượng đã gửi, hoặc tồn in-transit bị âm |
| Phê duyệt | Điều chỉnh lớn thiếu approval hoặc dùng approval cho số lượng khác |
| Kiểm kê vật lý | Số hệ thống khớp ledger nhưng thực tế thiếu hàng |

Đối soát kiểm kê cần mốc chốt và cách xử lý những nghiệp vụ đang diễn ra. Ví dụ, hàng vừa xuất khỏi kệ nhưng chưa hoàn thành bước ghi nhận có thể tạo chênh lệch theo thời điểm; cần điều tra quy trình, không tự động kết luận gian lận.

Khi có sai lệch, giữ lại bằng chứng và xác định phạm vi ảnh hưởng. Tùy mức độ, có thể chặn nghiệp vụ liên quan đến đúng kho/SKU đang lỗi, mở quy trình sửa sai có phê duyệt rồi đối soát lại. Không tự chèn một adjustment để làm báo cáo hết đỏ trước khi xác định căn cứ.

### 10.3. Tín hiệu cảnh báo có giá trị

Một số tín hiệu nên theo dõi theo tenant, kho và loại nghiệp vụ:

- Chênh lệch giữa số dư và ledger hoặc giữa `reserved` và reservation.
- Entry không có căn cứ hợp lệ, version bất thường hoặc hành vi sửa/xóa bị từ chối.
- Điều chỉnh lặp lại ngay dưới ngưỡng phê duyệt; tần suất cao hơn mức bình thường của chủ thể.
- Một actor liên tục đổi key để yêu cầu cùng hiệu ứng, hoặc thường xuyên gặp xung đột fingerprint.
- Chuyển kho treo quá thời gian dự kiến, outbox bị dồn hoặc projection chậm vượt ngưỡng vận hành.

Không xem mọi retry là tấn công: mạng không ổn định cũng tạo retry hợp lệ. Cảnh báo cần đi kèm căn cứ, trạng thái commit và ngữ cảnh nghiệp vụ để người vận hành đánh giá.

## 11. Kiểm thử các tình huống lạm dụng logic

Các tình huống sau dùng cho kiểm thử trong môi trường được phép. Mỗi ca cần xác minh cả response, trạng thái nghiệp vụ, số dư và sổ biến động sau xử lý.

| Tình huống | Kết quả cần đạt |
| --- | --- |
| Giữ hàng với số lượng 0, âm hoặc vượt giới hạn kiểu dữ liệu | Từ chối trước khi thay đổi; không có movement thành công |
| Hai request đồng thời cùng giữ 4 khi chỉ còn 5 | Chỉ lượng hợp lệ được giữ; tổng `reserved` không vượt `on_hand` |
| Cùng key, cùng payload, gửi đồng thời hoặc retry sau timeout | Chỉ một hiệu ứng và một nhóm entry được commit; replay kết quả cũ |
| Cùng key nhưng đổi số lượng hoặc đổi kho | Báo xung đột; không áp dụng payload mới |
| Đổi key để xuất lại cùng phần hàng của một chứng từ | Không xuất thêm; kiểm tra effect và lượng còn được phép vẫn có hiệu lực |
| Đổi tenant hoặc kho trong request | Không đọc hoặc thay đổi đối tượng ngoài quyền; không rò rỉ kết quả replay |
| Nhả reservation đã được xuất hết | Không làm `reserved` âm và không tạo thêm hàng có thể bán |
| Nhận hàng trước khi chứng từ chuyển ở trạng thái được phép | Từ chối chuyển trạng thái và không tăng số dư kho đích |
| Sửa số lượng điều chỉnh sau khi đã được duyệt | Approval cũ không cho phép áp dụng nội dung đã thay đổi |
| Người đề nghị tự duyệt khi chính sách cấm | Từ chối; không chỉ dựa vào field `approved` do client gửi |
| Lỗi khi insert movement sau khi đã chạy lệnh update số dư | Toàn bộ transaction rollback, không có số dư thay đổi đơn lẻ |
| Commit thành công rồi ngắt kết nối trước khi trả response | Retry trả kết quả đã lưu, không tạo biến động lần hai |
| Bù trừ cùng entry hai lần hoặc bù từng phần vượt lượng gốc | Chặn phần vượt; giữ nguyên lịch sử lần đầu |
| Cùng lúc hủy đơn và giữ hoặc xuất hàng cho đơn đó | Kết quả theo thứ tự hợp lệ của state machine; không có cam kết trái trạng thái |
| Sự kiện outbox được giao lặp | Projection chỉ áp dụng hiệu ứng một lần nhờ cơ chế chống trùng của consumer |
| Tài khoản ứng dụng thử sửa/xóa movement đã commit | Bị chặn theo quyền; có dấu vết vận hành để điều tra |

Các ca cạnh tranh cần cho request chạm cùng điểm quyết định, thay vì chỉ gửi tuần tự rồi gọi đó là kiểm thử đồng thời. Khi chèn lỗi, cần có điểm lỗi trước commit và điểm mất response sau commit: hai trường hợp này có kỳ vọng idempotency khác nhau.

Ngoài các ca tấn công, cần kiểm tra đường nghiệp vụ hợp lệ như xuất từng phần, nhận từng phần và bù trừ từng phần. Một cơ chế chống trùng quá rộng có thể chặn thao tác hợp lệ, khiến người vận hành phải tìm đường vòng ngoài hệ thống.

## 12. Bài tập áp dụng

### Bài tập 1: Giải thích chênh lệch

Tại checkpoint đã xác minh, SKU-X có `H = 20`, `R = 4`. Sau đó sổ ghi:

```text
RECEIPT:        delta H = +5, delta R =  0
RESERVE:        delta H =  0, delta R = +3
ISSUE_RESERVED: delta H = -2, delta R = -2
ADJUST_DOWN:    delta H = -1, delta R =  0
```

Bảng số dư hiện ghi `H = 24`, `R = 5`.

Hãy tính trạng thái kỳ vọng, xác định phần sai lệch và nêu dữ liệu cần thu thập trước khi sửa.

**Gợi ý giải:** Theo sổ, `H = 20 + 5 - 2 - 1 = 22`, `R = 4 + 3 - 2 = 5`, nên `A = 17`. Bảng số dư thừa 2 ở `on_hand` so với sổ. Chỉ từ kết quả này chưa thể khẳng định nguyên nhân là thao tác xuất: có thể là cập nhật sai, sửa trực tiếp số dư, checkpoint sai hoặc dữ liệu audit thiếu/sai.

Cần đối chiếu version, chuỗi before/after, chứng từ, reservation và các đường ghi liên quan tại cùng mốc dữ liệu. Nếu hệ thống thật sự ghi số dư và entry đúng trong cùng transaction, sai lệch như vậy là dấu hiệu cần điều tra cả logic ghi và khả năng ghi ngoài luồng chuẩn.

### Bài tập 2: Nhận diện audit chưa đủ an toàn

Một service thực hiện ba bước: cập nhật số dư, ghi log JSON ra stdout, rồi gửi message để hệ thống báo cáo lưu movement. Client tự gửi `actor_id`, `approved` và `idempotency_key`.

Hãy đề xuất cách sửa ranh giới transaction, nguồn dữ liệu tin cậy và chống trùng.

**Gợi ý giải:** Ghi movement cùng số dư và trạng thái nghiệp vụ vào database trong một transaction; ghi outbox nếu cần phát sự kiện. Lấy actor từ danh tính đã xác thực, xác minh approval ở server và ràng buộc approval với nội dung điều chỉnh. Dùng idempotency kèm fingerprint cho retry, đồng thời ràng buộc hiệu ứng và lượng còn được phép trên chứng từ. Stdout vẫn phục vụ chẩn đoán, còn báo cáo bên ngoài là nơi đọc dữ liệu được chuyển tiếp có kiểm soát trùng và độ trễ.

Một thiết kế inventory movement audit có giá trị khi cho phép lần ngược từ số dư đến nghiệp vụ hợp lệ, và từ nghiệp vụ đến toàn bộ tác động tồn kho của nó. Khi dữ liệu không khớp, hệ thống cần giữ được bằng chứng để điều tra và sửa sai bằng một nghiệp vụ có căn cứ.
