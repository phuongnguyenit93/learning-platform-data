# Revocation của delegated access

## 1. Thu hồi quyền được ủy nghĩa là gì?

Revocation của delegated access là việc chấm dứt hiệu lực của một ủy quyền hoặc một phần phạm vi đã trao, để ủy quyền đó không còn được dùng làm căn cứ cho các hành động tiếp theo.

Ví dụ, Lan là chủ sở hữu báo cáo và ủy quyền cho Minh đọc trong một tuần. Sau hai ngày, Lan quyết định dừng chia sẻ. Grant chưa hết hạn nhưng hệ thống phải ngăn các yêu cầu sử dụng grant đó theo thời điểm và phạm vi thu hồi đã cam kết.

Trong IAM, thao tác “thu hồi” liên quan đến nhiều lớp:

- Bản ghi ủy quyền trong kho dữ liệu.
- Quan hệ phát sinh trong đồ thị ReBAC.
- Quyết định cấp quyền được cache.
- Token, phiên hoặc đường tải dữ liệu đã phát hành.
- Job nền và yêu cầu đang chạy.
- Điểm thực thi quyền tại API, dịch vụ và kho dữ liệu.

Thay một field thành REVOKED chỉ là một phần của giải pháp. Mục tiêu cần kiểm chứng là ủy quyền đã mất hiệu lực trên đúng đường thực thi, đúng các thao tác và trong khoảng thời gian mà hệ thống công bố.

Thu hồi quyền không xóa được nội dung đã được tải hợp lệ trước đó, không tự hoàn tác giao dịch đã hoàn tất và không mặc nhiên xóa mọi quyền khác của người nhận.

Bài học dùng mô hình minh họa với grant có định danh, grant cha và nguồn thẩm quyền. Các tên trạng thái, API, revision và mã Java trong bài là lựa chọn thiết kế của ứng dụng, không phải một giao thức revocation chung cho mọi engine ReBAC.

## 2. Ví dụ xuyên suốt: một tài liệu có nhiều đường cấp quyền

Trong tenant acme, Lan là owner của document:report-42. Hệ thống có các grant:

~~~text
dg-101: Lan  -> Minh
        tài nguyên: report-42
        hành động: read, comment
        cho phép ủy quyền tiếp

dg-102: Minh -> An
        tài nguyên: report-42
        hành động: read
        parentGrantId: dg-101

dg-103: Lan  -> An
        tài nguyên: report-42
        hành động: read
        grant trực tiếp, độc lập với dg-101
~~~

Sơ đồ nguồn quyền:

~~~mermaid
flowchart LR
    L["Lan: owner"] --> G1["dg-101: read, comment"]
    G1 --> M["Minh"]
    G1 --> G2["dg-102: read; phụ thuộc dg-101"]
    G2 --> A["An"]
    L --> G3["dg-103: read; độc lập"]
    G3 --> A
~~~

Nếu Lan thu hồi dg-101:

- Minh mất đường quyền do dg-101 tạo ra.
- An không còn dùng dg-102 nếu grant con phải phụ thuộc grant cha.
- An vẫn có thể đọc qua dg-103, nếu grant đó còn hợp lệ.
- Không được xóa dg-103 chỉ vì nó có cùng người nhận hoặc cùng tài nguyên.

Kết quả “An vẫn đọc được” chưa đủ để kết luận revocation thất bại. Cần xác định An đang dùng nguồn quyền nào. Ngược lại, dg-101 đã được đánh dấu thu hồi cũng chưa đủ để kết luận mọi đường thực thi đã chặn nó.

Điều này cho thấy hai yêu cầu khác nhau:

~~~text
Yêu cầu A: Thu hồi nguồn cấp dg-101 và các quyền phụ thuộc nó.
Yêu cầu B: Chặn An truy cập report-42 bất kể quyền đến từ nguồn nào.
~~~

Yêu cầu B có thể cần thu hồi nhiều nguồn hoặc dùng một policy hạn chế riêng. Không được âm thầm thực hiện yêu cầu B khi người quản trị chỉ chọn A.

## 3. Phân biệt revocation với các thay đổi gần giống

| Thay đổi | Ngữ nghĩa chính | Điều không được tự suy ra |
|---|---|---|
| Revoked | Grant bị chấm dứt theo hành động thu hồi | Không tự hoạt động trở lại khi căn cứ cũ xuất hiện |
| Expired | Đã qua thời hạn áp dụng | Không cần chờ job dọn dữ liệu mới mất hiệu lực |
| Suspended | Tạm không đáp ứng điều kiện | Chỉ khôi phục nếu policy cho phép |
| Thu hẹp phạm vi | Một số action hoặc tài nguyên không còn được cấp | Không có nghĩa mọi quyền trong grant đều mất |
| Gỡ quan hệ nền | Nguồn thẩm quyền hoặc membership bị thay đổi | Tác động phụ thuộc mô hình grant |
| Xóa dữ liệu grant | Bản ghi bị xóa khỏi kho | Chưa chứng minh cache, token và quyền vật chất hóa đã mất hiệu lực |

Trong mô hình của bài, REVOKED là trạng thái cuối của một grant. Nếu muốn cấp lại, hệ thống tạo grant mới có định danh và lịch sử mới. Cách này giúp phân biệt “cấp lại có chủ đích” với “dữ liệu cũ sống lại vì đồng bộ sai thứ tự”.

Một sản phẩm có thể hỗ trợ khôi phục grant đã thu hồi, nhưng khi đó phải coi khôi phục là hành động cấp quyền cần phân quyền và kiểm toán lại. Không biến nó thành tác dụng phụ của việc khôi phục bản sao cơ sở dữ liệu.

Nếu chỉ muốn bỏ comment nhưng giữ read, có thể tạo phiên bản phạm vi mới hoặc thay grant cũ bằng grant mới. Dù chọn cách nào, quyết định cũ cấp comment phải mất hiệu lực theo hợp đồng độ mới tương ứng.

## 4. Hiệu lực theo chuỗi: điều kiện AND và các đường quyền OR

Một grant con chỉ có thể làm căn cứ khi toàn bộ các phụ thuộc bắt buộc của nó còn hợp lệ.

Với dg-102:

