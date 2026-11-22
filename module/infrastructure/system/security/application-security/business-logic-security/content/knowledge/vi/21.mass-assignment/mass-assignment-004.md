# Nested property binding: kiểm soát gán dữ liệu vào thuộc tính lồng nhau

## 1. Mục tiêu bài học

Trong chương **Mass Assignment** của module **Bảo mật logic nghiệp vụ** (mã dịch vụ: SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY), **nested property binding** là quá trình ánh xạ input vào các thuộc tính nằm sâu trong một cấu trúc đối tượng.

Ví dụ, dữ liệu có thể được đưa vào deliveryAddress.city, lines[0].quantity hoặc budgetAccount.owner.id, tùy giao thức và binder được ứng dụng hỗ trợ.

Binding lồng nhau giúp xây dựng API thuận tiện. Rủi ro xuất hiện khi caller điều khiển được những nhánh hoặc thuộc tính mà hành động hiện tại không cho phép sửa, đặc biệt khi input được gán trực tiếp vào entity và các đối tượng liên quan.

Sau bài học, bạn có thể:

- Nhận diện ranh giới giữa dữ liệu lồng nhau được phép nhập và object graph có thẩm quyền.
- Hiểu vì sao allowlist chỉ ở cấp gốc không đủ.
- Tách value object, tham chiếu entity và collection con khi thiết kế command.
- Ngăn đổi giá, giả phê duyệt, chuyển quan hệ hoặc sửa đối tượng dùng chung qua payload con.
- Xử lý PATCH, null, danh sách và property path có ngữ nghĩa rõ ràng.
- Kiểm thử các đường binding lồng nhau cùng transaction, scope và trạng thái nghiệp vụ.

## 2. Binding có thể đi sâu hơn field nhìn thấy trên form

Một cấu trúc JSON có thể là:

~~~json
{
  "deliveryAddress": {
    "recipientName": "Người nhận",
    "street": "Địa chỉ minh họa",
    "city": "Thành phố minh họa"
  }
}
~~~

Nếu command chỉ cho phép ba giá trị này thì cấu trúc trên có thể hợp lệ. Nhưng entity dùng trong hệ thống có thể còn chứa:

~~~text
deliveryAddress.verificationStatus
deliveryAddress.verifiedBy
deliveryAddress.sourceAddressBookEntry.id
deliveryAddress.internalRiskFlags
~~~

Nếu binder hoặc mapper tự đi qua toàn bộ object graph, caller có thể thử gửi thêm các nhánh đó dù UI không hiển thị.

### 2.1. JSON lồng nhau và property path là hai dạng đầu vào

Một số cơ chế nhận JSON object. Một số cơ chế có thể nhận tên field dạng đường dẫn, ví dụ:

~~~text
deliveryAddress.city
lines[0].quantity
budgetAccount.owner.personId
~~~

Ý nghĩa cụ thể phụ thuộc giao thức, parser và cấu hình. Không phải mọi JSON key chứa dấu chấm đều tự được hiểu là một đường dẫn.

Điều cần kiểm chứng là các dạng input mà endpoint thực sự hỗ trợ có thể chạm tới thuộc tính nào. Chặn một cách viết không có tác dụng nếu endpoint còn chấp nhận một biểu diễn khác.

### 2.2. Ranh giới tin cậy

~~~text
Input do caller đề nghị
    → decode theo hợp đồng
    → command với tập thuộc tính được phép
    → kiểm tra quyền, scope, trạng thái và dữ liệu
    → domain thực hiện thay đổi cụ thể
    → lưu dữ liệu có thẩm quyền
~~~

Không nên rút gọn thành:

~~~text
Input
    → bind/merge trực tiếp vào entity đang được quản lý
    → save toàn bộ graph
~~~

Các setter, quan hệ và field phục vụ persistence không đồng nghĩa là API công khai cho người gọi sửa.

## 3. Một ví dụ mass assignment qua nhánh con

Giả sử endpoint cho phép sửa mô tả, địa chỉ giao hàng và số lượng dòng trong hồ sơ mua hàng. Server đã kiểm tra actor được sửa hồ sơ X.

Handler khái niệm:

~~~java
PurchaseRequest update(Actor actor, RequestId id, Map<String, Object> input) {
    var request = requests.findById(id)
            .orElseThrow(NotFound::new);

    authorization.requireCanEdit(actor, request);
    graphMapper.merge(input, request);

    return requests.save(request);
}
~~~

Nếu graphMapper có thể đi sâu và gán mọi property phù hợp, caller thử:

~~~json
{
  "deliveryAddress": {
    "city": "Thành phố minh họa",
    "verificationStatus": "VERIFIED",
    "verifiedBy": "trusted-service"
  },
  "lines": [
    {
      "id": "line-12",
      "quantity": 1,
      "pricingSnapshot": {
        "unitPriceMinor": 1,
        "discountPercent": 100
      }
    }
  ],
  "budgetAccount": {
    "id": "another-budget",
    "tenantId": "another-tenant",
    "limitMinor": 999999999
  }
}
~~~

Các lớp kiểm soát bị bỏ qua có thể gồm:

