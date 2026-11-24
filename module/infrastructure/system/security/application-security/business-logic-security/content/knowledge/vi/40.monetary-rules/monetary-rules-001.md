# Balance ownership: bảo vệ quyền sở hữu số dư

## 1. Vì sao quyền sở hữu số dư là một quy tắc tiền tệ?

Trong chương **Monetary Rules**, *balance ownership* trả lời câu hỏi: **số dư này thuộc về chủ thể nào, và ai được phép làm số tiền khả dụng của chủ thể đó thay đổi?** Đây là một business invariant, tức điều kiện hệ thống phải duy trì qua mọi luồng nghiệp vụ, kể cả khi người dùng sửa request, bỏ qua giao diện, gọi lại API hoặc gửi nhiều yêu cầu đồng thời.

Một API có thể yêu cầu đăng nhập, xác thực chữ ký và kiểm tra số tiền dương nhưng vẫn sai nghiêm trọng nếu cho phép người gọi trừ tiền của người khác. Một ví điện tử có thể tính toán chính xác đến từng đơn vị tiền nhỏ nhất nhưng vẫn mất an toàn nếu endpoint hoàn tiền chuyển tiền về tài khoản do người gọi tùy chọn.

Ví dụ, người dùng An sở hữu ví `wallet-an`, Bình sở hữu `wallet-binh`. An gửi:

~~~http
POST /wallet-transfers
Authorization: Bearer <token-cua-an>
Idempotency-Key: transfer-2026-001
Content-Type: application/json

{
  "sourceAccountId": "wallet-binh",
  "destinationAccountId": "wallet-an",
  "amountMinor": 300000,
  "currency": "VND"
}
~~~

`300000` ở đây là 300.000 VND vì mô hình ví dụ dùng đơn vị nguyên đồng cho VND. Không được suy rộng cách biểu diễn này sang mọi loại tiền.

Nếu backend chỉ kiểm tra `wallet-binh` tồn tại và có đủ tiền, việc chuyển tiền vẫn có thể thành công về mặt kỹ thuật. Lỗi nằm ở quyền thao tác trên đối tượng số dư: An chưa được phép ghi nợ ví nguồn.

Bài học này thuộc phạm vi bảo mật logic nghiệp vụ: thiết kế invariant, quyền theo đối tượng, trạng thái tài khoản, transaction, idempotency và kiểm thử các cách lách quy trình. Mục tiêu là ngăn hệ thống thực hiện một biến động tiền đúng định dạng nhưng sai quyền hoặc sai căn cứ nghiệp vụ.

## 2. Phân biệt chủ sở hữu, người thao tác và nguồn phát sinh quyền

### 2.1. Chủ sở hữu số dư

Chủ sở hữu là người hoặc tổ chức được hệ thống nghiệp vụ ghi nhận quyền lợi đối với số dư. Trong mô hình đơn giản, mỗi tài khoản có một chủ thể sở hữu được xác định rõ:

~~~text
BalanceAccount
  id
  tenantId
  ownerType       // USER hoặc ORGANIZATION trong mô hình này
  ownerId
  currency
  status
  postedMinor
  reservedMinor
  version
~~~

Trong hệ thống thực tế, một tài khoản có thể đại diện cho tiền ký quỹ, tiền chờ quyết toán hoặc nghĩa vụ đối với nhiều bên. Khi đó cần mô hình quyền lợi hoặc sổ phụ phù hợp; không mặc định rằng một cột `ownerId` là đủ để diễn tả quyền sở hữu pháp lý. Bài này dùng mô hình một chủ thể sở hữu cho mỗi tài khoản nội bộ để tập trung vào cơ chế thực thi quyền.

`tenantId` xác định miền cô lập dữ liệu. `ownerId` xác định chủ thể sở hữu trong miền đó. Hai tài khoản cùng tenant chưa chắc có cùng chủ sở hữu; hai bản ghi có cùng giá trị `ownerId` ở hai tenant cũng chưa chắc đại diện cho cùng một chủ thể. Định danh và các ràng buộc phải phản ánh mô hình dữ liệu thực tế.

### 2.2. Người thao tác không nhất thiết là chủ sở hữu

Người thao tác, hay *actor*, là danh tính đang yêu cầu hành động. Actor có thể là:

- Người dùng chi tiền từ ví cá nhân của mình.
- Nhân viên được tổ chức cấp quyền chi tiêu trong hạn mức.
- Dịch vụ quyết toán chuyển tiền theo giao dịch đã được ghi nhận.
- Tiến trình thu phí, hoàn tiền hoặc đối soát có quyền chuyên biệt.

Việc actor khác chủ sở hữu không tự động là lỗi. Lỗi xuất hiện khi hệ thống không chứng minh được **căn cứ cho phép actor thực hiện đúng hành động, trên đúng tài khoản, trong đúng điều kiện**.

Không dùng quy tắc duy nhất `account.ownerId == authenticatedUserId` cho mọi trường hợp. Quy tắc đó phù hợp với ví cá nhân đơn giản nhưng không biểu diễn được tài khoản tổ chức, quyền ủy nhiệm, thu phí theo hợp đồng hoặc hoàn tiền theo giao dịch gốc.

### 2.3. Quyền phải cụ thể theo hành động