~~~text
ValidPath(dg-102)
  = dg-102 còn hiệu lực
    AND dg-101 còn hiệu lực
    AND quan hệ cha–con hợp lệ
    AND nguồn thẩm quyền gốc còn đáp ứng policy
    AND điều kiện toàn cục cho phép yêu cầu
~~~

Đây là điều kiện AND trong một đường quyền. Thu hồi một mắt xích bắt buộc làm đường đó mất hiệu lực.

Nếu An có nhiều đường độc lập:

~~~text
CanRead(An, report-42)
  = GlobalControlsAllow(An, report-42)
    AND (
      ValidPath(dg-102)
      OR ValidPath(dg-103)
      OR OtherRecognizedReadAuthority(An, report-42)
    )
~~~

Đây là mô hình kết hợp của ứng dụng minh họa. Những hệ thống có policy deny, quan hệ loại trừ hoặc quy tắc ưu tiên khác phải áp dụng đúng ngữ nghĩa đã định nghĩa; không mặc định mọi ReBAC đều chỉ là phép OR của cạnh cho phép.

Một lỗi thiết kế thường gặp là vật chất hóa dg-102 thành một cạnh reader trực tiếp rồi quên rằng cạnh đó phụ thuộc dg-101. Khi cha bị thu hồi, cạnh reader vẫn còn và trở thành nguồn quyền độc lập ngoài ý muốn.

Cần giữ được provenance — nguồn gốc quyền — bằng grantId, parentGrantId hoặc chỉ mục phụ thuộc phù hợp. Nếu không biết một cạnh reader được tạo từ nguồn nào, rất khó thu hồi chính xác mà không xóa nhầm nguồn quyền khác.

## 5. Chọn hợp đồng thời gian trước khi chọn cách triển khai

“Thu hồi ngay” là một mô tả chưa đủ rõ cho hệ thống phân tán. Cần xác định ngay đối với điều gì và bắt đầu từ mốc nào.

Các mốc minh họa:

~~~text
t_request : server nhận yêu cầu thu hồi
t_commit  : trạng thái thu hồi được ghi bền vững
t_ack     : API trả phản hồi cho người yêu cầu
t_visible : một PEP cụ thể đã nhìn thấy trạng thái đủ mới
t_effect  : thao tác thuộc phạm vi cam kết không còn được chấp nhận
~~~

Các mốc này có thể không trùng nhau. API trả sau t_commit không tự chứng minh mọi PEP đã qua t_visible.

Có thể chọn một trong các hợp đồng, tùy nhu cầu sản phẩm:

| Hợp đồng minh họa | Điều API xác nhận | Cơ chế cần có |
|---|---|---|
| Ghi thu hồi thành công | Trạng thái đã commit; việc lan truyền còn có thể đang diễn ra | Bản ghi bền vững, theo dõi lan truyền |
| Có hiệu lực trong giới hạn thời gian | Các đường truy cập trong phạm vi bị chặn trước một hạn đã định nghĩa | Giới hạn độ cũ và đo lường đáp ứng |
| Đọc quyền sau thu hồi phải phản ánh thay đổi | Các kiểm tra sau mốc cam kết không được dùng snapshot trước thay đổi | Revision, rào chắn hoặc giao thức nhất quán phù hợp |
| Hủy cả công việc đang chạy | Một số thao tác đang xử lý cũng phải dừng | Cơ chế hủy và kiểm tra sát thời điểm tác động |

Mã Java trong bài chỉ xác nhận việc ghi thu hồi bền vững cùng sự kiện cần phát. Nó chưa tự tạo ra cam kết hủy mọi yêu cầu đang chạy.

Không cộng cơ học TTL, độ trễ bản sao và thời gian sống token để tuyên bố một giới hạn chung. Có hệ thống dùng các cơ chế song song, có hệ thống dùng chúng nối tiếp, và có đường đi bỏ qua hoàn toàn kho grant. Phải lập đường truy cập thực tế rồi xác định giới hạn của từng đường.

Cam kết cũng cần nêu cách xử lý khi phụ thuộc lỗi. Nếu không đọc được trạng thái đủ mới, PEP có thể phải chặn hoặc trì hoãn thao tác. Tiếp tục dùng một Permit cũ vô hạn khiến cam kết thu hồi mất ý nghĩa.

## 6. Dữ liệu cần giữ để thu hồi chính xác

Một bản ghi grant minh họa:

~~~json
{
  "id": "dg-101",
  "tenantId": "acme",
  "resource": "document:report-42",
  "grantor": "user:lan",
  "grantee": "user:minh",
  "actions": ["document:read", "document:comment"],
  "parentGrantId": null,
  "authorityBasis": "CURRENT_OWNER",
  "status": "REVOKED",
  "version": 8,
  "revokedAt": "2026-11-26T03:15:00Z",
  "revokedBy": "user:lan",
  "revocationReasonCode": "SHARING_ENDED",
  "authorizationEpoch": 51
}
~~~

version giúp phân biệt các lần thay đổi của chính grant. authorizationEpoch là một bộ đếm của phạm vi tài nguyên trong ví dụ, dùng để ràng buộc độ mới khi các grant liên quan thay đổi. Hai trường này không có cùng ý nghĩa.

Để epoch có tác dụng, mọi thay đổi quyền thuộc phạm vi được bảo vệ phải cập nhật nó, và PEP phải biết giá trị tối thiểu cần tôn trọng từ một nguồn đáng tin cậy. Nếu PEP đọc cả grant lẫn epoch từ cùng bản cache cũ, thêm field epoch không giải quyết được việc không biết có thu hồi mới.

Các thông tin thường hữu ích:

- Định danh grant ổn định, không tái sử dụng cho một lần cấp mới.
- Parent và nguồn thẩm quyền để xác định phụ thuộc.
- Version để xử lý cạnh tranh và sự kiện trễ.
- Người thu hồi, thời điểm và mã lý do để kiểm toán.
- Revision hoặc dấu mốc đồng bộ theo hợp đồng kho quyền.
- Định danh sự kiện để xử lý trùng lặp.

Không cần chép access token hoặc toàn bộ dữ liệu tài liệu vào bản ghi revocation. Mã lý do có kiểm soát thường dễ bảo vệ và xử lý hơn một ô văn bản tùy ý chứa thông tin cá nhân.

