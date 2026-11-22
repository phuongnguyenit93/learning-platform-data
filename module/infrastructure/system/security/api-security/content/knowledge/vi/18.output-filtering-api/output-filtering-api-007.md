# Kiểm tra output khi object có trạng thái đặc biệt

Một object có thể được truy cập hợp lệ nhưng không phải mọi thuộc tính của nó đều được phép xuất hiện trong response ở mọi trạng thái. Ví dụ, khách hàng có quyền xem đơn hàng của mình, nhưng khi đơn đang bị điều tra gian lận, API không nên trả ghi chú nội bộ của đội risk; khi tài liệu đang chờ phê duyệt, người gửi có thể xem nội dung nhưng không được thấy nhận xét riêng của người duyệt; khi tài khoản bị khóa, một số thông tin hỗ trợ có thể được hiển thị nhưng token khôi phục hoặc dữ liệu xác minh phải được giữ kín.

Vì vậy, lọc output cần xét cả danh tính người xem, quyền trên object, quyền trên property và trạng thái hiện tại của object. Đây là **state-aware output filtering**: quyết định response projection theo trạng thái và ngữ cảnh nghiệp vụ, thay vì serialize toàn bộ entity hoặc dùng một DTO cố định cho mọi trường hợp.

Trong API Security, việc object có trạng thái đặc biệt không tự động có nghĩa mọi truy cập đều bị cấm. Có thể vẫn cho phép đọc một phần dữ liệu, trả trạng thái tổng quát hoặc chỉ cho một nhóm chuyên trách xem một số trường. Điều quan trọng là chính sách phải rõ ràng, được thực thi ở server và nhất quán trên detail, list, search, export, cache và các API khác cùng truy cập object.

Sau bài học, người đọc có thể:

- Nhận diện những trạng thái object làm thay đổi quyền hiển thị dữ liệu.
- Phân biệt quyền truy cập object với quyền đọc từng property theo trạng thái.
- Thiết kế response DTO/projection phù hợp với viewer và trạng thái hiện tại.
- Tránh rò rỉ dữ liệu qua list, search, export, cache, lỗi và side channel.
- Xử lý trạng thái thay đổi đồng thời để response không dùng policy cũ.
- Viết test xác minh cả field được phép, field bị ẩn và hành vi khi object chuyển trạng thái.

## 1. Vì sao trạng thái object ảnh hưởng đến output?

Trạng thái mô tả vị trí hiện tại của object trong vòng đời nghiệp vụ. Cùng một object có thể hiển thị các thuộc tính khác nhau tùy trạng thái và người xem.

Ví dụ các trạng thái thường gặp:

| Trạng thái | Ví dụ | Rủi ro khi trả output không phù hợp |
|---|---|---|
| `DRAFT` | Hồ sơ hoặc báo cáo chưa gửi | Lộ nội dung chưa được công bố hoặc bản nháp nội bộ |
| `PENDING_REVIEW` | Đơn đang chờ phê duyệt | Lộ nhận xét nội bộ, danh tính người duyệt hoặc dữ liệu chưa xác minh |
| `SUSPENDED` / `LOCKED` | Tài khoản bị tạm khóa | Lộ tín hiệu risk, thông tin điều tra hoặc chi tiết cơ chế bảo vệ |
| `UNDER_INVESTIGATION` | Giao dịch đang được điều tra | Lộ cờ gian lận, bằng chứng hoặc quy tắc phát hiện |
| `ARCHIVED` | Hồ sơ đã lưu trữ | Trả dữ liệu quá thời hạn hoặc cho người không còn quyền truy cập |
| `DELETED` / `SOFT_DELETED` | Object đã xóa logic | Làm lộ dữ liệu mà policy yêu cầu ẩn hoặc xóa khỏi API thông thường |
| `QUARANTINED` | Tệp bị cách ly | Cho phép tải nội dung có mã độc hoặc nội dung chưa quét |
| `LEGAL_HOLD` | Dữ liệu đang được giữ theo yêu cầu pháp lý | Tiết lộ thông tin pháp lý hoặc cho phép thao tác xóa trái phép |
| `EXPIRED` | Token, phiên hoặc ưu đãi hết hạn | Tiếp tục trả dữ liệu/quyền lợi đã hết hiệu lực |