- Trạng thái xác minh địa chỉ vốn chỉ được dịch vụ có thẩm quyền thiết lập.
- Giá và chiết khấu phải theo snapshot/policy phía server.
- Quyền dùng hoặc chỉnh sửa tài khoản ngân sách liên quan.
- Biên tenant của đối tượng tham chiếu.
- Hành động đổi liên kết, vốn khác với sửa nội dung thông thường.

Không phải ứng dụng nào cũng sẽ bind các nhánh này. Lỗ hổng phụ thuộc đường ánh xạ thực tế. Bài học là phải giới hạn có chủ đích, thay vì dựa vào việc caller không biết cấu trúc entity.

### 3.1. Cho phép deliveryAddress chưa đủ

Một kiểm tra chỉ xét tên field cấp gốc có thể cho qua mọi thứ bên dưới deliveryAddress.

Allowlist cần trả lời:

~~~text
deliveryAddress:
  recipientName: được nhận
  street: được nhận
  city: được nhận
  verificationStatus: không được nhận
  verifiedBy: không được nhận
  sourceAddressBookEntry: không được nhận qua command này
~~~

Quy tắc tương tự áp dụng cho từng phần tử lines, không chỉ cho tên collection.

### 3.2. Có quyền sửa cha chưa đủ quyền sửa đối tượng liên quan

Actor được sửa purchase request không mặc nhiên được sửa budget account, customer profile, user hoặc price list được request tham chiếu.

Nếu persistence có khả năng lưu các thay đổi lan sang entity liên quan, một payload con có thể tác động nhiều đối tượng dù handler chỉ chủ động gọi save trên đối tượng gốc.

Cần kiểm soát cả giá trị được gán và ranh giới những entity được phép thay đổi.

## 4. Phân loại từng nhánh trước khi thiết kế binding

| Loại nhánh | Ví dụ | Cách tiếp nhận phù hợp |
|---|---|---|
| Value object thuộc đối tượng gốc | Snapshot địa chỉ giao hàng | Chỉ nhận các giá trị được phép, tạo value object bằng code có chủ đích |
| Tham chiếu tới entity khác | budgetAccountId | Nhận ID nếu action cho phép; nạp và kiểm tra entity ở server |
| Collection con thuộc aggregate | Các dòng hàng | Command theo ý định, xác minh từng ID thuộc đúng cha và tenant |
| Dữ liệu tính toán | pricingSnapshot, totalMinor | Tính hoặc lấy từ nguồn có thẩm quyền, không bind từ input sửa thông thường |
| Chứng cứ workflow | approval, approvedBy, paidAt | Chỉ command tương ứng được tạo/thay đổi |
| Quan hệ quyền | owner, members, roles | Action quản lý quyền riêng với kiểm tra phù hợp |
| Metadata mở | Nhãn/thuộc tính tùy chỉnh | Giới hạn ý nghĩa và kiểu; không đưa lại vào binder để sửa domain |

Một cấu trúc lồng nhau có thể chứa nhiều loại nhánh. Không thể áp dụng một quy tắc merge chung cho tất cả.

### 4.1. Value object không có nghĩa mọi field đều được sửa

Một snapshot địa chỉ có thể chứa dữ liệu người dùng nhập và kết quả xác minh phía server. Command chỉ nhận phần người dùng được quyết định.

Nếu thay địa chỉ làm mất hiệu lực xác minh, domain phải đặt lại trạng thái phù hợp. Không giữ VERIFIED cũ cho nội dung địa chỉ mới.

### 4.2. Tham chiếu ID khác object patch

Nếu endpoint chỉ cho chọn một budget account có sẵn, input nên biểu đạt việc chọn đó theo hợp đồng, không là cả một budgetAccount entity có các field có thể bị merge.

Nhận budgetAccountId vẫn chưa đủ an toàn: cần kiểm tra quyền chọn, tenant, quan hệ nghiệp vụ và trạng thái của account.

Chọn account và sửa hạn mức account là hai hành động khác nhau.

## 5. Thiết kế hợp đồng input đóng ở từng cấp

### 5.1. DTO gốc an toàn nhưng DTO con mở vẫn có rủi ro

Một UpdateRequestInput chỉ chứa address nhưng address lại có kiểu entity đầy đủ sẽ tiếp tục mở bề mặt binding phía dưới.

Tương tự:

~~~text
DTO gốc có allowlist
    → nested Map<String, Object>
    → mapper tổng quát đi vào domain
~~~

vẫn có thể tạo mass assignment.

Cần kiểm soát mọi node mà input có thể đi tới: tên field, kiểu giá trị, độ sâu và các loại con được phép.

### 5.2. Ví dụ command theo ý định

~~~java
record DeliveryAddressInput(
        String recipientName,
        String street,
        String city) {
}

record LineQuantityInput(
        LineId lineId,
        int quantity) {
}

record ChangeLineQuantitiesCommand(
        RequestId requestId,
        long expectedContentRevision,
        List<LineQuantityInput> changes) {
}
~~~

Các kiểu trên chỉ minh họa hợp đồng. Chúng không chứa owner, tenant, verification, pricing snapshot, approval hay entity ngân sách.