Xóa cứng grant ngay sau thu hồi có thể làm mất bằng chứng hoặc khiến sự kiện đến trễ không biết trạng thái mới nhất. Có thể giữ một bản ghi đánh dấu đã thu hồi trong thời hạn phù hợp, rồi dọn dữ liệu theo chính sách lưu trữ riêng.

## 7. Ai được phép thu hồi?

Quyền thu hồi là một thao tác quản trị quyền. Nó cũng cần được phân quyền.

Một policy minh họa cho phép:

- Grantor thu hồi grant mình đã cấp khi còn đủ thẩm quyền theo chính sách.
- Owner hiện hành quản lý các grant trong phạm vi tài liệu.
- Người nhận từ bỏ quyền được cấp cho chính mình.
- Quản trị viên được ủy quyền quản lý đúng tenant và phạm vi.
- Dịch vụ vòng đời thu hồi khi một nhiệm vụ hoặc hợp đồng chấm dứt.

Không mặc định những lựa chọn trên đều bắt buộc cho mọi sản phẩm. Chẳng hạn, quyền tự thu hồi của grantor sau khi rời tổ chức cần được xác định rõ; có thể hệ thống chỉ cho owner hoặc quản trị viên hiện hành xử lý.

API cần định vị grant bằng tenant, tài nguyên và grantId đã được kiểm chứng. Biết grantId không đồng nghĩa được phép sửa grant.

Ngay cả với yêu cầu idempotent, server vẫn phải kiểm tra quyền trước khi tiết lộ rằng grant đã bị thu hồi. Nếu chỉ cần gọi lại là đọc được tên người nhận, thời điểm và lý do thu hồi, endpoint có thể làm lộ quan hệ quyền.

Với thao tác hàng loạt, cần xác minh người gọi có quyền trên toàn bộ phạm vi được yêu cầu. Không chuyển một grantId thành câu lệnh xóa mọi quan hệ của người nhận trên toàn tenant.

## 8. Ghi trạng thái và phát sự kiện một cách bền vững

Một quy trình thường cần làm hai việc:

~~~text
A. Ghi grant đã REVOKED.
B. Thông báo cho cache, bộ vật chất hóa và các dịch vụ liên quan.
~~~

Nếu thực hiện A rồi gọi broker cho B, tiến trình có thể dừng giữa hai bước. Grant đã bị thu hồi trong kho chính nhưng không có thông báo đi ra.

Nếu phát B trước A, consumer có thể nhận một sự kiện cho thay đổi chưa commit hoặc sẽ rollback.

Một cách triển khai là transactional outbox trong cùng phạm vi giao dịch:

~~~mermaid
flowchart LR
    A["Kiểm tra quyền thu hồi"] --> T["Giao dịch"]
    T --> G["Đánh dấu grant REVOKED"]
    T --> E["Tăng authorization epoch"]
    T --> O["Ghi outbox event"]
    G --> C["Commit cùng nhau"]
    E --> C
    O --> C
    C --> P["Publisher đọc outbox và thử gửi"]
    P --> N["Consumer cập nhật cache hoặc trạng thái"]
~~~

Outbox giải quyết độ bền của ý định phát sự kiện trong phạm vi giao dịch đó. Nó không làm cho mọi consumer cập nhật tức thời và không mặc nhiên tạo ra xử lý exactly-once.

Consumer cần chấp nhận sự kiện trùng, nhận ra sự kiện cũ và phục hồi sau gián đoạn. Nếu một sự kiện grant version 7 đến sau version 8 đã bị thu hồi, consumer không được ghi đè trạng thái mới bằng trạng thái cũ.

Việc đối chiếu version phải theo đúng thực thể hoặc phạm vi mà version đại diện. Không so sánh hai bộ đếm độc lập của hai grant rồi coi số lớn hơn là mới hơn cho toàn đồ thị.

## 9. Ví dụ Java: ghi thu hồi cùng authorization epoch và outbox

Đoạn mã sau minh họa một ứng dụng có grant, nguồn thẩm quyền cần kiểm tra, epoch tài nguyên và outbox trong cùng cơ sở dữ liệu. Các interface là hợp đồng của ví dụ; mã chưa phải ứng dụng chạy độc lập.

~~~java
public final class DelegationRevocationService {

    private final GrantStore store;
    private final RevocationPolicy policy;
    private final java.time.Clock clock;

    public DelegationRevocationService(
            GrantStore store,
            RevocationPolicy policy,
            java.time.Clock clock) {
        this.store = store;
        this.policy = policy;
        this.clock = clock;
    }

    public RevocationReceipt revoke(
            VerifiedActor actor,
            RevokeGrantCommand command) {

        return store.inResourceTransaction(
                actor.tenantId(),
                command.resourceId(),
                tx -> {
                    // Transaction khóa phạm vi tài nguyên theo hợp đồng.
                    Grant grant = tx.loadGrantForUpdate(
                            actor.tenantId(),
                            command.resourceId(),
                            command.grantId()
                    );

                    // Kiểm tra trước cả nhánh trả kết quả idempotent.
                    policy.requireCanRevoke(
                            actor,
                            grant,
                            tx.currentAuthorityView()
                    );

                    if (grant.status() == GrantStatus.REVOKED) {
                        return RevocationReceipt.writeCommitted(
                                grant.id(),
                                grant.version(),
                                grant.revokedAt(),
                                grant.revocationEpoch()
                        );
                    }

                    if (grant.version() != command.expectedVersion()) {
                        throw new GrantVersionConflict();
                    }

                    java.time.Instant now = clock.instant();
                    long epoch = tx.incrementAuthorizationEpoch(
                            command.resourceId()
                    );

                    Grant revoked = grant.revoke(
                            actor.id(),
                            command.reasonCode(),
                            now,
                            epoch
                    );

                    tx.save(revoked);

                    String eventId =
                            revoked.id() + ":" + revoked.version();

                    tx.appendOutbox(
                            new GrantRevokedEvent(
                                    eventId,
                                    revoked.tenantId(),
                                    revoked.resourceId(),
                                    revoked.id(),
                                    revoked.version(),
                                    epoch,
                                    now
                            )
                    );

                    return RevocationReceipt.writeCommitted(
                            revoked.id(),
                            revoked.version(),
                            now,
                            epoch
                    );
                }
        );
    }
}
~~~