| Hành động | Căn cứ quyền cần kiểm tra | Điều không thể tự suy ra |
|---|---|---|
| Xem số dư | Quyền đọc tài khoản trong tenant hiện tại | Có quyền đọc không có nghĩa là được chi tiền |
| Chuyển tiền từ tài khoản | Quyền ghi nợ, hạn mức, trạng thái và điều kiện phê duyệt | Biết ID tài khoản không tạo ra quyền |
| Giữ tiền cho đơn hàng | Quyền giữ tiền và quan hệ tài khoản với giao dịch mua | Được tạo đơn hàng không đồng nghĩa được giữ tiền ở mọi ví |
| Thu tiền từ khoản đã giữ | Quyền capture theo đúng hold và nghiệp vụ gốc | Một hold hợp lệ không cho phép thu vượt số tiền đã giữ |
| Hoàn tiền | Quyền xử lý giao dịch gốc, hạn mức hoàn và quy tắc chọn bên nhận | Gửi được `refundAccountId` không có nghĩa là được tự chọn người nhận |
| Điều chỉnh số dư | Quyền điều chỉnh chuyên biệt, lý do và phê duyệt cần thiết | Vai trò hỗ trợ khách hàng không mặc nhiên được sửa tiền |

Một người quản trị tổ chức có thể được thêm thành viên nhưng không được rút tiền. Nếu sản phẩm cho phép quản trị viên tự cấp quyền chi tiền, đó phải là quyết định chính sách rõ ràng, có kiểm soát tương ứng; không phải hệ quả ngầm của vai trò `ADMIN`.

## 3. Các invariant cần bảo vệ

Với mô hình tài khoản trả trước không cho phép thấu chi, có thể xác định các invariant sau.

**Invariant về quyền:** mọi bút toán làm giảm quyền lợi tiền tệ của một chủ thể phải gắn với actor và căn cứ nghiệp vụ hợp lệ. Căn cứ có thể là lệnh chuyển tiền được phép, khoản thu đã được chấp thuận hoặc điều chỉnh đã được phê duyệt.

**Invariant về phạm vi:** tài khoản nguồn, tài khoản đích, quyền ủy nhiệm và giao dịch liên quan phải được giải quyết trong đúng tenant và đúng miền tài sản. Nếu sản phẩm hỗ trợ chuyển xuyên tenant, cần một luồng riêng với chính sách và đối soát riêng; không bỏ kiểm tra tenant ở endpoint thông thường.

**Invariant về tiền tệ:** số tiền phải dương, có đơn vị biểu diễn rõ ràng và cùng loại tiền trong một lệnh chuyển nội bộ không có đổi ngoại tệ. Khi có phí hoặc đổi ngoại tệ, phí, tỷ giá và các tài khoản trung gian phải được mô hình hóa riêng.

**Invariant về số dư:** không được chi phần tiền đã giữ hoặc số tiền chưa được ghi nhận là khả dụng. Trong mô hình của bài:

~~~text
availableMinor = postedMinor - reservedMinor
postedMinor >= 0
reservedMinor >= 0
reservedMinor <= postedMinor
~~~

Đây là quy ước cho mô hình trả trước đang xét. Các tài khoản kế toán khác, tài khoản có thấu chi hoặc sản phẩm tín dụng cần invariant khác; không áp dụng máy móc điều kiện số dư không âm.

**Invariant về hiệu lực:** quyền và trạng thái phải hợp lệ tại điểm quyết định giao dịch theo quy tắc đồng thời đã định nghĩa. Một lần kiểm tra quyền trước khi bắt đầu transaction không đủ nếu quyền có thể bị thu hồi trong lúc xử lý.

**Invariant về số lần:** một lệnh nghiệp vụ được chấp nhận chỉ tạo ra biến động tiền một lần. Retry phải tham chiếu đúng lệnh cũ; đổi nội dung nhưng tái sử dụng khóa không được âm thầm coi là cùng lệnh.

**Invariant về truy vết:** phải truy được biến động số dư về giao dịch, actor, chủ sở hữu tại thời điểm liên quan và căn cứ quyền. Không thay đổi chủ sở hữu của tài khoản để hợp thức hóa một giao dịch vốn sai quyền.

## 4. Ranh giới tin cậy: client đề nghị hành động, server quyết định quyền

Client có thể gửi tài khoản nguồn, tài khoản đích và số tiền như một đề nghị. Những giá trị đó đều là dữ liệu không đáng tin cậy cho tới khi server kiểm tra.

| Dữ liệu | Nguồn có thể chấp nhận | Cách sử dụng |
|---|---|---|
| Danh tính actor | Ngữ cảnh xác thực đã được backend kiểm chứng | Tra cứu quyền và ghi audit |
| Tenant đang thao tác | Ngữ cảnh tenant đã kiểm tra quan hệ thành viên hoặc quyền dịch vụ | Giới hạn truy vấn và kiểm tra quan hệ đối tượng |
| `sourceAccountId` | Request | Tra cứu tài khoản và kiểm tra quyền ghi nợ |
| `destinationAccountId` | Request hoặc dữ liệu nghiệp vụ đã lưu | Kiểm tra khả năng nhận tiền, phạm vi và loại tiền |
| `ownerId`, `isAdmin`, `canDebit` trong body | Không có giá trị chứng minh quyền | Từ chối hoặc không cho xuất hiện trong DTO của lệnh |
| Số dư mới trong body | Không phải kết quả tính toán đáng tin cậy | Không dùng làm giá trị ghi đè số dư |
| Số tiền hoàn và bên nhận | Giao dịch gốc cùng chính sách hoàn | Đối chiếu quyền, số tiền còn có thể hoàn và đường tiền |