Có thể dùng command riêng ReplaceDeliveryAddress, ChangeLineQuantities, AddLine hoặc RemoveLine thay vì một cây input cho phép thay mọi nhánh.

Một DTO hẹp không thay thế quyền, kiểm tra giá trị và trạng thái. Nó giảm số loại thay đổi mà một command có thể biểu đạt.

### 5.3. Root và nested unknown fields đều cần chính sách

Nếu chọn từ chối field không thuộc hợp đồng:

~~~text
Field lạ ở cấp gốc:
    từ chối.

Field lạ trong deliveryAddress:
    từ chối.

Field lạ trong từng phần tử changes:
    từ chối.

Nhánh không được hỗ trợ:
    từ chối trước khi tạo hiệu ứng.
~~~

Không chỉ kiểm tra top-level rồi bỏ qua schema của phần tử collection.

Nếu chọn bỏ qua field lạ vì tương thích, phải bảo đảm field đó không còn được một converter, mapper, event builder hoặc worker khác đọc từ raw payload để tạo hiệu ứng. Một pipeline vừa “bỏ qua” vừa giữ raw input để merge sau là không nhất quán.

### 5.4. Read model không tự là write model

API có thể cần trả:

~~~text
line.id
line.quantity
line.pricingSnapshot.unitPriceMinor
line.pricingSnapshot.currency
line.approvalStatus
~~~

để UI hiển thị. Điều này không có nghĩa endpoint nhận lại toàn bộ cấu trúc đó khi cập nhật.

Tách input theo action và output theo quyền xem. Không lấy một response đầy đủ rồi deserialize/merge nguyên trở lại entity chỉ để tiện xây form.

### 5.5. Blocklist nhạy cảm không bao phủ được toàn bộ graph

Chặn owner, role và status ở cấp gốc có thể bỏ sót:

~~~text
account.owner
members[0].role
workflow.approval.status
lines[0].pricingSnapshot.approvedUnitPrice
~~~

Tên mới hoặc nhánh mới trong entity cũng có thể tự xuất hiện trong bề mặt bind nếu cơ chế cho phép mọi property.

Allowlist theo hợp đồng đóng giúp một field mới trong domain không tự trở thành input được phép.

## 6. Property path, converter và kiểu động

### 6.1. Allow prefix quá rộng có thể mở các hậu duệ nhạy cảm

Các mẫu tương đương “mọi thứ dưới address” hoặc “mọi property trong lines” cần được xem xét cẩn thận.

Nếu domain sau này thêm address.verificationStatus, một wildcard cũ có thể vô tình cho caller sửa nó.

Nên định nghĩa các đường dẫn/ngữ nghĩa được phép tới mức phù hợp, kết hợp kiểu node và command. Không chỉ dùng kiểm tra chuỗi bắt đầu bằng một prefix.

### 6.2. Kiểm tra biểu diễn sau khi decode theo đúng giao thức

Nếu endpoint hỗ trợ đường dẫn property, hãy kiểm soát tập segment đã được parser hiểu theo hợp đồng.

Không tự ghép nhiều quy tắc escape/chuẩn hóa ở các tầng rồi giả định chúng cho cùng một path. Từ chối cú pháp mơ hồ hoặc dạng không hỗ trợ, thay vì sửa nó thành một đường dẫn khác.

Các định dạng JSON, form hoặc patch theo path có thể có biểu diễn khác nhau. Chỉ hỗ trợ những dạng đã được đặc tả và kiểm thử; không suy ra một allowlist cho mọi định dạng từ một chuỗi thô.

### 6.3. ID converter không được bỏ qua scope

Một converter có thể biến một chuỗi ID thành entity. Nếu nó lookup toàn cục trước khi ứng dụng kiểm tra quyền, nested binding có thể gắn entity ngoài tenant vào graph.

Một lựa chọn dễ kiểm soát là decode ID thành kiểu giá trị, sau đó tầng ứng dụng nạp entity trong tenant/scope phù hợp và kiểm tra quan hệ.

Nếu hệ thống có converter nhận entity trực tiếp, phải chứng minh nó có đúng ngữ cảnh, thẩm quyền và hành vi lỗi. Không mặc định “converter tìm được entity” nghĩa là caller được dùng/sửa entity đó.

### 6.4. Chọn subtype cũng là một quyền cần giới hạn

Nếu có binding đa hình, caller không được tự chỉ ra một lớp nội bộ tùy ý để có thêm field.

Có thể ánh xạ discriminator vào tập subtype nghiệp vụ được cho phép. Mỗi subtype vẫn cần schema và quyền tương ứng.

Vấn đề đang xét là không để đổi kiểu input làm mở các thuộc tính như internalLimit, permissions hoặc verified. Tên lớp hoặc type hint không phải bằng chứng thẩm quyền.

### 6.5. Metadata mở phải giữ nguyên vai trò dữ liệu

Một map tùy chỉnh có thể hợp lệ cho nhãn hoặc dữ liệu mở của sản phẩm. Cần quy định namespace, kiểu, kích thước và cách sử dụng.

Không đưa map đó trở lại một binder/mapper để diễn giải các key như property path của domain. Một trường được nhận như metadata không được trở thành lệnh sửa owner hoặc trạng thái ở bước sau.