Không phải mọi trạng thái đặc biệt đều yêu cầu che giấu toàn bộ object. Ví dụ, khách hàng có thể cần biết đơn hàng đang bị tạm giữ và mã hỗ trợ, nhưng không được xem ghi chú điều tra nội bộ. Với tệp bị cách ly, API có thể trả metadata an toàn như tên hiển thị và trạng thái `UNAVAILABLE`, nhưng không cấp URL tải xuống.

## 2. Bốn lớp cần kiểm tra trước khi tạo response

Một response an toàn cần đánh giá ít nhất bốn yếu tố:

1. **Subject/viewer:** ai đang xem, thuộc tenant nào, có role/scope hoặc quan hệ nào?
2. **Object authorization:** người xem có quyền truy cập object này không? Object có thuộc owner, tenant, nhóm hoặc phạm vi được giao không?
3. **Property authorization:** người xem được đọc những thuộc tính nào? Quyền đọc có khác nhau giữa dữ liệu công khai, dữ liệu cá nhân và dữ liệu nội bộ không?
4. **Object state/context:** trạng thái hiện tại có làm thay đổi tập thuộc tính được phép trả, điều kiện hiển thị hoặc khả năng truy cập không?

Có thể mô tả quyết định như sau:

```text
response = project(object, viewer, action, context)

1. Xác thực viewer.
2. Kiểm tra viewer có quyền đọc object.
3. Đọc trạng thái và các thuộc tính cần cho policy.
4. Xác định field mask theo viewer + object + state.
5. Tạo response chỉ từ field được phép.
6. Kiểm tra cache/audit và trả kết quả.
```

Trạng thái object không thay thế quyền người xem. Một tài liệu ở trạng thái `PUBLISHED` vẫn có thể chỉ được xem bởi một nhóm người dùng; một đơn ở trạng thái `PENDING_REVIEW` có thể được người gửi xem nhưng không được người ngoài tenant xem.

| Viewer | Object/state | Output có thể được phép |
|---|---|---|
| Chủ đơn hàng | `PROCESSING` | Thông tin đơn, sản phẩm, tổng tiền và tiến độ giao hàng |
| Chủ đơn hàng | `UNDER_INVESTIGATION` | Trạng thái tổng quát và hướng dẫn liên hệ; ẩn risk score/ghi chú điều tra |
| Nhân viên risk được phân công | `UNDER_INVESTIGATION` | Bằng chứng, cờ risk và ghi chú theo quyền chuyên trách |
| Người gửi tài liệu | `PENDING_REVIEW` | Nội dung đã gửi và trạng thái chờ; ẩn nhận xét riêng của reviewer |
| Reviewer được phân công | `PENDING_REVIEW` | Nội dung, lịch sử review và nhận xét trong phạm vi được cấp |
| Người dùng bất kỳ | `QUARANTINED` file không thuộc phạm vi | Không tiết lộ metadata riêng tư hoặc nội dung file |

## 3. Xác định field mask theo trạng thái

Field mask là tập thuộc tính được phép xuất hiện trong một response cụ thể. Một cách thực tế là phân loại property trước khi viết mapper:

- **Public:** có thể hiển thị cho mọi người có quyền truy cập endpoint, ví dụ mã đơn rút gọn hoặc trạng thái công khai.
- **Owner-visible:** chỉ chủ thể hoặc người được chia sẻ object mới xem, ví dụ địa chỉ giao hàng hoặc ghi chú cá nhân.
- **Role-restricted:** chỉ role/nhóm chuyên trách được xem, ví dụ nhận xét kiểm duyệt hoặc thông tin xử lý nội bộ.
- **State-restricted:** chỉ hiển thị ở một số trạng thái, ví dụ `publishedAt` khi đã công bố hoặc `reviewComment` sau khi review hoàn tất và theo policy.
- **Never-return:** không được trả trực tiếp qua API thông thường, ví dụ password hash, secret, reset token hoặc khóa mã hóa.

Ví dụ object đơn hàng:

| Property | `PROCESSING` - chủ đơn | `UNDER_INVESTIGATION` - chủ đơn | `UNDER_INVESTIGATION` - risk analyst |
|---|---|---|---|
| `orderNumber` | Có | Có | Có |
| `items` | Có | Có theo policy | Có |
| `total` | Có | Có thể có | Có |
| `deliveryStatus` | Có | Có thể chỉ hiển thị trạng thái tổng quát | Có |
| `riskScore` | Không | Không | Có nếu được cấp quyền |
| `investigationNotes` | Không | Không | Có nếu được phân công |
| `internalRuleId` | Không | Không | Chỉ khi thật sự cần cho tác vụ chuyên trách |
| `paymentToken` | Không | Không | Không trả trực tiếp |

Không nên dùng một boolean chung như `isAdmin` để quyết định mọi field. Có thể cần quyền chuyên biệt như `risk:case:read`, quan hệ assignment và tenant scope. Quyền xem một trường cũng có thể phụ thuộc trạng thái xử lý và mục đích sử dụng.

## 4. Tạo response DTO thay vì serialize entity

Serialize trực tiếp entity là cách dễ làm lộ field khi model phát triển. Entity có thể chứa quan hệ lazy, cờ nội bộ, ghi chú, token hoặc field mới được thêm cho một luồng quản trị. Nếu response tự động phản ánh entity, thay đổi ở persistence model có thể vô tình thay đổi public API.

Hãy dùng DTO/projection riêng cho từng mục đích response. Ví dụ:

```java
public record OrderCustomerResponse(
        UUID id,
        String orderNumber,
        OrderStatusView status,
        BigDecimal total,
        List<OrderItemResponse> items,
        String supportMessage) {
}

public record OrderRiskResponse(
        UUID id,
        String orderNumber,
        OrderStatusView status,
        BigDecimal total,
        Integer riskScore,
        List<String> investigationNotes) {
}
```

Hai DTO có thể dùng chung một số field nhưng có mục đích và quyền đọc khác nhau. `OrderRiskResponse` chỉ được tạo sau khi kiểm tra quyền của risk analyst trên đúng case; không trả DTO này cho khách hàng rồi trông chờ frontend ẩn các field.

Service có thể tạo projection dựa trên policy:

```java
public Object getOrderResponse(UUID orderId, ApiPrincipal viewer) {
    Order order = orderRepository
            .findByIdAndTenantId(orderId, viewer.tenantId())
            .orElseThrow(OrderNotFoundException::new);

    authorizationService.requireCanReadOrder(viewer, order);

    if (order.getStatus() == OrderStatus.UNDER_INVESTIGATION
            && authorizationService.canReadRiskCase(viewer, order)) {
        return orderMapper.toRiskResponse(order);
    }

    return orderMapper.toCustomerResponse(order, viewer);
}
```

Đây là ví dụ rút gọn. Trong ứng dụng thực tế nên dùng kiểu response rõ ràng, chẳng hạn một DTO chung với field mask hoặc một sealed response hierarchy, thay vì trả `Object` nếu client cần contract ổn định. Điểm cốt lõi là kiểm tra quyền trên object trước, sau đó mới chọn projection; điều kiện trạng thái không được cấp quyền thay cho authorization.

### 4.1. DTO chung với field mask

Khi API cần một schema response ổn định, có thể dùng một DTO chung và chỉ điền field được phép:

```java
public record OrderResponse(
        UUID id,
        String orderNumber,
        OrderStatusView status,
        BigDecimal total,
        String supportMessage,
        Integer riskScore,
        List<String> investigationNotes) {
}
```

Mapper nhận policy result đã được tính:

```java
OrderResponse toResponse(Order order, OrderViewPolicy policy) {
    return new OrderResponse(
            order.getId(),
            order.getOrderNumber(),
            policy.publicStatus(order),
            policy.canReadTotal() ? order.getTotal() : null,
            policy.supportMessage(order),
            policy.canReadRiskScore() ? order.getRiskScore() : null,
            policy.canReadInvestigationNotes()
                    ? List.copyOf(order.getInvestigationNotes())
                    : List.of());
}
```

Nếu dùng `null` để biểu thị field bị ẩn, contract cần phân biệt rõ giữa “không được phép xem”, “giá trị thật sự null” và “field không áp dụng”. Một số API nên bỏ hẳn field qua `JsonView`/serializer hoặc dùng DTO riêng; tuy nhiên việc điều khiển serializer phải được kiểm thử để không vô tình lộ field qua một đường response khác.