Ví dụ thiết kế nguy hiểm:

~~~java
// Ví dụ có lỗi: dữ liệu do client gửi đang quyết định chủ sở hữu và số dư.
account.setOwnerId(request.ownerId());
account.setPostedMinor(request.newBalanceMinor());
repository.save(account);
~~~

Một endpoint cập nhật hồ sơ tài khoản cũng không được dùng cơ chế ánh xạ toàn bộ JSON vào entity có các trường nhạy cảm như `ownerId`, `tenantId`, `postedMinor` hoặc `reservedMinor`. DTO cần chỉ chứa các trường được phép sửa, chẳng hạn tên hiển thị.

Với ví cá nhân mặc định, có thể để server tìm tài khoản nguồn từ danh tính đã xác thực thay vì nhận `sourceAccountId`. Cách này giảm diện tấn công nhưng không thay thế kiểm tra quyền: một người vẫn có thể có nhiều tài khoản, nhiều loại tiền hoặc nhiều vai trò tổ chức.

UUID khó đoán cũng không thay thế được kiểm tra quyền. ID có thể xuất hiện trong lịch sử giao dịch, log, liên kết chia sẻ hoặc dữ liệu từ một endpoint khác.

## 5. Mô hình quyền cho tài khoản cá nhân và tổ chức

### 5.1. Ví cá nhân

Một chính sách ghi nợ tối thiểu có dạng:

~~~text
actor đã được xác thực
AND tài khoản thuộc tenant mà actor được phép thao tác
AND tài khoản thuộc về actor
AND hành động được chính sách sản phẩm cho phép
AND tài khoản cho phép ghi nợ ở trạng thái hiện tại
AND giao dịch đáp ứng các điều kiện phê duyệt và hạn mức
~~~

Chỉ khớp `ownerId` chưa đủ. Tài khoản có thể bị khóa ghi nợ, giao dịch có thể vượt hạn mức hoặc cần xác nhận bổ sung. Chính chủ cũng không được bỏ qua những điều kiện này.

### 5.2. Tài khoản tổ chức

Với tài khoản tổ chức, quyền thường xuất phát từ quan hệ ủy nhiệm:

~~~text
SpendingGrant
  tenantId
  accountId
  actorId
  action
  status
  validFrom
  validUntil
  perTransactionLimitMinor
  version
~~~

Đây chỉ là mô hình minh họa. Nếu có hạn mức tích lũy theo ngày hoặc theo dự án, hệ thống còn cần dữ liệu tiêu dùng hạn mức và cơ chế cập nhật nguyên tử. Kiểm tra riêng `amount <= dailyLimit` không bảo vệ được hạn mức ngày khi nhiều giao dịch chạy đồng thời.

Phải kiểm tra thời gian hiệu lực theo nguồn thời gian của server. Không chấp nhận `approvedAt`, `grantValid` hoặc `remainingLimit` do client gửi làm bằng chứng.

Nếu quy trình yêu cầu người tạo khác người phê duyệt, cả hai danh tính và quyết định phê duyệt phải gắn với đúng nội dung lệnh. Thay tài khoản nguồn, số tiền hoặc người nhận sau khi phê duyệt phải làm mất hiệu lực phê duyệt cũ hoặc tạo một phiên bản lệnh mới cần được duyệt lại.

### 5.3. Tài khoản đích cũng có chính sách

Người gửi không cần sở hữu tài khoản đích trong dịch vụ chuyển tiền giữa người dùng. Tuy nhiên, backend vẫn phải kiểm tra tài khoản đó có được nhận tiền theo luồng hiện tại hay không: đúng loại tiền, đúng phạm vi, đúng loại tài khoản và đúng trạng thái nhận.

Trạng thái khóa ghi nợ có thể vẫn cho phép nhận tiền; trạng thái đóng tài khoản có thể không cho phép. Nên biểu diễn các quyền theo hành động như `canDebit` và `canReceive`, hoặc có chính sách tương đương, thay vì coi mọi trạng thái khác `ACTIVE` đều giống nhau.

Khi tra cứu người nhận, chỉ trả thông tin cần thiết để người gửi xác nhận. Quyền chuyển tiền đến tài khoản không tạo ra quyền xem số dư hoặc toàn bộ thông tin cá nhân của chủ tài khoản đó.

## 6. Thực thi quyền và cập nhật tiền trong cùng ranh giới nhất quán

### 6.1. Vấn đề của kiểm tra trước rồi ghi sau

Xét luồng sau:

~~~text
T1: đọc quyền của nhân viên → được phép chi
T2: quản trị viên thu hồi quyền → commit
T1: bắt đầu transaction cập nhật số dư → vẫn chi tiền
~~~

Hệ thống cần định nghĩa rõ giao dịch nào được xem là xảy ra trước. Nếu yêu cầu là “mọi giao dịch ghi nợ phải xếp trước hoặc sau việc thu hồi quyền một cách nhất quán”, việc ghi nợ và thu hồi phải cùng tham gia một cơ chế đồng bộ hóa, chẳng hạn khóa bản ghi quyền trong cùng transaction.