## 7. Collection con là một ranh giới quan trọng

### 7.1. ID phần tử phải thuộc đúng cha

Actor được sửa request X không tự được sửa line L của request Y.

Với mỗi lineId, server cần xác định:

~~~text
line thuộc request đang xử lý
line thuộc đúng tenant
action trên line được phép
line còn trong trạng thái phù hợp
version hoặc quan hệ liên quan không bị thay đổi trái ý định
~~~

Không lấy một line toàn cục từ input rồi gọi setParent(X) trước khi kiểm tra. Hành động đó có thể biến update số lượng thành chuyển dòng hàng giữa hồ sơ.

### 7.2. Chỉ số không phải danh tính bền vững

lines[0] là vị trí trong một biểu diễn, không nhất thiết là dòng nghiệp vụ mà caller đã xem nếu danh sách vừa thay đổi thứ tự.

Có thể dùng ID ổn định và expected revision cho command theo dòng. Nếu API thật sự dùng chỉ số, phải có quy tắc snapshot/version rõ ràng.

Không cho chỉ số thưa hoặc quá lớn làm binder tự tạo cấu trúc khổng lồ. Giới hạn phải được kiểm tra đủ sớm, trước các thao tác cấp phát không cần thiết.

### 7.3. Trùng ID cần có hợp đồng rõ

Hai phần tử cùng lineId có thể bị hiểu theo các cách khác nhau:

~~~text
validator kiểm tra phần tử đầu
mapper lấy phần tử cuối
bộ tính tổng cộng cả hai
repository chỉ lưu một dòng
~~~

Trong command đổi số lượng minh họa, từ chối lineId trùng. Không âm thầm chọn first-wins/last-wins ở một tầng trong khi tầng khác dùng nghĩa khác.

### 7.4. Update, replace, add và remove khác nhau

Nếu changes là danh sách các dòng cần đổi số lượng:

- Dòng không xuất hiện được giữ nguyên.
- Không có lineId không đồng nghĩa xóa dòng.
- Không nhận line mới qua command này.
- Quantity không hợp lệ không được hiểu thành lệnh xóa ngầm.

Nếu API chọn replace toàn bộ collection, cần nói rõ những dòng bị bỏ sẽ ra sao và kiểm tra quyền xóa/tác động nghiệp vụ.

Một mapper thay cả collection hoặc persistence xóa các phần tử bị loại có thể tạo hiệu ứng lớn hơn việc caller được phép làm. Việc đó phải do domain quyết định, không là tác dụng phụ ngoài hợp đồng.

### 7.5. Kiểm tra từng phần tử chưa đủ cho cả tập

Sau khi từng dòng hợp lệ, còn có thể cần kiểm tra số lượng dòng, tổng số lượng, tổng tiền, currency hoặc ràng buộc sản phẩm.

Giá và chiết khấu lấy theo nguồn/snapshot giá có thẩm quyền của hồ sơ, không theo nested pricing data do caller gửi. Không mặc định phải lấy giá mới nhất nếu hợp đồng nghiệp vụ đã chốt một snapshot khác.

## 8. PATCH và merge phải có ngữ nghĩa rõ ràng

### 8.1. Partial object không tự nói là merge hay replace

Caller gửi:

~~~json
{
  "deliveryAddress": {
    "city": "Thành phố mới"
  }
}
~~~

Hai cách hiểu có thể khác nhau:

~~~text
Merge:
  chỉ đổi city, giữ recipientName và street.

Replace:
  thay cả address bằng object mới;
  recipientName và street không được cung cấp.
~~~

Nếu validator giả định replace còn mapper thực hiện merge, hoặc ngược lại, dữ liệu cuối có thể khác dữ liệu đã kiểm tra.

Cần công bố rõ ngữ nghĩa theo action. Một command ReplaceDeliveryAddress có thể yêu cầu đủ các field cho value object mới. Một command patch địa chỉ cần biểu diễn rõ thao tác ở từng field.

### 8.2. Phân biệt không gửi, clear và set

Một mô hình có thể dùng:

~~~text
Unspecified: không thay đổi.
Clear: xóa nếu được phép.
Set(value): đặt giá trị mới hợp lệ.
~~~

Không để DTO nullable làm mất khác biệt giữa missing và null nếu endpoint cần phân biệt.

address=null không được tự xóa địa chỉ trong khi trạng thái nghiệp vụ vẫn bắt buộc có địa chỉ. Một field con rỗng cũng không tự trở thành lệnh xóa quan hệ.

### 8.3. Dữ liệu server-derived phải được tính lại

Nếu nội dung địa chỉ thay đổi, verified=true của địa chỉ cũ không tự áp dụng cho nội dung mới.

Nếu quantity thay đổi, total phải được tính lại theo giá có thẩm quyền. Không giữ tổng cũ hoặc nhận total từ cùng payload để làm số liệu đối chiếu.

Nếu thay đổi ảnh hưởng nội dung đã phê duyệt, cần chính sách revision/tái phê duyệt. Nested merge không được âm thầm giữ approval cũ cho dữ liệu mới.