Các điều kiện để hiểu đúng ví dụ:

- VerifiedActor đến từ lớp xác thực và không được tạo trực tiếp từ dữ liệu client tự khai.
- Command chỉ định đúng resourceId, grantId, expectedVersion và mã lý do hợp lệ.
- inResourceTransaction chỉ trả kết quả thành công sau khi giao dịch đã commit.
- Khóa phạm vi tài nguyên và cách đọc authority view phải được mọi đường thay đổi liên quan tuân thủ; tên phương thức không tự tạo ra cơ chế đó.
- Grant.revoke tạo trạng thái REVOKED, tăng version và giữ định danh grant. Không tái sử dụng version cũ.
- Lưu grant, tăng epoch và ghi outbox phải cùng thành công hoặc cùng rollback.
- eventId có ràng buộc duy nhất trong outbox để giảm phát sinh sự kiện nghiệp vụ trùng cho cùng phiên bản.
- writeCommitted chỉ xác nhận thay đổi bền vững. Nó không tuyên bố mọi PEP và token đã đồng bộ.

Ở nhánh gọi lại với một grant đã REVOKED, phương thức trả thông tin của lần thu hồi đã lưu. Nó không thay revokedAt bằng thời gian gọi lại và không tăng epoch vô ích. Caller vẫn phải đủ quyền để nhận kết quả đó.

Nếu client mất kết nối sau commit, nó có thể thử lại và nhận kết quả phù hợp. Không suy ra rằng lần đầu thất bại chỉ vì client không thấy phản hồi.

Ví dụ xử lý toàn bộ grant. Với thu hẹp một số action, cần một command và policy có ngữ nghĩa riêng; không đổi trạng thái toàn grant sang REVOKED rồi giả định read vẫn tồn tại bên trong cùng grant đó.

## 10. Ba chiến lược làm mất hiệu lực grant con

### 10.1. Kiểm tra chuỗi khi sử dụng

Mỗi lần dùng dg-102, bộ đánh giá xác minh dg-102, dg-101 và nguồn thẩm quyền gốc. dg-101 đã REVOKED thì đường đó không đủ căn cứ.

Ưu điểm là không phải chờ sửa từng grant con để làm mất hiệu lực đường quyền. Chi phí là phải đọc và đánh giá phụ thuộc với độ mới phù hợp.

Luồng minh họa:

~~~text
load leaf theo snapshot được chấp nhận
-> xác minh người nhận, tài nguyên và action
-> duyệt parent theo cùng hợp đồng dữ liệu
-> chặn nếu bất kỳ grant bắt buộc đã REVOKED, hết hạn hoặc thiếu
-> kiểm tra nguồn thẩm quyền và điều kiện toàn cục
-> chỉ trả Permit cho một đường hợp lệ
~~~

Thiếu parent do lỗi đọc không được xử lý như “không cần parent”. Vòng lặp hoặc vượt giới hạn duyệt cũng không được làm đường quyền tự hợp lệ.

### 10.2. Vô hiệu hóa các quyền phát sinh đã vật chất hóa

Hệ thống có thể lưu chỉ mục từ grant cha tới các grant con hoặc cạnh quyền được tạo ra. Khi thu hồi cha, một tác vụ đánh dấu các phụ thuộc mất hiệu lực.

Cách này có thể hữu ích cho danh sách quyền, tìm kiếm và tối ưu truy vấn, nhưng cần xử lý:

- Một grant cha có số lượng con rất lớn.
- Grant con được tạo đồng thời với lúc thu hồi.
- Tác vụ bị dừng giữa chừng.
- Consumer xử lý trùng hoặc sai thứ tự.
- Người nhận còn nguồn quyền khác.
- Quyền vật chất hóa nằm ở nhiều kho.

Nếu chỉ chặn khi mọi dòng con được cập nhật xong, độ trễ xử lý tác vụ là một phần của thời gian hiệu lực thu hồi.

### 10.3. Kết hợp chặn tại nguồn với cập nhật nền

Một thiết kế kết hợp có thể làm mất hiệu lực nguồn grant trước, yêu cầu PEP kiểm tra nguồn hoặc epoch đủ mới, rồi cập nhật các bản vật chất hóa ở nền.

Điều kiện quyết định là PEP không được tiếp tục coi cạnh reader vật chất hóa là bằng chứng độc lập. Nếu không có kiểm tra phụ thuộc hoặc rào chắn tương ứng, “đã thu hồi ở nguồn” vẫn chưa chặn được đường truy cập đó.

Các tác vụ nền hoàn thiện trạng thái hiển thị và tối ưu dữ liệu. Chúng không được là một bước bị quên trong lời hứa rằng thu hồi đã có hiệu lực.

## 11. Cạnh tranh giữa tạo grant con và thu hồi grant cha

Hai lệnh có thể chạy đồng thời:

~~~text
Lệnh A: Minh tạo dg-102 từ dg-101.
Lệnh B: Lan thu hồi dg-101.
~~~

Một cách triển khai sai:

~~~text
A1: Đọc dg-101 ACTIVE.
B1: Đánh dấu dg-101 REVOKED.
B2: Quét các grant con hiện có, chưa thấy dg-102.
A2: Ghi dg-102 ACTIVE.
~~~

Nếu hệ thống chỉ dựa vào lần quét của B2, dg-102 bị bỏ sót.

Có thể giải quyết tùy mô hình lưu trữ:

- Tạo grant con và thu hồi cha cùng tuân thủ cơ chế khóa hoặc kiểm tra version nguồn cấp tại commit.
- Grant con luôn được đánh giá cùng cha tại lúc sử dụng, nên con mới ghi không thể vượt qua cha đã mất hiệu lực.
- Consumer theo dõi thay đổi bằng revision và có bước đối soát để phát hiện phụ thuộc tạo muộn.
- Rào chắn của nguồn cấp làm mọi quyết định dựa trên nguồn cũ mất hiệu lực.