Nếu lệnh ghi nợ giữ khóa trước, việc thu hồi có thể phải chờ và lệnh được xử lý như xảy ra trước thu hồi. Nếu thu hồi có hiệu lực trước khi lệnh kiểm tra quyền trong ranh giới đó, lệnh phải bị từ chối. Không thể hứa rằng một cú nhấp thu hồi sẽ đảo ngược mọi giao dịch đã được chấp nhận trước đó.

Nếu quyền nằm ở một dịch vụ khác, transaction cơ sở dữ liệu cục bộ không tự giải quyết được vấn đề này. Cần một thiết kế quyền có phiên bản, sự chấp thuận được lưu bền vững hoặc giao thức điều phối phù hợp với độ trễ thu hồi đã công bố. Việc đưa kết quả kiểm tra từ xa vào một biến boolean không tạo ra tính nguyên tử.

### 6.2. Trình tự xử lý một lệnh chuyển nội bộ

Với hai tài khoản nằm trong cùng một cơ sở dữ liệu có transaction, một trình tự tham khảo là:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant P as Chính sách quyền
    participant D as Cơ sở dữ liệu
    C->>A: Lệnh chuyển + khóa idempotency
    A->>A: Xác thực actor, xác lập tenant
    A->>D: Bắt đầu transaction; nhận quyền xử lý khóa
    A->>D: Khóa tài khoản và dữ liệu quyền cần thiết
    A->>P: Kiểm tra quyền, trạng thái, phê duyệt, hạn mức
    P-->>A: Cho phép hoặc từ chối
    A->>D: Ghi biến động nguồn, đích, ledger và kết quả lệnh
    A->>D: Commit toàn bộ
    A-->>C: Kết quả lệnh đã commit
~~~

Các khóa idempotency, tài khoản và dữ liệu quyền phải tuân theo một thứ tự lấy khóa thống nhất giữa các luồng ghi. Khi khóa nhiều tài khoản, có thể sắp theo khóa định danh. Cách cụ thể tùy cơ sở dữ liệu; phải xác nhận rằng câu lệnh và cơ chế truy cập thực sự lấy khóa theo thứ tự mong muốn.

Không chỉ luồng chuyển tiền mới cần tuân thủ cơ chế này. Luồng thu hồi quyền, thay đổi trạng thái tài khoản, giữ tiền và cập nhật hạn mức cũng phải dùng ranh giới nhất quán tương thích, nếu chúng có thể làm thay đổi điều kiện chấp nhận lệnh.

### 6.3. Mã Java minh họa ranh giới nghiệp vụ

Đoạn mã sau là phác thảo thiết kế, không phải một lớp có thể sao chép để chạy ngay. Các thành phần transaction, repository, policy và idempotency phải được triển khai theo cùng hợp đồng nhất quán; tên phương thức không tự tạo ra tính an toàn.

~~~java
record TransferCommand(
        String sourceAccountId,
        String destinationAccountId,
        long amountMinor,
        String currency,
        String idempotencyKey) {}

TransferResult transfer(AuthContext auth, TransferCommand command) {
    if (command.amountMinor() <= 0) {
        throw new InvalidAmount();
    }
    if (command.sourceAccountId()
            .equals(command.destinationAccountId())) {
        throw new InvalidTransfer();
    }

    // auth do backend tạo từ danh tính và tenant đã được xác minh.
    // Fingerprint được tạo từ biểu diễn chuẩn hóa, gồm mọi trường
    // ảnh hưởng đến lệnh; không hash JSON thô tùy thứ tự trường.
    var scope = new CommandScope(
            auth.tenantId(), auth.actorId(), "INTERNAL_TRANSFER");
    var fingerprint = fingerprints.ofCanonicalTransfer(command);

    return transactions.execute(() -> {
        // Nhận quyền xử lý bằng ràng buộc unique trong DB.
        // Cùng scope/key nhưng fingerprint khác phải bị từ chối.
        var claim = idempotency.claimOrLoad(
                scope, command.idempotencyKey(), fingerprint);

        if (claim.completed()) {
            // Không thực hiện lại biến động tiền. Việc đọc kết quả
            // vẫn phải tuân theo chính sách truy cập hiện tại.
            resultAccess.requireCanRead(auth, claim.resultReference());
            return claim.savedResult();
        }

        var accounts = accountRepository.lockBothInStableOrder(
                auth.tenantId(),
                command.sourceAccountId(),
                command.destinationAccountId());

        var source = accounts.require(command.sourceAccountId());
        var destination = accounts.require(command.destinationAccountId());

        // Cùng tham gia giao thức khóa với luồng thu hồi quyền,
        // sửa quyền, sửa hạn mức và phê duyệt.
        var authority = authorityRepository.lockForDebit(auth, source);
        var approval = approvals.lockIfRequired(auth, command);

        debitPolicy.requireAllowed(auth, source, authority, approval, command);
        creditPolicy.requireAllowed(auth, destination, command);
        moneyPolicy.requireSameCurrency(source, destination, command.currency());

        long available = Math.subtractExact(
                source.postedMinor(), source.reservedMinor());
        if (available < command.amountMinor()) {
            throw new InsufficientFunds();
        }

        long sourceAfter = Math.subtractExact(
                source.postedMinor(), command.amountMinor());
        long destinationAfter = Math.addExact(
                destination.postedMinor(), command.amountMinor());

        // Kiểm tra cả hạn mức tích lũy trong transaction này.
        limits.consumeIfAllowed(auth, source, command);
        approvals.consumeIfRequired(approval, command);

        var transferId = transferIds.next();
        accountRepository.updatePosted(source, sourceAfter);
        accountRepository.updatePosted(destination, destinationAfter);
        ledger.appendTransfer(transferId, auth, source, destination, command);

        var result = TransferResult.accepted(transferId);
        idempotency.complete(claim, result);
        outbox.recordTransferCommitted(transferId);
        return result;
    });
}
~~~