### 8.4. Tách sửa snapshot và chọn bản ghi dùng chung

Nếu deliveryAddress là một bản sao giá trị thuộc request, sửa snapshot không nhất thiết sửa address book entry nguồn.

Nếu chọn một addressBookEntryId, server có thể xác minh quyền rồi tạo snapshot theo chính sách. Không merge các field client gửi vào chính bản ghi address book dùng chung chỉ vì request có tham chiếu tới nó.

Hai loại thao tác cần command và quyền phù hợp. Không để kiểu dữ liệu nested tự quyết định đối tượng nào sẽ bị thay đổi.

## 9. Java minh họa cập nhật dòng con

Ví dụ dưới đây minh họa command chỉ đổi số lượng các dòng đang có. Nó không thêm, xóa, đổi product hoặc nhận giá từ client.

Mã dùng các kiểu và repository giả định, không phải chương trình độc lập.

Giả định:

- Actor và tenant context đã được xác minh.
- Mọi đường sửa aggregate và các dòng liên quan tuân thủ cùng giao thức khóa/version.
- Candidate là dữ liệu tách biệt, không giữ tham chiếu mutable tới entity được persistence quản lý.
- Pricing facts lấy theo hợp đồng giá/snapshot có thẩm quyền của request.
- Các thao tác lưu bắt buộc cùng transaction.

~~~java
DraftChanged changeLineQuantities(
        Actor actor, ChangeLineQuantitiesCommand command) {
    return transactions.required(() -> {
        var request = requests.lockForUpdate(
                actor.tenantId(), command.requestId());

        authorization.requirePermit(
                actor, EDIT_DRAFT_LINES, request);
        requireState(request, DRAFT);
        requireContentRevision(
                request, command.expectedContentRevision());

        collectionRules.requireBoundedUniqueChanges(
                command.changes());

        var before = request.auditSnapshot();
        var candidate = PurchaseDraftCandidate.fromSnapshot(
                request.readSnapshot());
        var pricingFacts = prices.requireApplicableFacts(request);

        for (var change : command.changes()) {
            var line = request.requireOwnedLine(change.lineId());

            authorization.requireCanChangeQuantity(
                    actor, request, line);
            quantities.requireAllowed(
                    line, change.quantity(), pricingFacts);

            candidate = candidate.withQuantity(
                    line.id(), change.quantity());
        }

        var pricedCandidate = pricing.recalculate(
                candidate, pricingFacts);
        draftRules.requireValid(pricedCandidate);

        request.applyValidatedLineQuantitiesAndTotals(
                pricedCandidate);
        request.advanceContentRevision();
        requests.save(request);
        audit.insertLinesChanged(actor, before, request);
        outbox.insertDraftLinesChanged(request);

        return new DraftChanged(
                request.id(), request.contentRevision());
    });
}
~~~

### 9.1. Các ranh giới cần kiểm chứng

requireOwnedLine phải dựa trên quan hệ thực của dòng trong aggregate đang được bảo vệ. Nó không được tự nạp một dòng ở nơi khác rồi chuyển parent.

collectionRules kiểm tra số phần tử, ID trùng và cấu trúc theo hợp đồng. quantities kiểm tra giá trị và giới hạn nghiệp vụ. draftRules kiểm tra toàn bộ trạng thái cuối.

applyValidatedLineQuantitiesAndTotals chỉ áp dụng các thay đổi đã được cho phép. Nó không là một graph merge khác nhận lại raw payload.

Các giá trị price, discount hoặc approval do client lén gửi không đi vào command. Decoder cần thực thi chính sách field lạ cả ở từng phần tử changes.

### 9.2. Domain method không được trở thành binder thứ hai

Một phương thức tên applyValidated nhưng thực chất copy mọi field từ một map mở vẫn giữ nguyên vấn đề.

Candidate nên chứa những giá trị có nguồn gốc rõ ràng: ID dòng đã đối chiếu, số lượng được chấp nhận và kết quả tính giá phía server. Nó không chứa entity ngân sách hoặc một object con tùy ý do caller tạo.

Nếu có field cần đổi nguồn thẩm quyền, dùng command riêng thay vì mở rộng mapper vô hạn.

### 9.3. Đường AddLine hoặc RemoveLine cần quy tắc riêng

AddLine phải xác minh product/variant và nguồn giá, không cho client tạo một child entity với mọi field.

RemoveLine phải kiểm tra quyền xóa, trạng thái, dòng bắt buộc và tác động tới tổng tiền/approval. Không dùng quantity=0 như lệnh xóa ngầm nếu hợp đồng không quy định.

ID do server tạo cho thao tác thêm và idempotency phù hợp giúp tránh tạo nhiều dòng do retry.

## 10. Tránh mutation trước khi validate xong

### 10.1. Entity đang được quản lý có thể bị theo dõi thay đổi

Trong cơ chế persistence có theo dõi thay đổi, gọi save không phải ranh giới duy nhất có thể ghi dữ liệu.

Nếu binder đã sửa entity/association rồi validator phát hiện lỗi, một đường flush hoặc xử lý exception không đúng có thể làm dữ liệu bị ghi ngoài ý định.