Trong mô hình phụ thuộc, không nhất thiết phải bảo đảm “không bao giờ có bản ghi con ACTIVE dưới cha REVOKED” ở mọi thời điểm. Điều bắt buộc là bản ghi đó không trở thành đường quyền hợp lệ. Tuy nhiên, trạng thái lưu trữ dễ gây hiểu nhầm vẫn cần được đồng bộ và giải thích đúng trên giao diện.

Nếu dữ liệu grant nằm ở nhiều hệ thống, phải chỉ ra hệ thống nào quyết định hiệu lực. Đọc parent từ kho mới nhưng dùng một quyền reader độc lập trong kho cũ có thể làm mọi kiểm tra concurrency ở parent trở nên vô nghĩa.

## 12. Dữ liệu quyền cũ có thể làm lộ nội dung mới

Giả sử:

~~~text
09:00:00  Minh còn quyền đọc báo cáo.
09:01:00  Lan thu hồi dg-101.
09:01:05  Lan thêm thông tin nhạy cảm mới vào báo cáo.
09:01:06  PEP đọc quyền từ cache trước 09:01 và trả bản báo cáo mới.
~~~

Vấn đề không chỉ là giao diện còn hiện nút đọc. Một quyết định cũ đã được dùng để công bố nội dung phát sinh sau khi quyền bị thu hồi.

Cần ràng buộc độ mới của quyền với thay đổi liên quan tới tài nguyên. Nếu nội dung mới yêu cầu kiểm tra quyền ít nhất sau một mốc thu hồi, PEP phải dùng dữ liệu đáp ứng mốc đó hoặc từ chối phục vụ theo đường kiểm tra hiện tại.