Các điểm cần đọc từ ví dụ:

- Không có `ownerId`, `newBalance` hay `approved` do client truyền vào để quyết định quyền.
- Quyền chi tiêu có thể dựa trên sở hữu hoặc ủy nhiệm, nhưng luôn gắn với tài khoản nguồn cụ thể.
- Trạng thái, tiền khả dụng, hạn mức và phê duyệt được kiểm tra trong ranh giới nhất quán với cập nhật.
- `Math.addExact` và `Math.subtractExact` giúp phát hiện tràn số nguyên trong tính toán minh họa. Lỗi phải làm rollback; vẫn cần giới hạn nghiệp vụ và kiểu dữ liệu cơ sở dữ liệu phù hợp.
- Bút toán, số dư, hạn mức đã dùng, phê duyệt đã tiêu thụ, kết quả idempotency và bản ghi outbox cùng commit hoặc cùng rollback trong mô hình này.

Nếu dùng số thập phân, phải quy định độ chính xác và quy tắc làm tròn theo từng nghiệp vụ. Không dùng `double` để biểu diễn tiền cần tính toán chính xác. Việc dùng số nguyên cũng chỉ đúng khi mọi bên thống nhất đơn vị và quy tắc chuyển đổi.

Trong Java, ranh giới transaction thực tế phụ thuộc cách cấu hình framework và gọi phương thức. Một chú thích transaction hoặc tên hàm `execute` không thay thế việc kiểm chứng rằng toàn bộ thao tác trên thực sự dùng cùng transaction và rollback đúng khi lỗi xảy ra.

### 6.4. SQL có điều kiện là một lớp bảo vệ bổ sung

Ví dụ sau minh họa cập nhật một tài khoản trả trước sau khi đã kiểm tra số tiền dương, phạm vi giá trị, quyền, loại tiền và các điều kiện nghiệp vụ trong transaction:

~~~sql
UPDATE balance_account
SET posted_minor = posted_minor - :amount_minor,
    version = version + 1
WHERE id = :source_account_id
  AND tenant_id = :tenant_id
  AND currency = :currency
  AND debit_enabled = TRUE
  AND posted_minor - reserved_minor >= :amount_minor;
~~~

Phải kiểm tra số dòng cập nhật chính xác là một. Nếu bằng không, không được tiếp tục ghi có cho bên nhận. Không trả lại thông tin quá chi tiết khiến người không có quyền suy ra số dư hoặc trạng thái của tài khoản người khác.

Câu lệnh này không chứa toàn bộ logic quyền sở hữu hay ủy nhiệm. Nó không đủ để trở thành một endpoint chuyển tiền an toàn. Tài khoản đích, hạn mức, ledger và các bản ghi liên quan vẫn phải được xử lý nguyên tử; các đường ghi khác cũng phải bảo vệ cùng invariant.

Có thể dùng khóa bi quan, cập nhật có điều kiện, kiểm tra phiên bản hoặc mức cô lập phù hợp. Chọn phương án theo invariant và cơ chế của cơ sở dữ liệu; khi xung đột cần retry có giới hạn và giữ nguyên danh tính lệnh nghiệp vụ.

## 7. Ledger giúp chứng minh tiền đã đi theo quyền nào

Nếu chỉ có cột `balance`, rất khó giải thích vì sao số dư thay đổi. Ledger lưu các biến động có căn cứ, giúp đối soát và phát hiện sai lệch.

Trong ví dụ chuyển nội bộ không phí, dùng quy ước **delta số dư của người dùng**:

| Giao dịch | Tài khoản | Delta | Căn cứ |
|---|---|---:|---|
| `tx-001` | Ví nguồn | `-300000 VND` | Lệnh chuyển đã kiểm tra quyền |
| `tx-001` | Ví đích | `+300000 VND` | Bên nhận của cùng lệnh |

Tổng delta bằng không trong phạm vi chuyển nội bộ này. Đây là cách minh họa biến động số dư, không phải định nghĩa đầy đủ của hệ thống kế toán kép. Trong kế toán kép, ý nghĩa tăng giảm của debit và credit phụ thuộc loại tài khoản; không đồng nhất mọi debit với dấu âm.

Mỗi giao dịch nên truy được ít nhất:

~~~text
transactionId
businessOperationType
businessReference
actorId
actorType
tenantId
sourceAccountId
destinationAccountId
amountMinor
currency
authorizationReference
approvalReference (nếu cần)
idempotencyRecordId
committedAt
~~~

Thông tin chủ sở hữu có thể được lưu bằng snapshot hoặc tham chiếu lịch sử có phiên bản. Chỉ join sang `ownerId` hiện tại sẽ làm mất ngữ cảnh nếu quan hệ sở hữu thay đổi hợp lệ về sau. Không đưa token truy cập, bí mật ký hoặc thông tin thanh toán nhạy cảm không cần thiết vào audit.