Không bind vào entity thật rồi hy vọng “chưa gọi save nên chưa sao”. Dựng candidate tách biệt, validate, sau đó áp dụng thay đổi có chủ đích là cách dễ kiểm soát hơn.

Một shallow copy vẫn có thể trỏ tới các object con mutable dùng chung. Cần hiểu rõ candidate có thực sự tách biệt hay không.

### 10.2. Transaction phải bao phủ thay đổi nghiệp vụ bắt buộc

Nếu một thay đổi gồm:

~~~text
đổi quantity
tính/lưu tổng mới
tăng revision
ghi audit
ghi outbox bắt buộc
~~~

thì các bước phải commit hoặc rollback theo cùng hợp đồng.

Exception validation không được bị catch rồi tiếp tục commit graph đã bị sửa một phần. Không tạo notification/job bên ngoài transaction trước khi toàn bộ input được chấp nhận.

Rollback DB không hoàn tác một lời gọi dịch vụ ngoài đã tạo hiệu ứng; không đặt lời gọi đó vào mapper/setter như một tác dụng phụ khó kiểm soát.

### 10.3. Concurrency vẫn cần được bảo vệ

Một request hợp lệ về field có thể được xây từ snapshot cũ. Request khác vừa submit, chuyển quyền hoặc thay collection.

Khóa/version/cập nhật có điều kiện phải bảo vệ các dữ kiện cần thiết. Nếu submit thắng, đường sửa DRAFT không được ghi đè nội dung đã submit. Nếu sửa thắng, submit phải xem revision mới hoặc nhận xung đột.

Transaction cục bộ không tự khóa dữ liệu quyền hoặc catalog ở dịch vụ khác. Cần chính sách độ mới và kiểm chứng phù hợp với quyết định.

### 10.4. Retry không được tạo thêm hiệu ứng ngoài ý định

Một command set quantity có thể nhìn giống idempotent, nhưng retry vẫn có thể tăng revision, ghi audit/event hoặc đè một thay đổi mới nếu thiếu kiểm soát.

Nếu hỗ trợ idempotency, fingerprint phải giữ đúng ý nghĩa command và binding tenant/actor/action/target theo thiết kế. Cùng key nhưng thay lineId, quantity hoặc semantics patch phải được phát hiện.

Receipt không thay kiểm tra quyền xem kết quả. Một lần retry đã hoàn tất không được merge lại raw input vào trạng thái mới.

## 11. Giới hạn graph trước khi nó trở thành vấn đề tài nguyên

Các giới hạn có thể gồm:

- Kích thước request và chuỗi.
- Độ sâu cấu trúc.
- Số phần tử mỗi collection và tổng phần tử toàn payload.
- Chỉ số lớn nhất nếu giao thức hỗ trợ indexed path.
- Tập field/path được hỗ trợ.
- Số lượng lookup và thay đổi mà một command có thể tạo.

Giới hạn cần được áp dụng đủ sớm; chỉ kiểm tra sau khi binder đã tự mở rộng một collection rất lớn là quá muộn cho mục tiêu bảo vệ tài nguyên.

Giới hạn cấu trúc không thay thế kiểm tra quyền. Một payload nhỏ chỉ đổi approval.status vẫn có thể gây thiệt hại lớn.

Khi vượt giới hạn hoặc thiếu facts bắt buộc, không tự bỏ một phần kiểm soát rồi tiếp tục merge các nhánh còn lại như thể request đã hợp lệ.

## 12. Kiểm thử đường binding thực tế

### 12.1. Dữ liệu nền

Chuẩn bị:

~~~text
Tenant A:
  request X, actor E được sửa bản nháp.
  request Y, E không có quyền sửa.
  line X1 thuộc X.
  line Y1 thuộc Y.
  một budget account được X tham chiếu.

Tenant B:
  request Z và các dòng riêng.
~~~

Chuẩn bị thêm các giá trị verification, pricing, approval và quan hệ ngân sách để có thể phát hiện chúng bị thay đổi ngoài ý định.

Test phải đi qua decoder/binder/handler thật của endpoint liên quan. Chỉ unit test một DTO đã được tạo sẵn có thể bỏ sót field mà binder thật vẫn nhận.

### 12.2. Ma trận tình huống