### 4.2. Không để mapper quyết định quyền bằng role đơn giản

Mapper nên nhận policy result hoặc field mask được tạo từ authorization layer. Tránh viết logic rải rác như `if (user.isAdmin()) includeEverything`. Admin của một tenant có thể không được xem object tenant khác; một nhân viên risk có thể chỉ xem case được phân công; một số secret không nên xuất hiện ngay cả với admin.

## 5. Trạng thái đặc biệt và cách phản hồi an toàn

### 5.1. Draft và pending review

Với object chưa công bố, người tạo có thể xem bản nháp của mình, reviewer được phân công có thể xem nội dung để đánh giá, còn người dùng khác không nên tìm thấy object qua list hoặc search.

Khi object ở `PENDING_REVIEW`, response cho người gửi có thể chứa `status`, thời điểm gửi và hướng dẫn sửa nếu bị trả lại. Nhận xét riêng của reviewer, điểm đánh giá nội bộ hoặc ghi chú moderation cần field policy riêng. Nếu nghiệp vụ cho phép công khai nhận xét sau khi hoàn tất, chỉ trả khi trạng thái và quyền phù hợp.

### 5.2. Locked, suspended và under investigation

Với tài khoản bị khóa hoặc giao dịch đang điều tra, API có thể trả trạng thái tổng quát để người dùng biết cần liên hệ hỗ trợ. Không nên trả nguyên nhân nội bộ như risk score, rule ID, tín hiệu thiết bị hoặc bằng chứng có thể giúp attacker điều chỉnh hành vi để né phát hiện.

Thông báo cần đủ hữu ích nhưng không tiết lộ cơ chế phòng vệ. Ví dụ `ACCOUNT_RESTRICTED` và mã hỗ trợ có thể phù hợp hơn việc trả `blocked because device fingerprint matched rule R-17`.

### 5.3. Archived và soft-deleted

Object đã lưu trữ có thể chỉ được truy cập qua endpoint archive hoặc bởi nhóm có quyền retention. Object soft-deleted cần được loại khỏi list/search mặc định; endpoint detail phải áp dụng chính sách ẩn/hiển thị phù hợp. Không để export, autocomplete hoặc count vô tình trả dữ liệu đã xóa.

Nếu hệ thống cho phép khôi phục, response có thể chỉ hiển thị metadata cần thiết cho người có quyền restore. Không trả toàn bộ nội dung đã xóa cho user thông thường chỉ vì bản ghi vẫn còn trong database.

### 5.4. Quarantined file hoặc nội dung chưa quét

Với file ở trạng thái `QUARANTINED`, có thể trả metadata an toàn như `status: UNAVAILABLE` và hướng dẫn liên hệ hỗ trợ. Không trả download URL, signed URL, nội dung preview hoặc thumbnail có thể chứa nội dung chưa được kiểm tra. Endpoint tải file cần kiểm tra lại trạng thái ngay trước khi stream.

Khi scan hoàn tất và file chuyển sang `AVAILABLE`, việc tải vẫn cần xác thực và object authorization. Trạng thái sạch không có nghĩa mọi người đều được quyền đọc file.

### 5.5. Legal hold và trạng thái retention

Object ở `LEGAL_HOLD` có thể bị cấm xóa hoặc sửa, nhưng một số người vẫn được xem theo nhiệm vụ. Output không nên tiết lộ chi tiết pháp lý hoặc danh tính người yêu cầu giữ dữ liệu nếu không có quyền. Endpoint export/restore/delete phải tuân thủ cùng policy và audit đầy đủ.

## 6. Trả trạng thái hay che giấu object?

Đôi khi API cần quyết định người dùng có được biết object tồn tại hay không. Ví dụ, user A gọi ID của một hồ sơ thuộc user B. Nếu trả `403`, response xác nhận object có tồn tại. Nếu chính sách yêu cầu không tiết lộ, có thể trả `404` như trường hợp không tìm thấy.

Với trạng thái đặc biệt, cũng cần quyết định mức độ tiết lộ:

- **Hiển thị trạng thái tổng quát:** phù hợp khi người dùng là chủ thể có quyền biết object đang tạm giữ hoặc chờ xử lý.
- **Ẩn sự tồn tại:** phù hợp khi việc xác nhận object tồn tại cũng là dữ liệu nhạy cảm.
- **Hiển thị trạng thái chi tiết theo role:** dành cho nhân viên chuyên trách hoặc người được phân công.

Hãy áp dụng nhất quán cho detail, list, search, count, export, webhook và lỗi. Nếu detail trả `404` nhưng search trả tên object hoặc count tăng lên, chính sách che giấu đã bị phá vỡ.

## 7. Tránh rò rỉ qua list, search, export và API phụ

Output filtering cần được áp dụng ở mọi cách truy cập cùng dữ liệu:

- **Detail:** lọc field theo viewer và state.
- **List:** chỉ đưa object vào tập kết quả nếu viewer được phép biết sự tồn tại; áp dụng field mask cho từng item.
- **Search/filter/sort:** không cho suy luận giá trị field ẩn qua điều kiện lọc, thứ tự hoặc facet nếu policy không cho phép.
- **Count/aggregation:** không tính object bị ẩn vào tổng số hiển thị cho viewer.
- **Export/report:** dùng cùng policy hoặc một quyền export riêng; không xuất entity đầy đủ.
- **Nested resource:** kiểm tra quyền trên cả object cha và con, trạng thái của cả hai nếu ảnh hưởng đến output.
- **GraphQL:** mỗi resolver/field nhạy cảm phải áp dụng policy; DataLoader không được dùng cache chung làm lộ field giữa viewer.
- **Webhook/event:** chỉ phát các field được phép cho subscriber; trạng thái nội bộ không mặc nhiên được gửi ra đối tác.

Ví dụ, một tài liệu `DRAFT` không được trả trong danh sách public. Việc lọc sau khi phân trang có thể làm lộ số lượng bản ghi hoặc tạo trang rỗng bất thường; tốt hơn là đưa điều kiện quyền và trạng thái vào query trước khi phân trang.

## 8. Cache và response theo trạng thái

Cache có thể gây rò rỉ nếu response được tạo cho viewer hoặc trạng thái này lại được trả cho viewer khác hoặc trạng thái mới.

Ví dụ:

1. Risk analyst đọc case `UNDER_INVESTIGATION`, response có `riskScore` và `investigationNotes` được cache theo URL `/orders/42`.
2. Khách hàng đọc cùng URL.
3. Nếu cache không phân biệt principal/policy, khách hàng có thể nhận response quản trị.

Hoặc object chuyển từ `DRAFT` sang `PUBLISHED`, nhưng cache vẫn giữ response cũ hoặc ngược lại. Cần cân nhắc:

- Response riêng tư dùng `Cache-Control: private` hoặc `no-store` theo độ nhạy cảm.
- Cache key phải phản ánh mọi yếu tố làm thay đổi response, như viewer/tenant/role hoặc policy version; tránh đưa token thô vào cache key/log.
- Cache authorization decision cần TTL và invalidation khi owner, assignment, role, share hoặc state thay đổi.
- Khi object chuyển trạng thái, vô hiệu hóa cache của các representation bị ảnh hưởng.
- Kiểm tra quyền trước khi trả dữ liệu từ cache nếu quyền có thể thay đổi nhanh.
- Không cache response lỗi hoặc dữ liệu nhạy cảm theo cách dùng chung giữa các caller.

ETag/conditional GET cũng phải đại diện cho representation mà viewer được phép thấy. Nếu cùng object có nhiều projection, ETag dùng chung có thể khiến client nhận `304 Not Modified` dù representation theo quyền đã thay đổi. Tạo validator theo representation/policy scope hoặc tắt cache cho response nhạy cảm.

## 9. Trạng thái thay đổi đồng thời khi tạo response

Một lỗi tinh vi xảy ra khi ứng dụng đọc state, tính field mask rồi object đổi trạng thái trước khi dữ liệu được trả. Ví dụ file đang `AVAILABLE` khi kiểm tra, nhưng scanner chuyển sang `QUARANTINED` ngay trước khi download bắt đầu.

Với output nhạy cảm, cần xác định thời điểm quyết định quyền và tính nhất quán cần bảo đảm:

- Đọc state và dữ liệu trong cùng transaction/snapshot phù hợp khi tạo response.
- Với download/stream dài, kiểm tra trạng thái trước khi cấp quyền và cân nhắc khả năng thu hồi URL/stream nếu trạng thái đổi.
- Dùng version/ETag hoặc điều kiện truy vấn để phát hiện object thay đổi giữa kiểm tra và sử dụng.
- Với thao tác quan trọng, query chỉ lấy dữ liệu khi state và quyền thỏa điều kiện.
- Nếu không xác định được state hiện tại hoặc policy service lỗi, không trả field nhạy cảm theo quyết định cũ.

Ví dụ truy vấn chỉ lấy file được phép tải:

```sql
SELECT f.id, f.storage_key, f.content_type
FROM files f
WHERE f.id = :fileId
  AND f.tenant_id = :trustedTenantId
  AND f.owner_id = :trustedUserId
  AND f.status = 'AVAILABLE';
```

Query này giới hạn owner, tenant và state cho một chính sách đơn giản. Nếu có quyền chia sẻ hoặc assignment, cần bổ sung quan hệ được phép. Không dùng query này thay cho authorization tổng thể nếu policy phức tạp hơn.

## 10. Không để output tạo side channel

Ngay cả khi field nhạy cảm bị loại khỏi JSON, API vẫn có thể tiết lộ thông tin qua:

- Khác biệt rõ rệt về response time giữa object tồn tại và không tồn tại.
- Khác biệt status code hoặc thông báo lỗi làm lộ trạng thái điều tra, khóa hoặc xóa.
- Count, pagination, facet hoặc kết quả search.
- Header, ETag, filename, content length, redirect URL hoặc metadata tệp.
- Log, trace, metric label hoặc thông báo webhook gửi tới bên không phù hợp.
- Cache hit/miss hoặc kích thước response có thể suy luận field ẩn.

Không phải mọi khác biệt đều cần làm bằng nhau về thời gian; mục tiêu là tránh tín hiệu ngoài ý muốn có thể tiết lộ dữ liệu nhạy cảm trong threat model. Có thể dùng response lỗi tổng quát, query có scope, cache policy phù hợp và giới hạn metadata. Đừng đưa `riskScore`, `internalStatus` hoặc rule name vào header chỉ vì không muốn đặt chúng trong body.

## 11. Audit và giám sát quyết định output

Với dữ liệu nhạy cảm, nên ghi nhận ai đã xem object, loại dữ liệu được trả và quyết định policy ở mức cần thiết:

- Actor/viewer đã được xác thực và tenant scope.
- Object ID/type và trạng thái tại thời điểm truy cập.
- Action như `read`, `download`, `export`.
- Policy/field mask version hoặc nhóm field được phép.
- Allow/deny và request ID để liên kết các tầng.

Không ghi toàn bộ response hoặc giá trị secret vào audit log. Nếu cần chứng minh một trường đã được truy cập, ghi tên nhóm dữ liệu hoặc event phù hợp, giới hạn quyền đọc log và bảo vệ tính toàn vẹn của audit trail.

Theo dõi các dấu hiệu như user liên tục dò object ở trạng thái ẩn, tải file vừa chuyển sang quarantine, export có số field bất thường, response cache trả khác nhau giữa viewer, hoặc tỷ lệ `403`/`404` tăng đột biến. Cảnh báo nên gắn với actor, endpoint, tenant và loại dữ liệu, nhưng tránh dùng dữ liệu cá nhân/secret làm metric label.

## 12. Kiểm thử output khi object có trạng thái đặc biệt

Test phải bao gồm nhiều viewer và nhiều trạng thái của cùng object. Đừng chỉ kiểm tra một response cho một role.