Khi phát hiện giao dịch sai, dùng nghiệp vụ điều chỉnh hoặc bút toán đảo có quyền riêng và liên kết giao dịch gốc. Không xóa lịch sử hoặc sửa trực tiếp số dư để làm ledger trông khớp. Bản thân luồng sửa sai cũng phải bảo vệ quyền, hạn mức, phê duyệt và chống thực thi trùng.

## 8. Các đường vòng thường làm mất quyền sở hữu số dư

### 8.1. Giữ tiền, thu tiền và giải phóng tiền giữ

Giữ tiền làm giảm tiền khả dụng dù chưa làm giảm `postedMinor`. Vì vậy, tạo hold trên tài khoản người khác cũng là một hình thức tác động trái phép đến số dư.

Trong mô hình đơn giản:

~~~text
Giữ tiền x:
  reserved' = reserved + x
  posted'   = posted

Thu đủ khoản giữ x:
  reserved' = reserved - x
  posted'   = posted - x

Giải phóng khoản giữ x:
  reserved' = reserved - x
  posted'   = posted
~~~

Các bước trên phải gắn với cùng một hold hợp lệ và được cập nhật nguyên tử. Một hold cần ràng buộc với tài khoản, tenant, loại tiền, số tiền còn lại, trạng thái và nghiệp vụ gốc. Không cho client thay `accountId` khi capture hoặc release.

Ví dụ state machine tối giản, chưa xét thu từng phần:

~~~mermaid
stateDiagram-v2
    [*] --> HELD: Giữ tiền được phép
    HELD --> CAPTURED: Thu đúng khoản đã giữ
    HELD --> RELEASED: Giải phóng theo chính sách
    HELD --> EXPIRED: Hết hạn và giải phóng
    CAPTURED --> [*]
    RELEASED --> [*]
    EXPIRED --> [*]
~~~

Không được capture sau release hoặc release hai lần. Nếu hỗ trợ capture từng phần, phải lưu phần còn có thể thu hoặc giải phóng và kiểm tra tổng số tiền qua mọi request, kể cả các request đồng thời. State machine của hold phối hợp với quyền sở hữu; nó không thay thế kiểm tra quyền.

### 8.2. Hoàn tiền về sai chủ thể

Một endpoint nhận cả `paymentId` và `refundAccountId` tùy ý có thể biến quyền yêu cầu hoàn thành quyền chuyển tiền cho chính mình.

Quy tắc nên là: bên nhận được xác định từ giao dịch gốc và chính sách hoàn đã được kiểm soát. Nếu chính sách cho phép đổi nơi nhận, đó phải là một quy trình riêng có xác minh và phê duyệt phù hợp.

Phải kiểm tra đồng thời:

- Actor có quyền yêu cầu hoặc phê duyệt hoàn cho giao dịch gốc.
- Giao dịch gốc thuộc đúng tenant và trạng thái cho phép hoàn.
- Tổng tiền đã hoàn, đang hoàn và lần hoàn mới không vượt phần còn có thể hoàn, theo mô hình trạng thái của sản phẩm.
- Bên nhận khớp với đường tiền được chính sách cho phép.
- Việc gửi lại không tạo thêm một lần hoàn.

Người mua hiện tại của một đơn hàng, người tạo ticket hỗ trợ hoặc người sở hữu tài khoản sau khi chuyển giao không tự động trở thành người được nhận tiền của thanh toán trước đó. Quyền đối với giao dịch phải được suy từ dữ liệu nghiệp vụ có lịch sử, không chỉ từ quan hệ hiện tại.

### 8.3. Nạp tiền qua webhook

Webhook đã xác thực chữ ký vẫn cần được ánh xạ đến giao dịch nạp do server ghi nhận. Backend phải kiểm tra nhà cung cấp, tài khoản merchant hoặc tenant liên quan, mã giao dịch, số tiền, loại tiền và trạng thái phù hợp.

Không ghi có vào `walletId` tùy ý chỉ vì trường đó có mặt trong metadata của callback. Metadata có thể bắt nguồn từ dữ liệu do người dùng gửi ở bước tạo thanh toán. Chữ ký chứng minh nguồn thông điệp theo cơ chế nhà cung cấp; không tự chứng minh rằng mọi quan hệ nghiệp vụ trong thông điệp là hợp lệ.

Cần chống xử lý trùng cả theo định danh sự kiện phù hợp lẫn giao dịch thanh toán nghiệp vụ. Một lần thanh toán có thể liên quan nhiều thông báo. Việc ghi nhận callback và ghi có phải không cho phép cùng khoản thanh toán được cộng tiền nhiều lần.

### 8.4. Đổi chủ sở hữu hoặc sửa số dư qua endpoint quản trị

Không xem `ownerId` là một trường hồ sơ thông thường. Nếu sản phẩm hỗ trợ chuyển quyền sở hữu tài khoản, cần xác định rõ điều kiện về số dư, khoản giữ, giao dịch đang chờ, quyền cũ, quyền mới và lịch sử trách nhiệm.

Trong nhiều sản phẩm, chuyển tiền sang một tài khoản mới rồi đóng tài khoản cũ dễ giữ lịch sử rõ ràng hơn việc thay chủ trên cùng ID. Đây là lựa chọn thiết kế, không phải quy tắc bắt buộc cho mọi hệ thống.

Tài khoản dịch vụ dùng cho sửa sai hoặc quyết toán cũng không nên có quyền ghi nợ mọi tài khoản cho mọi mục đích. Giới hạn theo loại nghiệp vụ và tham chiếu bắt buộc giúp tránh biến một credential bị lộ thành khả năng tùy ý chuyển tiền.