| Tình huống | Điều phải kiểm chứng |
|---|---|
| Nested address chỉ có field được phép | Cập nhật hợp lệ theo semantics của command |
| Thêm address.verificationStatus/verifiedBy | Không giả kết quả xác minh |
| Thêm line.pricingSnapshot.unitPriceMinor | Không thay giá bằng quyền sửa số lượng |
| Thêm approval.status/approvedBy | Không chuyển workflow hoặc tạo bằng chứng duyệt |
| Chỉ top-level hợp lệ nhưng field sâu không hợp lệ | Chính sách unknown field được thực thi ở node con |
| Gửi budgetAccount object đầy đủ | Không merge hạn mức/tenant/owner của entity dùng chung |
| Chọn accountId ngoài scope | Không tạo/chuyển quan hệ trái phép |
| Gửi line Y1 trong command của X | Không sửa, chuyển cha hoặc tiết lộ dữ liệu Y1 |
| Gửi line của tenant B | Không vượt biên tenant |
| Gửi ID dòng chưa thuộc X | Không tự tạo/attach dòng qua command update |
| Trùng lineId trong collection | Không có validator/mapper/bộ tính tổng dùng các nghĩa khác nhau |
| Bỏ một dòng khỏi changes | Không xóa ngầm nếu command là cập nhật chọn lọc |
| quantity=0 hoặc null ngoài hợp đồng | Không biến thành lệnh remove ngầm |
| Replace address thiếu field bắt buộc | Không lưu value object thiếu dữ liệu |
| Partial patch chỉ một field | Merge/replace đúng hợp đồng, không dùng giả định khác giữa các tầng |
| Clear node đang được nghiệp vụ yêu cầu | Bị chặn theo trạng thái cuối |
| Indexed path vượt giới hạn | Không tự mở rộng collection ngoài giới hạn |
| Type hint/subtype ngoài tập hỗ trợ | Không mở thêm field nội bộ |
| Metadata chứa key giống property path | Xử lý như dữ liệu theo hợp đồng, không sửa domain |
| Input lặp field hoặc có biểu diễn path mơ hồ | Decode nhất quán, không có hai giá trị hiệu lực khác nhau |
| Sửa dòng và submit đồng thời | Không ghi đè revision đã submit |
| Lỗi sau một phần cập nhật trong transaction | Không có graph hoặc dữ liệu liên quan bị commit một phần |
| Replay cùng key, đổi nhánh con/line/giá trị | Không tái sử dụng receipt cho command khác |
| Một field nhạy cảm mới được thêm vào entity | Không tự xuất hiện trong input được phép |

Nếu endpoint không hỗ trợ một kiểu property path, kỳ vọng là nó không được diễn giải như một cách khác để sửa domain. Không cần biến mọi cú pháp thành cú pháp được hỗ trợ chỉ để kiểm thử.

### 12.3. Kiểm thử cả đối tượng gốc và entity liên quan

Sau request bị chặn, đọc lại bằng transaction mới:

~~~text
Nội dung request X không đổi ngoài hợp đồng.
line X1/Y1 giữ đúng cha và tenant.
Không có line mới ngoài ý định.
Giá/discount/total không bị thay từ input trái phép.
Budget account giữ nguyên hạn mức, owner và tenant.
Verification/approval không bị giả.
Revision không tăng như một lần sửa thành công.
Không có outbox/job của hành động bị chặn.
~~~

Nếu chỉ kiểm tra request X, có thể bỏ sót việc graph merge đã sửa một budget account dùng chung hoặc một dòng của Y.

Security/attempt log về lần thử có thể được ghi riêng. Nó không phải audit chứng minh cập nhật thành công.

### 12.4. Một ca kiểm thử giá có sức phân biệt

Chuẩn bị X:

~~~text
X1: quantity=1, unitPriceMinor=10000.
X2: quantity=2, unitPriceMinor=5000.
Tổng = 20000.
content revision = 7.
~~~

Gửi command có ý định đổi X1 thành quantity=3 nhưng kèm một pricingSnapshot chứa unitPriceMinor=1.

Với hợp đồng field nghiêm ngặt, request bị từ chối toàn bộ; đọc lại thấy quantity, giá, tổng và revision đều giữ nguyên.

Sau đó gửi command hợp lệ chỉ có lineId và quantity. Kết quả mong đợi:

~~~text
X1 quantity = 3.
Giá X1 vẫn theo nguồn có thẩm quyền: 10000.
Tổng mới = 40000.
Revision tăng theo hợp đồng.
Không có thay đổi ngân sách hoặc approval ngoài ý định.
~~~

Ca này kiểm tra cả việc chặn giá trái phép lẫn việc sửa số lượng hợp lệ vẫn sử dụng được.

### 12.5. Kiểm thử rollback qua đường persistence thật

Gây lỗi có kiểm soát khi ghi audit/outbox bắt buộc sau khi domain đã áp dụng thay đổi vào entity.

Sau khi transaction kết thúc, root, các dòng, tổng tiền, revision và trạng thái event phải cùng phản ánh rollback.

Cần kiểm tra trên cơ chế lưu trữ thực phù hợp. Mock save không chứng minh một managed association không bị flush hoặc một collection không bị xóa phần tử ngoài ý định.

### 12.6. Kiểm thử concurrency phải chạm dữ liệu được bảo vệ

Dùng hai transaction/kết nối độc lập cho:

~~~text
A: đổi số lượng các dòng của X theo revision 7.
B: submit X theo trạng thái/revision đang thấy.
~~~

Điều phối để chúng thật sự cạnh tranh ở điểm khóa/version.

Sau khi cả hai kết thúc, phải có một thứ tự nghiệp vụ hợp lệ hoặc xung đột được phát hiện. Không được có giá/tổng/nội dung đã thay sau submit mà quyết định workflow vẫn gắn với revision cũ.

Nếu các dòng còn có endpoint sửa riêng, kiểm thử đường đó cũng tuân thủ giao thức aggregate, không chỉ endpoint cập nhật gốc.