| Object/state | Viewer | Kiểm tra output mong đợi |
|---|---|---|
| `DRAFT` | Người tạo | Được xem field bản nháp cần thiết; không lộ secret hệ thống |
| `DRAFT` | Người dùng khác | Không tìm thấy object hoặc bị từ chối theo policy |
| `PENDING_REVIEW` | Người gửi | Thấy trạng thái chờ; không thấy reviewer private note |
| `PENDING_REVIEW` | Reviewer được phân công | Thấy nội dung và trường review được cấp quyền |
| `UNDER_INVESTIGATION` | Chủ giao dịch | Chỉ thấy trạng thái/hướng dẫn tổng quát |
| `UNDER_INVESTIGATION` | Risk analyst không được phân công | Không thấy case detail nếu assignment là điều kiện |
| `UNDER_INVESTIGATION` | Risk analyst được phân công | Thấy field risk theo scope |
| `QUARANTINED` | Chủ file | Có thể thấy metadata an toàn; không có download URL/nội dung |
| `QUARANTINED` | Người khác | Không lộ sự tồn tại hoặc metadata nếu policy yêu cầu |
| `ARCHIVED` | User thông thường | Không xuất hiện trong list/search mặc định |
| `LEGAL_HOLD` | Admin không có quyền retention | Không được xem field pháp lý hoặc thao tác trái policy |

Các nhóm test nên có:

1. **Field allowlist:** xác minh field được phép có mặt và field cấm vắng mặt.
2. **State transition:** thay state rồi gọi lại API, xác minh projection thay đổi đúng.
3. **Object authorization:** dùng ID object của user/tenant khác và xác minh không rò rỉ.
4. **List/search/export:** xác minh object ẩn không xuất hiện qua đường phụ và count không tiết lộ.
5. **Cache isolation:** đọc cùng URL bằng hai viewer khác quyền; không nhận response của nhau.
6. **Race condition:** đổi state trong lúc tạo response/download; xác minh không trả dữ liệu theo policy cũ.
7. **Error/side channel:** kiểm tra status, body, header, filename, ETag và metadata.
8. **Regression:** giữ test cho từng trường hợp rò rỉ đã phát hiện.

Ví dụ MockMvc kiểm tra file quarantine không trả URL tải:

```java
@Test
@WithMockUser(username = "file-owner", authorities = "file:read")
void quarantinedFileDoesNotExposeDownloadLocation() throws Exception {
    mockMvc.perform(get("/api/files/{id}", TestFiles.QUARANTINED_ID))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.status").value("UNAVAILABLE"))
        .andExpect(jsonPath("$.downloadUrl").doesNotExist())
        .andExpect(jsonPath("$.storageKey").doesNotExist())
        .andExpect(jsonPath("$.scanDetails").doesNotExist());
}
```

Ví dụ giả định owner được xem metadata an toàn của file quarantine. Nếu policy yêu cầu che giấu cả object, test phải mong đợi `404` và kiểm tra list/search cũng không tiết lộ file. Test cần đọc fixture đúng trạng thái và xác minh response thực tế, không chỉ dựa vào mapper unit test.

## 13. Checklist review trước khi phát hành

- [ ] Đã liệt kê các trạng thái object làm thay đổi khả năng hiển thị dữ liệu.
- [ ] Quyền truy cập object được kiểm tra trước khi tạo response.
- [ ] Field mask xét viewer, tenant, action, object state và quan hệ được phép.
- [ ] DTO/projection tách khỏi entity; không serialize entity trực tiếp.
- [ ] Secret và field never-return không xuất hiện trong response kể cả với admin thông thường.
- [ ] Detail, list, search, count, export, GraphQL, download và webhook áp dụng cùng policy.
- [ ] Trạng thái đặc biệt chỉ tiết lộ mức thông tin cần thiết cho từng viewer.
- [ ] Cache key, TTL, invalidation và ETag không làm lộ projection của viewer khác.
- [ ] State và dữ liệu được đọc nhất quán; xử lý race khi object đổi trạng thái.
- [ ] Error, header, filename, metadata và timing không tạo side channel ngoài ý muốn.
- [ ] Audit ghi nhận subject, object, state và action ở mức cần thiết mà không lưu secret.
- [ ] Có test nhiều viewer, nhiều state, list/search/export, cache và race condition.

## Kết luận

Khi object có trạng thái đặc biệt, API cần quyết định không chỉ người gọi có được xem object hay không mà còn field nào được phép xuất hiện ở thời điểm đó. Kết hợp object authorization, property authorization và state-aware response projection giúp giữ output phù hợp với vai trò và quy trình nghiệp vụ. DTO riêng, cache isolation, kiểm soát side channel và test theo ma trận viewer/state giúp tránh việc một endpoint an toàn nhưng một đường truy cập khác lại làm lộ dữ liệu.