## 9. Idempotency phải gắn với đúng người và đúng lệnh

Giả sử cùng một lệnh chuyển được gửi ba lần vì timeout. Kết quả mong muốn là một biến động tiền và những lần trả kết quả hoặc tiếp tục tra cứu cho cùng lệnh, theo trạng thái xử lý đã xác định.

Một mô hình khóa có thể là:

~~~text
unique(tenantId, actorId, operationType, idempotencyKey)
~~~

Đây là lựa chọn minh họa. Một hệ thống khác có thể dùng phạm vi rộng hơn, nhưng phải chủ động ngăn xung đột giữa người dùng và rò rỉ kết quả lệnh của người khác.

Bản ghi cần lưu fingerprint của các trường ảnh hưởng tới lệnh, ví dụ tài khoản nguồn, tài khoản đích, số tiền, loại tiền và tham chiếu phê duyệt. Với luồng có phí hoặc tỷ giá, phải gắn cả báo giá hoặc phiên bản giá có hiệu lực. Cần chuẩn hóa dữ liệu trước khi tạo fingerprint.

| Tình huống | Hành vi mong muốn |
|---|---|
| Cùng phạm vi, cùng khóa, cùng nội dung, lệnh đã commit | Trả lại kết quả phù hợp với quyền đọc; không chuyển tiền lần nữa |
| Cùng phạm vi, cùng khóa, khác nội dung | Báo xung đột lệnh; không âm thầm dùng kết quả cũ |
| Cùng khóa do người khác dùng | Không đọc được hoặc chiếm kết quả ngoài phạm vi quyền |
| Hai request đồng thời dùng cùng khóa | Một bên xử lý lệnh; bên còn lại chờ hoặc nhận trạng thái có kiểm soát |
| Client timeout sau commit | Retry truy được giao dịch đã commit thay vì ghi nợ thêm |
| Transaction lỗi trước commit | Không còn biến động tiền dở dang; trạng thái khóa cho phép xử lý theo chính sách retry |

Idempotency không phải bằng chứng sở hữu. Lệnh đầu tiên luôn phải được kiểm tra quyền đầy đủ. Trả lại kết quả của lệnh cũ không có nghĩa là thực hiện một lệnh ghi nợ mới, nhưng quyền đọc kết quả vẫn cần được bảo vệ.

Dùng một khóa mới cho cùng ý định nghiệp vụ có thể vượt qua lớp idempotency của request. Với thao tác chỉ được xảy ra một lần, như capture một hold toàn phần hoặc xử lý một khoản nạp, còn cần ràng buộc duy nhất và state machine theo tham chiếu nghiệp vụ. Thời hạn lưu khóa cũng phải phù hợp với cửa sổ retry và đối soát.

## 10. Khi tiền đi qua hệ thống bên ngoài

Transaction của cơ sở dữ liệu không bao trùm một API ngân hàng hoặc cổng thanh toán chỉ vì lời gọi HTTP được đặt bên trong hàm transaction.

Một luồng rút tiền thường cần:

1. Kiểm tra quyền và giữ hoặc ghi nhận tiền đang chờ theo mô hình sản phẩm.
2. Lưu lệnh rút và sự kiện cần gửi trong cùng transaction cục bộ.
3. Gửi lệnh ra ngoài qua tiến trình có khả năng retry và định danh lệnh ổn định.
4. Xác nhận hoặc xử lý thất bại theo trạng thái có căn cứ từ nhà cung cấp và đối soát.

Timeout không chứng minh rằng nhà cung cấp chưa trả tiền. Giải phóng khoản giữ ngay sau timeout có thể cho phép người dùng tiêu lại tiền trong khi khoản rút đã thành công ở bên ngoài. Trạng thái chưa rõ kết quả cần được xử lý như một trạng thái nghiệp vụ riêng.

Outbox hỗ trợ lưu bền vững ý định phát sự kiện cùng transaction. Nó không tự bảo đảm hệ thống ngoài xử lý đúng một lần. Bên gửi, bên nhận và quy trình đối soát vẫn cần chống trùng phù hợp.

Trong mọi trạng thái chờ, quyền sở hữu phải được giữ nguyên: không thay người nhận hoặc tài khoản nguồn của lệnh đã được chấp thuận chỉ vì người gọi sửa request retry.

## 11. Kiểm thử bằng tình huống lạm dụng logic

Không chỉ kiểm thử phản hồi HTTP. Cần kiểm tra số dư, khoản giữ, ledger, hạn mức đã dùng, trạng thái phê duyệt và bản ghi lệnh sau khi chạy. Với request bị từ chối, dấu vết từ chối trong audit có thể được tạo, nhưng không được có biến động tiền hoặc tiêu thụ hạn mức trái phép.

Giả sử các bài kiểm thử độc lập bắt đầu với:

~~~text
Tenant A:
  An sở hữu wallet-an:     posted = 1.000.000, reserved = 200.000 VND
  Bình sở hữu wallet-binh: posted =   500.000, reserved =       0 VND
  Cả hai tài khoản cho phép gửi và nhận tiền.
Tenant B:
  Có một tài khoản không thuộc phạm vi thao tác của An.
~~~