Một ví dụ sản phẩm là [cơ chế consistency của SpiceDB](https://authzed.com/docs/spicedb/concepts/consistency): ZedToken biểu diễn một mốc dữ liệu, và at_least_as_fresh yêu cầu kiểm tra không dùng dữ liệu cũ hơn mốc đó. Token này là giá trị opaque theo hợp đồng sản phẩm; không so sánh chuỗi như số thứ tự hay coi nó là token cấp quyền.

Ví dụ đó không yêu cầu mọi hệ thống phải dùng SpiceDB. Với kho khác, có thể dùng cơ chế revision hoặc phối hợp riêng, nhưng phải chứng minh được mối quan hệ giữa thay đổi quyền, nội dung và quyết định thực thi.

Chỉ truyền revision trong phản hồi cho người đã bấm thu hồi chưa bảo vệ mọi client khác. Minh không nhất thiết tự gửi revision mới. Server cần cách đặt và áp dụng yêu cầu độ mới trên mọi đường đọc liên quan.

Snapshot cố định cũng có giới hạn: một snapshot cũ có thể hữu ích khi phân trang theo một ảnh dữ liệu nhất quán, nhưng không tự đáp ứng yêu cầu nhìn thấy một lần thu hồi mới hơn.

## 13. Cache: phải vô hiệu hóa cả phụ thuộc gián tiếp

Một quyết định “An được đọc report-42 qua dg-102” phụ thuộc ít nhất vào dg-102, dg-101, nguồn thẩm quyền gốc và các điều kiện toàn cục.

Nếu cache key chỉ gồm:

~~~text
user:an + document:report-42 + read
~~~

thì việc thu hồi dg-101 không tự làm key thay đổi.

Có thể thiết kế các cơ chế như:

| Cơ chế | Cách dùng trong ví dụ | Giới hạn |
|---|---|---|
| Cache có thông tin phụ thuộc | Theo dõi grantId và version đã dùng trong quyết định | Phải vô hiệu hóa đủ mọi phụ thuộc |
| Epoch theo tài nguyên | Quyết định gắn với epoch quyền của report-42 | PEP phải lấy được epoch đủ mới |
| TTL có giới hạn | Không giữ Permit quá thời hạn cho phép | Chấp nhận cửa sổ quyền cũ nếu không có cơ chế khác |
| Thông báo thu hồi | Consumer xóa hoặc đánh dấu cache liên quan | Có độ trễ, lỗi và sự kiện trùng |
| Đọc quyền đủ mới | Bỏ kết quả cache không đáp ứng mốc cần thiết | Cần hỗ trợ từ kho dữ liệu và xử lý lỗi |

Một cache Deny cũ thường ảnh hưởng khả năng sử dụng sau khi cấp lại quyền. Một cache Permit cũ ảnh hưởng việc ngăn truy cập sau thu hồi. Cả hai cần được xét trong vòng đời, nhưng không nên khắc phục Deny cũ bằng cách khôi phục grant đã REVOKED.

Không dùng bộ nhớ cache như nơi lưu duy nhất trạng thái thu hồi. Mất cache hoặc khởi động lại không được làm các grant cũ trở về ACTIVE.

Khi consumer cập nhật cache, cần giữ quy tắc version. Sự kiện ACTIVE cũ đến muộn không được vượt sự kiện REVOKED mới hơn. Nếu muốn cấp lại, dùng một thay đổi quản trị hợp lệ và một nguồn quyền mới hoặc phiên bản chuyển trạng thái được policy cho phép.

## 14. Token, phiên và URL tải là những khả năng truy cập riêng

Một grant ReBAC bị thu hồi không tự làm mọi loại credential đã phát hành mất hiệu lực.

### 14.1. Access token và refresh token

[RFC 7009](https://www.rfc-editor.org/rfc/rfc7009.html) quy định cơ chế thu hồi token OAuth và thừa nhận có thể có độ trễ lan truyền. Việc vô hiệu hóa token liên quan phụ thuộc policy và hỗ trợ của authorization server. Không thể chỉ nhìn HTTP 200 của endpoint đó để kết luận mọi resource server đã chặn một grant nghiệp vụ trong ReBAC.

Trong ứng dụng, phải xác định token chỉ nhận diện người dùng hay tự mang khả năng truy cập một tài nguyên. Nếu mỗi request vẫn kiểm tra grant hiện hành, grant có thể bị chặn dù token nhận diện người dùng còn hạn.

Nếu resource server chỉ xác minh chữ ký, audience và exp của token đã mang quyền, việc thay status trong kho grant không tự được nhìn thấy. Cần một cơ chế như kiểm tra trạng thái, phiên bản quyền hoặc giới hạn thời gian chấp nhận được thiết kế rõ.

Thu hồi refresh token có thể ngăn tiếp tục lấy token mới theo hợp đồng của server. Không mặc định mọi access token đã được cấp đều lập tức bị mọi backend từ chối.

### 14.2. Token exchange

[RFC 8693](https://www.rfc-editor.org/rfc/rfc8693.html) nêu token exchange không tự tạo liên kết vòng đời chặt giữa token đầu vào và đầu ra; lan truyền sự kiện thu hồi là việc của triển khai.

Nếu dịch vụ đổi token của Minh thành token cho một backend khác, hệ thống cần giữ liên hệ cần thiết với grant dg-101 hoặc một quyền được quản lý riêng. Nếu không, chuỗi token có thể tồn tại lâu hơn nguồn ủy quyền mà sản phẩm muốn chấm dứt.

### 14.3. Phiên đăng nhập và kết nối dài

Phiên xác thực còn sống không có nghĩa mọi quyền đã được ủy vẫn còn. WebSocket, stream hoặc kết nối tương tác có thể cần kiểm tra lại theo sự kiện, chu kỳ hoặc từng đơn vị dữ liệu.

Chỉ ngắt một phiên trên trình duyệt không tự ngắt mọi phiên thiết bị khác, job nền hoặc kết nối của workload.

### 14.4. URL ký và bản sao đã xuất

Nếu trước khi thu hồi, Minh nhận một URL tải có thể dùng trực tiếp tại kho đối tượng, API không còn nằm trên đường tải. Cần thiết kế khả năng hết hạn hoặc vô hiệu hóa tại chính nơi kiểm soát URL.

URL thời hạn ngắn giới hạn thời gian sử dụng nhưng không đồng nghĩa thu hồi ngay. Bản CSV đã tải về là dữ liệu đã công bố, không còn chỉ là một quyết định quyền trong hệ thống.

## 15. Xử lý yêu cầu đang chạy khi bị thu hồi

Một yêu cầu có thể đã được cấp quyền trước thời điểm thu hồi:

~~~text
T0: Minh được Permit để cập nhật một nhận xét.
T1: Lan thu hồi grant.
T2: Yêu cầu của Minh chuẩn bị commit.
~~~

Hệ thống cần chọn rõ hành vi cho yêu cầu này.

**Mô hình cho phép hoàn tất thao tác đã được chấp nhận:** quyền được xét tại một mốc xác định, chẳng hạn lúc bắt đầu transaction. Thu hồi chặn các thao tác mới nhưng không hủy mọi thao tác đã vượt mốc.

**Mô hình kiểm tra lại trước tác động:** thao tác phải kiểm tra trạng thái hoặc epoch mới trước commit. Nếu quyền thay đổi, dừng hoặc đánh giá lại.

**Mô hình yêu cầu hủy chủ động:** một số job hoặc kết nối phải nhận tín hiệu hủy khi quyền bị thu hồi. Cần định nghĩa độ trễ, checkpoint và giới hạn hủy.

Không mô tả một lần kiểm tra lại độc lập như bảo đảm tuyệt đối nếu vẫn còn khoảng trống trước commit. Muốn sắp thứ tự chặt giữa revoke và cập nhật dữ liệu, hai thao tác phải phối hợp qua cơ chế giao dịch, khóa hoặc giao thức tương đương phù hợp.

Ví dụ, khi grant và dữ liệu nghiệp vụ ở cùng cơ sở dữ liệu, có thể thiết kế thao tác ghi kiểm tra epoch dưới cùng cơ chế đồng bộ mà revoke sử dụng. Cơ chế chỉ đúng nếu mọi đường ghi bắt buộc tuân thủ nó.

Với thanh toán hoặc lời gọi hệ thống ngoài, một transaction cơ sở dữ liệu không tự kéo tác động bên ngoài vào cùng ranh giới nguyên tử. Cần xác định thời điểm hành động được chấp nhận và cách xử lý hủy hoặc bù trừ. Thu hồi quyền không tự hoàn tiền hay đảo ngược một thông báo đã gửi.

Với thao tác đọc có đầu ra dài, có thể phải kiểm tra trước khi phát từng phần hoặc theo checkpoint. Tín hiệu hủy tới sau khi một phần dữ liệu đã gửi không thể lấy lại phần đó.

## 16. Job nền và các khả năng truy cập phát sinh

Delegation thường được dùng để khởi tạo công việc thực hiện sau. Nếu job giữ một cờ authorized=true mãi mãi từ thời điểm tạo, grant có thể bị thu hồi nhưng job vẫn dùng quyền của workload để tiếp tục.

Cần nhận diện các mốc:

~~~text
Người dùng yêu cầu job
-> job nằm trong hàng đợi
-> worker bắt đầu
-> worker đọc dữ liệu
-> worker phát hành kết quả
-> người dùng tải kết quả
~~~

Tại mỗi mốc, hãy xác định quyền được kiểm tra theo grant hiện hành hay theo một quyền thực hiện nhiệm vụ riêng đã được cấp.

Một thiết kế phụ thuộc grant có thể:

- Gắn job với grantId và nguồn quyền của người yêu cầu.
- Đánh giá lại khi bắt đầu xử lý.
- Dùng checkpoint để dừng giữa các phần dữ liệu.
- Không công bố tệp kết quả nếu quyền tải không còn.
- Đánh dấu công việc bị hủy vì quyền bị thu hồi, thay vì báo lỗi mạng chung.

Nếu sản phẩm muốn job tiếp tục sau khi grant nguồn bị thu hồi, phải cấp một quyền nhiệm vụ có phạm vi và vòng đời riêng. Đây là một thay đổi ngữ nghĩa, không phải tối ưu hiệu năng cho hàng đợi.

Bộ nhận sự kiện thu hồi cần xử lý job đã hoàn tất, job đang chạy và job chưa bắt đầu theo từng hợp đồng. Một thông điệp hủy có thể không đến đúng lúc; worker vẫn phải có kiểm tra phù hợp trước tác động quan trọng.

Không xóa tệp kết quả hợp lệ của người khác chỉ vì một grant bị thu hồi. Kết quả có thể có nhiều người được phép tải hoặc thuộc một quy trình lưu trữ riêng. Thu hồi quyền tải và xóa dữ liệu là hai thao tác cần quyền hạn khác nhau.

## 17. Khôi phục hệ thống không được làm quyền đã thu hồi sống lại

Sau sự cố, hệ thống có thể phục hồi grant từ một bản backup cũ hơn thời điểm thu hồi. Nếu chỉ nạp bảng grant và đánh dấu dịch vụ sẵn sàng, dg-101 có thể trở lại ACTIVE.

Quy trình phục hồi cần xét cả dữ liệu quyền, các dấu mốc thu hồi, outbox, vị trí consumer và dữ liệu vật chất hóa.

Các tình huống cần xử lý:

| Tình huống | Rủi ro | Cách kiểm soát cần thiết |
|---|---|---|
| Restore bản grant cũ | Grant REVOKED trở lại ACTIVE | Đối chiếu hoặc phát lại lịch sử thu hồi phù hợp trước phục vụ |
| Cache khôi phục từ snapshot | Permit cũ tiếp tục được dùng | Kiểm tra epoch hoặc loại bỏ cache chưa chứng minh được độ mới |
| Consumer quay lại offset cũ | Sự kiện cũ được xử lý lại | Idempotency và version theo thực thể |
| Consumer bỏ lỡ sự kiện | Một bản vật chất hóa không cập nhật | Đối soát với nguồn chuẩn |
| Job thu hồi hàng loạt chạy dở | Một phần grant còn hiệu lực | Lưu tiến độ bền vững và tiếp tục đúng phạm vi |

Một sự kiện cũ mô tả grant ACTIVE không được dùng để hồi sinh grant đã có bằng chứng REVOKED mới hơn. Bản ghi đánh dấu thu hồi và lịch sử lưu trữ cần đủ tuổi để đáp ứng thời gian phát lại và phục hồi của hệ thống.

Cũng không thể hứa giữ mọi bằng chứng mãi mãi. Thời hạn lưu, yêu cầu xóa dữ liệu và khả năng khôi phục phải được thiết kế cùng nhau. Nếu lịch sử không đủ để xác minh trạng thái quyền sau phục hồi, cần hoàn tất đối soát hoặc hạn chế phục vụ theo chính sách đã định nghĩa.

## 18. Audit và bằng chứng về hiệu lực thu hồi

Nên phân biệt sự kiện quản trị với kết quả thực thi.

~~~json
{
  "event": "delegation_revocation_committed",
  "eventId": "dg-101:8",
  "grantId": "dg-101",
  "grantVersion": 8,
  "tenantId": "acme",
  "resource": "document:report-42",
  "revokedBy": "user:lan",
  "reasonCode": "SHARING_ENDED",
  "authorizationEpoch": 51,
  "committedAt": "2026-11-26T03:15:00Z"
}
~~~

Sự kiện này xác nhận grant đã được ghi thu hồi theo hợp đồng. Nó không chứng minh mọi client đã bị ngắt kết nối.

Một kết quả kiểm tra sau thu hồi có thể ghi:

~~~json
{
  "event": "delegated_access_checked",
  "requestId": "req-902",
  "actor": "user:an",
  "resource": "document:report-42",
  "action": "document:read",
  "selectedGrant": "dg-102",
  "pathResult": "INVALID",
  "reasonCode": "ANCESTOR_REVOKED",
  "invalidatingGrant": "dg-101",
  "observedAuthorizationEpoch": 51
}
~~~

Nếu An được phép qua dg-103, kết quả quyền tổng thể có thể vẫn là Permit. Cần ghi đúng nguồn quyền được dùng; không báo “revocation bị bỏ qua” chỉ vì một đường khác hợp lệ.

Các chỉ số vận hành có ý nghĩa gồm:

- Độ trễ từ commit tới lúc các PEP bắt buộc đáp ứng mốc mới.
- Số sự kiện outbox chưa phát và tuổi sự kiện cũ nhất.
- Độ trễ consumer và số lỗi xử lý.
- Số lần PEP không thể kiểm tra với độ mới cần thiết.
- Số job hoặc kết nối bị dừng vì grant không còn hợp lệ.
- Số quyền vật chất hóa không khớp nguồn chuẩn khi đối soát.

Không gắn grantId, userId hoặc resourceId tùy ý làm nhãn metric nếu tạo ra số lượng giá trị không kiểm soát. Những định danh đó phù hợp hơn với log hoặc trace có cơ chế truy vấn và phân quyền.

Bằng chứng hiệu lực cần đến từ đường thực thi thật, chẳng hạn request sau mốc cam kết không lấy được dữ liệu qua dg-102. Một consumer đã nhận sự kiện không chứng minh PEP đã dùng trạng thái mới.

## 19. Ma trận kiểm thử revocation

| Tình huống | Kết quả cần xác minh |
|---|---|
| Thu hồi grant đang ACTIVE | Ghi REVOKED, tăng version và lưu nguồn thu hồi |
| Gọi lại cùng grant | Kết quả idempotent theo hợp đồng, không tạo lần thu hồi giả |
| Caller không đủ quyền | Không sửa grant hoặc làm lộ metadata ngoài phạm vi |
| Thu hồi ở tenant khác | Bị chặn theo định danh và phạm vi server kiểm chứng |
| Grant cha bị thu hồi | Đường quyền qua grant con không còn hợp lệ |
| Có grant độc lập khác | Giữ đúng quyền qua nguồn còn hợp lệ |
| Chỉ bỏ comment | comment mất hiệu lực; read được xử lý đúng thiết kế thay đổi phạm vi |
| Grant con được tạo đồng thời | Không có đường quyền thoát khỏi thu hồi cha |
| Outbox chưa phát được | Trạng thái commit được giữ; có retry và theo dõi |
| Sự kiện trùng hoặc đảo thứ tự | Không hồi sinh ACTIVE cũ hoặc ghi đè version mới |
| PEP có cache Permit cũ | Đáp ứng giới hạn độ mới của đường truy cập |
| Tài liệu cập nhật sau thu hồi | Người mất quyền không nhận nội dung mới qua quyết định cũ |
| Token còn hạn | Hành vi đúng với cơ chế kiểm tra grant đã công bố |
| Job đang nằm trong hàng đợi | Kiểm tra lại hoặc dùng quyền nhiệm vụ riêng đúng hợp đồng |
| Yêu cầu đã qua kiểm tra quyền | Tuân thủ chính sách xử lý yêu cầu đang chạy |
| URL tải đã phát hành | Hiệu lực còn lại đúng khả năng kiểm soát tại kho tải |
| Khôi phục từ backup cũ | Không tự phục hồi quyền đã thu hồi |
| Kho quyền không đủ mới hoặc bị lỗi | Không dùng Permit cũ ngoài giới hạn cho phép |

Với kiểm thử cạnh tranh, nên điều khiển thứ tự các bước bằng rào chắn hoặc cơ chế đồng bộ trong bài kiểm thử. Chỉ chạy nhiều request ngẫu nhiên có thể bỏ sót đúng khoảng trống giữa kiểm tra cha và ghi con.

Với kiểm thử thời gian hiệu lực, dùng nguồn thời gian có thể kiểm soát và quan sát revision hoặc epoch. Chờ một khoảng cố định rồi kiểm tra một lần dễ làm bài kiểm thử chập chờn và không xác định được hệ thống đã vi phạm ở mốc nào.

Với kiểm thử tích hợp, phải đi qua cùng PEP, cache và đường dữ liệu mà người dùng thật sử dụng. Truy vấn trực tiếp bảng grant chỉ xác minh lưu trữ.

## 20. Phân tích một ca thu hồi chưa có hiệu lực

Giả sử owner đã thu hồi quyền của Minh nhưng An vẫn tải được tài liệu qua một job xuất dữ liệu.

Cách phân tích có thể đi theo các câu hỏi:

1. An có nguồn quyền độc lập nào khác ngoài grant con của Minh không?
2. Job đang dùng grant nào và action nào?
3. Bản ghi cha đã commit REVOKED ở version nào?
4. Quyết định của job được đánh giá ở revision hoặc epoch nào?
5. Job có kiểm tra cha hay chỉ nhìn một cạnh reader đã vật chất hóa?
6. Token của workload có đang được dùng thay toàn bộ quyền của người yêu cầu không?
7. Tệp kết quả được tạo trước hay sau thu hồi, và quyền tải kiểm tra ở đâu?
8. API thu hồi đã hứa commit bền vững, lan truyền có giới hạn hay chặn cả công việc đang chạy?

Nếu job chỉ lưu authorized=true từ lúc được tạo, sửa giao diện hoặc tăng tốc cập nhật danh sách chia sẻ sẽ không giải quyết đường truy cập đó.

Một cách sửa theo mô hình phụ thuộc là gắn job với grant và nguồn quyền, kiểm tra lại ở checkpoint cần thiết, áp dụng mốc dữ liệu quyền đủ mới và bảo vệ riêng quyền tải kết quả. Sau thay đổi, kiểm thử cần chứng minh đúng đường job từng dùng đã không còn sử dụng grant bị thu hồi.

Không áp dụng một lệnh xóa mọi quyền của An để làm ca kiểm thử “xanh” nếu yêu cầu chỉ là thu hồi chuỗi của Minh. Cách đó có thể che lỗi và phá quyền được cấp độc lập.

## 21. Tự kiểm tra kiến thức

**Grant đã REVOKED trong cơ sở dữ liệu có đồng nghĩa thu hồi đã hoàn tất ở mọi nơi không?**

Không. Cần xét cache, bản sao, token, quyền vật chất hóa và đường thực thi theo hợp đồng thời gian của hệ thống.

**Thu hồi grant cha có bắt buộc xóa mọi bản ghi con ngay không?**

Không nhất thiết. Có thể chặn qua kiểm tra phụ thuộc đủ mới rồi đồng bộ dữ liệu con sau. Nhưng nếu PEP chỉ dùng quyền con vật chất hóa, cập nhật nguồn đơn lẻ chưa đủ.

**Vì sao người nhận vẫn có thể đọc sau khi thu hồi một grant?**

Người đó có thể còn một nguồn quyền độc lập. Cần phân biệt thu hồi nguồn quyền với cấm truy cập tổng thể.

**Transactional outbox giải quyết được gì?**

Nó giúp ghi thay đổi và ý định phát sự kiện bền vững trong cùng giao dịch. Nó không tự bảo đảm consumer đã cập nhật tức thời.

**Có thể dùng mỗi expiresAt để thay revocation không?**

Chỉ nếu sản phẩm chấp nhận quyền tồn tại đến hết thời hạn. Thu hồi trước hạn cần cơ chế khác trên đường thực thi.

**Cần chú ý điều gì khi cấp lại sau thu hồi?**

Cấp lại phải là hành động được phân quyền với lịch sử rõ ràng. Không để cache, sự kiện cũ hoặc restore backup vô tình hồi sinh grant.

## 22. Những nguyên tắc cần giữ

Thu hồi chính xác cần biết nguồn quyền nào bị chấm dứt và các quyền nào phụ thuộc nguồn đó. Trong một chuỗi, mọi mắt xích bắt buộc phải hợp lệ; giữa các đường độc lập, hệ thống phải giữ đúng ngữ nghĩa policy.

Cam kết thời gian phải gắn với điểm thực thi. Commit trạng thái, phát sự kiện, cập nhật cache và chặn thao tác là những mốc khác nhau cần được phối hợp và đo lường.

Token, workload, job nền, URL tải và yêu cầu đang chạy đều có thể tiếp tục mang khả năng truy cập. Mỗi đường cần một hợp đồng rõ về độ mới, kiểm tra lại và hủy.

Bằng chứng hoàn thành revocation là hành vi đúng của các thao tác thuộc phạm vi cam kết, đồng thời không xóa nhầm những nguồn quyền còn hợp lệ.

## Tài liệu tham khảo

- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html): cơ chế thu hồi token và các lưu ý về lan truyền, token liên quan.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html): giới hạn liên kết vòng đời giữa token đầu vào và đầu ra.
- [AuthZed — Consistency trong SpiceDB](https://authzed.com/docs/spicedb/concepts/consistency): ví dụ về dấu mốc dữ liệu và yêu cầu độ mới khi kiểm tra quyền.