## 13. Lỗi và audit không nên làm lộ object graph nội bộ

Thông báo lỗi có thể chỉ ra field path trong hợp đồng, ví dụ:

~~~json
{
  "errors": [
    {
      "field": "changes[0].pricingSnapshot",
      "code": "FIELD_NOT_ALLOWED"
    }
  ]
}
~~~

Không cần trả danh sách mọi property nội bộ mà entity có thể có, kiểu lớp persistence hoặc thông tin của line/account ngoài quyền.

Audit có thể ghi actor, tenant, root/child ID được phép lưu, revision, action, các loại field đã đổi và kết quả commit. Dữ liệu địa chỉ hoặc thông tin tài chính nhạy cảm chỉ được lưu khi thực sự cần và có kiểm soát phù hợp.

Không dump raw payload, token hoặc toàn bộ entity để chẩn đoán. Field path do caller gửi cũng phải được mã hóa/ghi có cấu trúc để không giả thêm dòng log.

Cần phân biệt:

~~~text
Decode/schema bị từ chối.
Không đủ quyền trên root/child/reference.
Không đạt quy tắc nghiệp vụ.
Xung đột version/trạng thái.
Transaction rollback.
Cập nhật đã commit.
~~~

Một trace “đã bind thành công” không chứng minh command hợp lệ hoặc đã được phép thực hiện.

## 14. Tình huống thực hành: quyền sửa cha lan sang graph khác

E có quyền sửa request X. Request X đang tham chiếu một budget account dùng chung. E không có quyền quản trị account đó.

Endpoint nhận nested budgetAccount và lines vì dùng chung entity model cho GET và UPDATE.

E thử hai hướng:

~~~text
Hướng 1:
  giữ root X hợp lệ;
  gửi budgetAccount.limitMinor lớn hơn qua object con.

Hướng 2:
  giữ root X hợp lệ;
  gửi lineId thuộc Y;
  đặt quantity và pricingSnapshot trong cùng phần tử.
~~~

Nếu handler chỉ authorize X rồi merge graph, việc kiểm tra root có thể hoàn toàn thành công mà vẫn tạo thay đổi trái phép ở account hoặc Y.

Thiết kế phù hợp cần:

1. Hợp đồng update chỉ nhận các thay đổi được phép.
2. Nested DTO không chứa trường quyền, hạn mức hoặc giá do server quản lý.
3. Reference được chọn bằng command có ngữ nghĩa rõ và được nạp trong scope.
4. ID child phải thuộc root và tenant hiện tại.
5. Giá/tổng được tính theo nguồn có thẩm quyền.
6. Mọi thay đổi bắt buộc cùng transaction và revision.
7. Output không đưa thêm dữ liệu của entity ngoài quyền vào response.

Nếu thật sự cần đổi hạn mức ngân sách, phải đi qua action quản lý ngân sách với quyền và quy trình tương ứng. Không cấp quyền đó gián tiếp bằng khả năng sửa một request có liên kết tới account.

## 15. Khung rà soát nested binding

~~~text
Action và đối tượng gốc:
Các định dạng input/property path thực sự hỗ trợ:
DTO/schema theo action:

Với từng nhánh:
  value object / reference / child collection / server-controlled
  field được nhận ở mọi độ sâu
  node type và subtype được phép
  semantics missing / null / set / merge / replace
  quyền, tenant và quan hệ cần kiểm tra

Với collection:
  stable ID hay index
  giới hạn, ID trùng, thêm/xóa/bỏ sót
  ràng buộc từng phần tử và toàn tập

Cách dựng candidate tách biệt:
Nguồn giá/trạng thái/verification có thẩm quyền:
Đường áp dụng thay đổi vào domain:
Transaction, version và xử lý persistence có theo dõi thay đổi:
Retry/idempotency, audit và hiệu ứng ngoài:
Các test chạm nhánh sâu và entity liên quan:
~~~

## 16. Câu hỏi tự kiểm tra

1. Vì sao cho phép root field deliveryAddress không có nghĩa được phép mọi property bên trong?
2. DTO con hoặc converter nào của bạn còn mang kiểu domain entity đầy đủ?
3. Actor được sửa root có quyền gì trên reference và child được gửi trong payload?
4. ID collection được kiểm tra với parent thật trước hay sau khi mapper gán quan hệ?
5. Bỏ một phần tử khỏi input là giữ nguyên, xóa hay replace trong hợp đồng hiện tại?
6. Có dữ liệu verification, pricing hoặc approval nào được nhận lại từ read model không?
7. Candidate có tách biệt thật hay vẫn giữ tham chiếu tới managed child/entity dùng chung?
8. Khi validation lỗi, những đối tượng nào cần đọc lại để phát hiện ghi ngoài ý định?
9. Một field mới trong entity có tự làm rộng bề mặt input mà không thay hợp đồng API không?

Nguyên tắc cần giữ là **cấu trúc dữ liệu caller gửi không quyết định phạm vi object graph mà caller được sửa**. Mỗi nhánh và từng thay đổi phải được cho phép có chủ đích, kiểm chứng trong đúng ngữ cảnh và áp dụng qua domain thay vì merge toàn bộ graph.