| Tình huống kiểm thử | Kết quả cần chứng minh |
|---|---|
| An chuyển 300.000 từ ví mình sang Bình | `wallet-an`: posted 700.000, reserved 200.000, khả dụng 500.000; `wallet-binh`: posted 800.000; có một giao dịch tương ứng |
| An đổi tài khoản nguồn thành ví Bình | Bị từ chối; cả hai số dư và ledger tiền không đổi |
| An gửi `ownerId` của Bình hoặc `canDebit=true` | Không thể tạo quyền; các trường đó không được sử dụng để cấp quyền |
| An lấy ID tài khoản của tenant B | Bị từ chối và không lộ dữ liệu tài khoản ngoài phạm vi |
| Actor chỉ có quyền xem ví tổ chức | Xem được theo chính sách nhưng không được giữ hoặc trừ tiền |
| Nhân viên có quyền chi tối đa 100.000 gửi 100.001 | Bị từ chối; hạn mức đã dùng không tăng |
| An chuyển 900.000 từ ví mình | Bị từ chối vì chỉ có 800.000 khả dụng |
| Hai lệnh khác khóa cùng chuyển 600.000 từ ví An | Chỉ một lệnh có thể thành công; tiền khả dụng không âm |
| Hai request cùng khóa, cùng nội dung | Chỉ có một lần ghi nợ và một lần ghi có |
| Cùng khóa nhưng đổi bên nhận hoặc số tiền | Báo xung đột; không tạo biến động mới |
| Quyền chi tiêu bị thu hồi đồng thời | Kết quả tuân theo thứ tự hiệu lực đã định nghĩa; không dựa vào một quyền cũ đọc ngoài ranh giới nhất quán |
| Số tiền bằng không, âm, sai loại tiền hoặc vượt phạm vi kiểu dữ liệu | Bị từ chối; không có cập nhật một phần |
| Lỗi khi ghi có sau khi đã thực hiện câu lệnh ghi nợ | Toàn bộ transaction rollback, kể cả ledger và hạn mức |
| Client timeout sau khi transaction đã commit rồi retry | Truy được lệnh cũ; không chuyển tiền thêm |
| Capture bằng hold của người khác hoặc hold đã release | Bị từ chối; không làm thay đổi tiền |
| Hoàn tiền nhưng đổi nơi nhận sang ví của người gọi | Bị từ chối nếu không có quy trình cho phép tương ứng |
| Hai lệnh hoàn đồng thời vượt tổng tiền còn được hoàn | Chỉ phần hợp lệ được chấp nhận; không hoàn vượt giao dịch gốc |
| Callback nạp bị phát lại hoặc thay metadata ví nhận | Không cộng tiền trùng hoặc cộng sang ví ngoài giao dịch đã lưu |
| Sửa hồ sơ tài khoản kèm `postedMinor` hoặc `ownerId` | Không làm thay đổi số dư hoặc chủ sở hữu |
| Tài khoản nguồn bằng tài khoản đích | Bị từ chối theo chính sách của lệnh chuyển minh họa |

Kiểm thử đồng thời cần điều khiển thời điểm các request gặp nhau bằng barrier hoặc latch trong môi trường kiểm thử phù hợp. Chạy hai request nối tiếp hoặc thêm độ trễ tùy ý không đủ chứng minh việc bảo vệ race condition.

Ngoài ví dụ cụ thể, có thể kiểm tra các tính chất sau sau mọi chuỗi lệnh được sinh trong phạm vi mô hình:

~~~text
Không có bút toán ghi nợ thành công thiếu căn cứ quyền.
Không có tài khoản trả trước nào có reserved > posted hoặc available < 0.
Tổng delta của một chuyển nội bộ không phí, cùng loại tiền, bằng 0.
Một lệnh nghiệp vụ đã hoàn tất không tạo thêm biến động khi bị retry.
Mọi biến động số dư đều truy về được giao dịch và căn cứ nghiệp vụ.
~~~

Các tính chất phải được đặt trong đúng phạm vi. Không cộng trực tiếp các loại tiền khác nhau, và không dùng quy tắc bảo toàn hai ví cho một nghiệp vụ có phí nhưng chưa đưa tài khoản phí vào phép kiểm tra.

## 12. Một cách rà soát luồng tiền từ đầu đến cuối

Khi đọc một endpoint hoặc một consumer có thể thay đổi tiền, lần theo chuỗi:

~~~text
Danh tính đã xác thực
    → tenant và quan hệ tài khoản
    → căn cứ sở hữu hoặc ủy nhiệm
    → quyền theo hành động
    → trạng thái, phê duyệt và hạn mức
    → kiểm tra tiền khả dụng
    → cập nhật nguyên tử và chống trùng
    → ledger, kết quả lệnh và đối soát
~~~

Tại mỗi mũi tên, xác định dữ liệu nào do server chứng minh và dữ liệu nào chỉ là đề nghị của client. Sau đó xác định điều gì có thể thay đổi giữa lúc đọc và lúc commit, và luồng ghi nào đang bảo vệ thay đổi đó.

Một thiết kế bảo vệ tốt balance ownership cho phép giải thích từng biến động tiền bằng một câu cụ thể: **actor nào, được ai hoặc chính sách nào cho phép, thực hiện hành động gì, trên tiền của chủ thể nào, trong giao dịch nào và với số lần bao nhiêu**. Nếu chỉ trả lời được “request đã đăng nhập” hoặc “tài khoản tồn tại”, invariant về quyền sở hữu vẫn còn thiếu.
