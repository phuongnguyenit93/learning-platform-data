# ReBAC và multi-tenant

## 1. Vì sao ReBAC cần ranh giới tenant?

Trong ứng dụng multi-tenant, nhiều khách hàng sử dụng chung một nền tảng nhưng dữ liệu và quyền quản trị của từng khách hàng phải được giới hạn theo thiết kế. Một tenant thường là một tổ chức khách hàng, workspace hoặc đơn vị được cấp một phạm vi vận hành riêng.

ReBAC (Relationship-Based Access Control) quyết định quyền dựa trên các quan hệ giữa danh tính và tài nguyên. Ví dụ:

~~~text
Lan -> member của team Backend
team Backend -> editor của tài liệu Thiết kế API
=> Lan có quyền chỉnh sửa tài liệu
~~~

Trong ứng dụng một tổ chức, đường quan hệ này có thể đủ để diễn đạt yêu cầu nghiệp vụ. Trong ứng dụng nhiều tenant, còn phải biết Backend và tài liệu thuộc tổ chức nào, Lan đang hành động trong ngữ cảnh nào và đường quan hệ liên tenant có được cho phép hay không.

Một tuple hợp lệ về kiểu vẫn có thể vi phạm ranh giới tenant:

~~~text
document:a-api-design#editor@team:b-backend#member
~~~

Nếu tài liệu thuộc tenant A nhưng team thuộc tenant B, quan hệ trên có thể mở quyền từ một tổ chức sang tổ chức khác. Engine không nhất thiết coi đây là lỗi: nếu mô hình cho phép editor nhận team#member, tuple vẫn có thể đúng schema.

Bài học sử dụng một hệ thống quản lý tài liệu làm ví dụ. Mục tiêu là xây dựng quyền đủ chi tiết trong từng tenant, đồng thời giữ cho quan hệ giữa các tenant chỉ xuất hiện qua những luồng đã được thiết kế và phê duyệt.

## 2. Phân biệt tenant, danh tính và ngữ cảnh truy cập

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Tenant | Phạm vi dữ liệu và quản trị của khách hàng | organization:a |
| Principal | Danh tính đang thực hiện yêu cầu | user:lan |
| Tenant membership | Danh tính được tham gia tenant nào | Lan thuộc A và B |
| Active tenant | Tenant được chọn và kiểm chứng cho request | Lan đang làm việc trong A |
| Resource tenant | Tenant sở hữu tài nguyên | Tài liệu API thuộc A |
| Relation | Quan hệ cụ thể dẫn tới quyền | Lan là editor qua team Backend |
| Platform authority | Quyền vận hành ở cấp nền tảng | Tác vụ hỗ trợ được cấp phạm vi riêng |

Một danh tính có thể thuộc nhiều tenant. Vì vậy, “người dùng đã đăng nhập” và “người dùng thuộc một tenant” đều chưa đủ để chứng minh quyền đối với một tài nguyên cụ thể.

Tenant cũng không nhất thiết bằng identity provider hoặc miền email. Hai khách hàng có thể cùng dùng một nhà cung cấp đăng nhập. Một tổ chức có thể dùng nhiều identity provider. Việc gộp hoặc liên kết tài khoản phải dựa vào ánh xạ danh tính được kiểm soát.

Nếu các nguồn danh tính có thể phát hành cùng một subject ID, backend cần chuẩn hóa danh tính theo nguồn phát hành và subject hoặc qua một ID nội bộ duy nhất. Không dùng email chưa xác minh làm khóa hợp nhất người dùng giữa các tenant.

### 2.1. Tenant do client chọn là đầu vào cần kiểm chứng

Một URL như /tenants/a/documents/42 hoặc header X-Tenant-ID có thể giúp chọn phạm vi thao tác. Nó không chứng minh người gọi được hành động trong tenant đó.

Backend phải ràng buộc lựa chọn này với danh tính đã xác thực và quyền tenant hiện hành. Với workload hoặc API key, cần kiểm tra tập tenant mà credential được phép phục vụ, thay vì giả lập một người dùng có membership.

OWASP khuyến nghị coi tenant ID do client gửi là giá trị lựa chọn và xác minh phạm vi được phép phía server. [OWASP Multi Tenant Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html).

### 2.2. Active tenant khác tập mọi tenant có membership

Lan có thể là thành viên của A và B nhưng request hiện tại đang mở workspace B. Nếu sản phẩm quy định mỗi request chỉ làm việc trong một tenant, quyền của Lan ở A không được tự động sử dụng trong request của B.

Ngữ cảnh này quan trọng với truy vấn danh sách, cache, thao tác hàng loạt và audit. Nó cũng tránh những trường hợp giao diện đang hiển thị B nhưng backend vô tình sử dụng quyền rộng hơn từ A.

Một endpoint tổng hợp nhiều tenant có thể tồn tại, nhưng cần được thiết kế rõ như một luồng khác, xác định phạm vi từng tài nguyên và quyền tương ứng.

## 3. Ba nhóm điều kiện cần phối hợp

Đối với luồng nội bộ một tenant của bài học, có thể diễn đạt quyết định như sau:

~~~text
Được thực hiện thao tác
    = danh tính và phiên hợp lệ
      AND ngữ cảnh tenant được kiểm chứng
      AND tài nguyên thuộc tenant trong ngữ cảnh
      AND tồn tại quyền ReBAC phù hợp trên tài nguyên
      AND các điều kiện bổ sung của thao tác được đáp ứng
~~~

Những điều kiện này bảo vệ các khía cạnh khác nhau:

- Tenant scope giới hạn request đang làm việc trên dữ liệu khách hàng nào.
- ReBAC xác định quyền cụ thể bên trong phạm vi đó.
- Trạng thái danh tính, mức bảo đảm phiên và điều kiện môi trường giới hạn việc sử dụng quyền.

Nếu chỉ lọc cùng tenant, mọi member có thể bị cấp quá nhiều quyền trong tenant. Nếu chỉ kiểm tra graph mà bỏ ngữ cảnh, một user nhiều tenant có thể truy cập đúng tài nguyên nhưng trong request sai phạm vi.

Quy định “mọi tài nguyên trong bài có đúng một tenant chủ quản” là một bất biến nghiệp vụ. Mô hình dữ liệu và các API ghi cần bảo vệ bất biến ấy; không chỉ ghi nó trong tài liệu.

## 4. Chọn cách tổ chức dữ liệu phân quyền

### 4.1. Một store dùng chung cho nhiều tenant

Các tenant cùng sử dụng một graph hoặc một store. Tenant, team và tài nguyên có ID phân biệt, còn ranh giới được thực thi qua mô hình, kiểm soát dữ liệu quan hệ và lớp ứng dụng.

Ưu điểm là dễ biểu diễn danh tính toàn cục hoặc chia sẻ liên tổ chức trong cùng miền phân quyền. Thách thức là mọi đường ghi, truy vấn và công cụ quản trị đều phải giữ đúng tenant scope.

Một lỗi ghi quan hệ có thể ảnh hưởng nhiều khách hàng nếu credential có quyền ghi toàn store. Vì vậy, việc dùng store chung cần đi kèm kiểm soát actor, phạm vi object và những quan hệ được phép ghi.

### 4.2. Tách store theo tenant

Mỗi tenant có store riêng. Backend định tuyến request đến store dựa trên ánh xạ được quản trị.

Trong OpenFGA, store chứa các phiên bản model và tuple; dữ liệu ở store khác không tự tham gia vào cùng phép đánh giá. [Khái niệm Store của OpenFGA](https://openfga.dev/docs/concepts).

Tách store giúp tạo một ranh giới dữ liệu phân quyền, nhưng không tự hoàn tất tenant isolation. Nếu backend lấy storeId tùy ý từ client hoặc dùng sai ánh xạ tenant -> store, nó vẫn có thể kiểm tra và đọc nhầm phạm vi.

Tách store cũng không nhất thiết bằng tách database, credential hay hạ tầng vật lý. Cần phân biệt ranh giới logic trong engine với mức cách ly triển khai mà hệ thống thực sự cung cấp.

### 4.3. So sánh lựa chọn

| Tiêu chí | Store chung | Store theo tenant |
| --- | --- | --- |
| Quyền giữa các tenant | Có thể biểu diễn trong cùng graph nếu được thiết kế | Cần cơ chế cầu nối hoặc điều phối bên ngoài |
| Quản lý model | Dễ dùng chung một model cho nhiều tenant | Cần theo dõi rollout model qua nhiều store |
| Lỗi định tuyến | Phải giữ đúng object và tenant scope | Phải giữ đúng ánh xạ tenant tới store |
| Lỗi ghi quan hệ | Có nguy cơ tạo cạnh sai giữa các tenant | Vẫn có nguy cơ ghi sai store bằng credential rộng |
| Vận hành | Ít store hơn nhưng graph có phạm vi rộng | Nhiều đơn vị provisioning và theo dõi hơn |
| Audit | Cần lọc tenant chính xác trong dữ liệu chung | Vẫn cần liên kết tenant, store và actor |

Không có lựa chọn duy nhất phù hợp cho mọi hệ thống. Cần dựa vào yêu cầu chia sẻ, mức cách ly, quy mô vận hành và phạm vi quyền của dịch vụ quản trị.

## 5. Mô hình minh họa cho truy cập nội bộ tenant

Ví dụ dưới đây sử dụng cú pháp DSL của OpenFGA. Các quan hệ do bài học tự thiết kế; mô hình không thay thế việc kiểm tra các bất biến dữ liệu ở lớp ghi.

~~~text
model
  schema 1.1

type user

type organization
  relations
    define member: [user]
    define admin: [user]
    define participant: member or admin

type team
  relations
    define organization: [organization]
    define assigned_member: [user]
    define org_participant: participant from organization
    define member: assigned_member and org_participant

type document
  relations
    define organization: [organization]
    define owner: [user]
    define editor: [user, team#member] or owner
    define viewer: [user, team#member] or editor
    define org_participant: participant from organization
    define can_view: viewer and org_participant
    define can_edit: editor and org_participant
    define can_share: owner and org_participant
~~~

Đọc mô hình theo từng lớp:

1. Participant của organization là member hoặc admin của organization đó.
2. Member có hiệu lực của team phải vừa được assigned_member, vừa là participant của organization gắn với team.
3. Viewer, editor và owner xác định các đường cấp quyền trên document.
4. Những quyền can_view, can_edit và can_share còn yêu cầu người dùng là participant của organization gắn với document.

Admin tổ chức được tính là participant, nhưng không tự có viewer của mọi tài liệu. Nếu nghiệp vụ cho admin quyền đọc hoặc quản trị toàn bộ tài liệu, cần thêm điều đó vào mô hình một cách rõ ràng.

Owner của document có editor và viewer theo quy tắc của ví dụ. Tuy nhiên, owner rời organization sẽ không có các quyền can_* nếu không còn org_participant.

### 5.1. Những bất biến mô hình chưa tự bảo đảm

Cần kiểm soát ở dữ liệu và luồng ghi ít nhất các điều kiện:

~~~text
Mỗi team thuộc đúng một organization.
Mỗi document thuộc đúng một organization.
Team được chia sẻ tài liệu nội bộ phải cùng organization với document.
Chủ thể được cấp quan hệ phải đáp ứng quy định của tổ chức.
Không có luồng ghi không được kiểm soát bỏ qua các điều kiện trên.
~~~

Khai báo organization: [organization] chỉ cho phép kiểu đối tượng tương ứng. Nó không tự đặt giới hạn “đúng một” tuple organization trên mỗi object.

Nếu một document được gắn nhầm cả organization A và B, tập org_participant có thể mở rộng qua cả hai. Vì vậy, kiểm soát số lượng parent organization là một phần bảo vệ tenant boundary.

### 5.2. Dữ liệu hợp lệ ban đầu

~~~text
organization:a#member@user:lan
organization:b#member@user:lan
organization:a#admin@user:minh
organization:b#member@user:bao

team:a-backend#organization@organization:a
team:a-backend#assigned_member@user:lan

team:b-backend#organization@organization:b
team:b-backend#assigned_member@user:bao

document:a-api-design#organization@organization:a
document:a-api-design#owner@user:minh
document:a-api-design#editor@team:a-backend#member
~~~

Dạng object#relation@subject là ký hiệu dễ đọc cho tuple. Các ID có tiền tố a hoặc b chỉ để minh họa; engine không tự giải nghĩa chúng là tenant.

~~~mermaid
flowchart LR
    L["Lan"] -->|"member"| OA["organization A"]
    L -->|"member"| OB["organization B"]
    L -->|"assigned_member"| TA["team Backend A"]
    TA -->|"organization"| OA
    TA -->|"member được cấp editor"| D["Tài liệu API A"]
    D -->|"organization"| OA
    M["Minh"] -->|"owner"| D
    B["Bảo"] -->|"member"| OB
    B -->|"assigned_member"| TB["team Backend B"]
    TB -->|"organization"| OB
~~~

### 5.3. Những kết quả theo graph

| Câu hỏi | Kết quả |
| --- | --- |
| Lan có member của team Backend A? | Có |
| Lan có can_edit tài liệu API A? | Có |
| Lan có can_share tài liệu API A? | Không |
| Bảo có can_view tài liệu API A? | Không |
| Minh có can_share tài liệu API A? | Có |
| Bảo có được đọc mọi tài liệu B chỉ vì member B? | Không suy ra được từ model |

Lan được graph cấp quyền tài liệu A vì có đường qua team Backend A và là participant của A. Bảo chưa có đường hợp lệ tới tài liệu A.

Những kết quả này chỉ là một phần quyết định thực thi. Model chưa sử dụng active tenant của request. Nếu Lan đang hành động trong ngữ cảnh B, lớp thực thi của luồng nội bộ vẫn phải ngăn truy cập tài liệu A theo hợp đồng đã chọn.

## 6. Vì sao kiểm tra membership tenant vẫn chưa đủ?

### 6.1. Một người có thể thuộc nhiều tenant

Giả sử Hà là member của cả A và B nhưng chỉ được assigned_member của team Backend B. Hà chưa được chia sẻ trực tiếp hoặc gián tiếp tài liệu API A.

~~~text
organization:a#member@user:ha
organization:b#member@user:ha
team:b-backend#assigned_member@user:ha
~~~

Với dữ liệu hợp lệ ban đầu, Hà không có can_view tài liệu API A.

Bây giờ một đường ghi lỗi tạo thêm:

~~~text
document:a-api-design#editor@team:b-backend#member
~~~

Hà là member có hiệu lực của Backend B, đồng thời là participant A. Cả điều kiện editor và org_participant trên document A đều có thể đúng. Khi đó, can_edit của Hà có thể trở thành true dù team chia sẻ tài liệu thuộc sai tenant theo quy tắc nội bộ.

Đây là phản ví dụ quan trọng: lấy giao giữa “có quyền tài liệu” và “là member tenant của tài liệu” chưa chứng minh rằng mọi cạnh trên đường quyền đều nằm trong tenant ấy.

### 6.2. Bảo vệ cấu trúc quan hệ

Đối với luồng chia sẻ nội bộ, API phải kiểm tra organization của team nhận chia sẻ bằng organization của document trước khi ghi tuple.

Tương tự, quan hệ document -> folder, folder -> workspace hoặc team -> team có thể đưa quyền đi qua nhiều bước. Cần quy định loại cạnh nào phải cùng tenant và cạnh nào được phép vượt tenant.

Nếu chỉ kiểm tra ở điểm cuối, một user có membership ở nhiều tổ chức có thể làm lỗi cấu trúc quan hệ khó bị phát hiện hơn so với ca kiểm thử chỉ dùng một user riêng cho mỗi tenant.

Model chỉ là một phần của ràng buộc. Việc kiểm soát mọi đường ghi, kiểm tra dữ liệu hiện hữu và kiểm thử ca nhiều membership là cần thiết để giữ đúng cấu trúc mong muốn.

## 7. Ràng buộc ngữ cảnh request với quyền tài nguyên

### 7.1. Luồng truy cập trong một tenant

Đối với endpoint nội bộ, một quy trình tham khảo là:

~~~text
readDocument(session, selectedTenantId, documentId):
    principal = authenticateAndResolveIdentity(session)
    require principal is active

    context = resolveAndValidateTenantContext(
        principal, selectedTenantId
    )

    document = repository.findMetadata(
        tenantId = context.tenantId,
        documentId = documentId
    )
    require document exists in that scope

    decision = authorization.check(
        user = principal.id,
        relation = "can_view",
        object = canonicalDocumentObject(document),
        store = trustedStoreMapping(context.tenantId),
        model = configuredModelForStore()
    )
    require decision is a valid ALLOWED result

    return repository.readWithinValidatedScope(document)
~~~

Đây là mã giả thiết kế, không phải API hoặc SDK cụ thể. Luồng này cố ý tìm tài nguyên theo tenant đã kiểm chứng, tạo object phân quyền từ dữ liệu phía server và chọn store qua mapping tin cậy.

Không kiểm tra quyền trên một object do client cung cấp rồi đọc dữ liệu từ object khác. Nếu tài nguyên có thể đổi tenant hoặc trạng thái trong lúc request chạy, cần cơ chế nhất quán, kiểm tra phiên bản hoặc đánh giá lại phù hợp.

### 7.2. Chọn bảo vệ ngữ cảnh ở ứng dụng hay trong model

Có thể dùng điều kiện ngữ cảnh trong engine hoặc ràng buộc ở middleware và lớp nghiệp vụ, miễn là mọi đường truy cập đều phải đi qua cơ chế đó.

OpenFGA có hướng dẫn cho trường hợp người dùng thuộc nhiều tổ chức và quyền còn phụ thuộc tổ chức đang đăng nhập. Hướng dẫn phân biệt quyền ở tổ chức sở hữu tài nguyên với quyền ở tổ chức được chia sẻ. [Authorization Through Organization Context](https://openfga.dev/docs/modeling/organization-context-authorization).

Nếu dùng contextual tuple hoặc dữ liệu context, backend phải xây dựng nó từ ngữ cảnh đã kiểm chứng. Cho client tự gửi một tuple “đang thuộc A” mà không xác minh chỉ chuyển lỗ hổng tenant selection vào input của engine.

Quyền truy cập dựa trên context cũng cần được phản ánh trong cache. Một kết quả Allow của Lan ở ngữ cảnh A không tự được tái sử dụng cho request ở B.

## 8. Kiểm soát việc ghi quan hệ

### 8.1. Quyền ghi tuple khác quyền của tenant admin

Một credential dịch vụ có thể có khả năng ghi tuple trên cả store. Điều đó không có nghĩa một admin của A được dùng credential ấy để sửa mọi object trong store.

Backend cần tách khả năng kỹ thuật của dịch vụ khỏi phạm vi nghiệp vụ của người yêu cầu. Mỗi thao tác phải xác định actor, tenant, tài nguyên, quan hệ được phép thay đổi và chủ thể được nhận quyền.

Ví dụ, khi Minh chia sẻ tài liệu API A cho Backend A:

1. Xác thực Minh và kiểm tra ngữ cảnh A.
2. Lấy metadata tài liệu và team từ nguồn chuẩn.
3. Kiểm tra tài liệu và team đều thuộc A theo luồng chia sẻ nội bộ.
4. Kiểm tra Minh có can_share trên đúng tài liệu.
5. Kiểm tra loại quyền được cấp nằm trong phạm vi Minh được ủy quyền.
6. Ghi thay đổi và audit qua cơ chế có kiểm soát.

Không nhận relation tự do từ client rồi ghi nguyên vẹn. Một endpoint “thêm viewer” không nên cho phép đổi trường relation thành owner hoặc organization.

Quản trị tenant A cũng không tự có quyền quản trị model toàn store. Thay model dùng chung có thể thay đổi quyền của mọi tenant, nên thuộc một phạm vi vận hành khác.

### 8.2. Ràng buộc cùng tenant ở nguồn dữ liệu

Nếu quan hệ được quản lý ở một database nghiệp vụ rồi đồng bộ sang graph, có thể dùng ràng buộc dữ liệu để bảo vệ một số bất biến.

Schema SQL khái niệm dưới đây minh họa chia sẻ nội bộ giữa document và team cùng tenant:

~~~sql
CREATE TABLE team (
    tenant_id VARCHAR(100) NOT NULL,
    team_id VARCHAR(100) NOT NULL,
    PRIMARY KEY (tenant_id, team_id)
);

CREATE TABLE document (
    tenant_id VARCHAR(100) NOT NULL,
    document_id VARCHAR(100) NOT NULL,
    PRIMARY KEY (tenant_id, document_id)
);

CREATE TABLE document_team_editor (
    tenant_id VARCHAR(100) NOT NULL,
    document_id VARCHAR(100) NOT NULL,
    team_id VARCHAR(100) NOT NULL,
    PRIMARY KEY (tenant_id, document_id, team_id),
    FOREIGN KEY (tenant_id, document_id)
        REFERENCES document (tenant_id, document_id),
    FOREIGN KEY (tenant_id, team_id)
        REFERENCES team (tenant_id, team_id)
);
~~~

Cùng một tenant_id được dùng trong cả hai khóa ngoại. Vì vậy, một hàng chia sẻ không tham chiếu được tài liệu A với team chỉ tồn tại trong B.

Đây là ví dụ cho nguồn dữ liệu quan hệ, không phải schema lưu tuple của OpenFGA. Nó không tự bảo vệ graph nếu có một API khác cho phép ghi trực tiếp quan hệ trái quy định.

Ràng buộc này cũng không kiểm tra người gọi có quyền chia sẻ. Backend vẫn phải kiểm tra actor và action. Khóa ngoại bảo vệ tính hợp lệ của liên kết, không thay thế authorization.

### 8.3. Đồng bộ và reconciliation

Nếu nguồn chuẩn ghi một giao dịch rồi graph được cập nhật bất đồng bộ, cần liên kết thay đổi với một version hoặc định danh sự kiện ổn định.

Sự kiện có thể chứa tenant chủ quản, object chuẩn hóa, thay đổi quan hệ và version tại nguồn. Bộ đồng bộ phải kiểm tra nguồn phát và phạm vi được ủy quyền, không coi một tenant_id bất kỳ trong payload là đáng tin.

Sự kiện cũ đến muộn không được phục hồi một quyền đã thu hồi. Cơ chế retry và idempotency cần giữ đúng thứ tự hoặc đối chiếu trạng thái mới nhất theo thiết kế.

Reconciliation nên phát hiện những bất thường như:

- Document hoặc team không có organization, hoặc có nhiều organization.
- Quan hệ chia sẻ nội bộ trỏ sang team của tenant khác.
- Object không còn tồn tại trong nguồn chuẩn nhưng vẫn còn quyền.
- Tuple trong graph không có provenance hợp lệ.
- Model hoặc store không khớp cấu hình tenant được quản lý.

Phát hiện sai lệch không đồng nghĩa tự xóa mọi dữ liệu bất thường. Luồng xử lý cần phân biệt lỗi với các trường hợp chia sẻ liên tenant được thiết kế riêng, đồng thời tránh ghi đè thay đổi mới bằng snapshot cũ.

## 9. Chia sẻ liên tenant có chủ đích

### 9.1. Cross-tenant access không luôn là lỗi

Một công ty A có thể mời đối tác B xem một dự án. Đây là yêu cầu hợp lệ nếu sản phẩm hỗ trợ cộng tác liên tổ chức.

Điểm cần giữ là phân biệt quan hệ chia sẻ được cấp có chủ đích với một cạnh sai trong luồng nội bộ. Không sửa lỗi bằng cách bỏ toàn bộ kiểm tra tenant khi có nhu cầu cộng tác.

Một grant liên tenant nên xác định:

~~~text
Tenant chủ tài nguyên: A
Tài nguyên: dự án hoặc tài liệu cụ thể
Bên nhận: một user hoặc tập thành viên được chọn của B
Hành động: xem, bình luận hoặc chỉnh sửa theo phạm vi
Quyền quản trị: có hay không, với định nghĩa cụ thể
Thời hạn và điều kiện thu hồi: theo hợp đồng chia sẻ
Người cấp và căn cứ: được ghi nhận
~~~

Document vẫn thuộc A. Chia sẻ cho B không tự chuyển ownership, không tự trao quyền xóa tài nguyên và không tự cho admin B sửa membership của A.

### 9.2. Chia sẻ cho người hay cho cả tổ chức?

Chia sẻ trực tiếp cho user Hà tạo quyền gắn với danh tính được chọn. Chia sẻ cho organization B#participant có thể mở quyền cho mọi người hiện được tính là participant B, tùy model.

Nếu B bổ sung thành viên, những người mới có thể tự nhận quyền qua grant userset ấy. Đây là một quyết định ủy quyền quản trị thành viên cho phía B, không chỉ là cách giảm số tuple.

Có thể chọn nhóm đối tác riêng hoặc danh tính guest tại phía chủ tài nguyên để giới hạn phạm vi. Mỗi cách cần quy định nguồn membership, quản trị khách và thời điểm thay đổi có hiệu lực.

Không mặc nhiên thêm khách vào relation member thông thường của A chỉ để vượt qua điều kiện org_participant. Nếu các tài nguyên khác đang cấp quyền cho mọi member A, thao tác đó có thể mở thêm quyền ngoài mục tiêu chia sẻ.

### 9.3. Ngữ cảnh chủ tài nguyên và ngữ cảnh bên nhận

Trong luồng cộng tác, active tenant của bên nhận có thể là B trong khi resource tenant là A. Vì vậy, điều kiện “hai tenant phải bằng nhau” của endpoint nội bộ không áp dụng nguyên xi.

Cần một đường kiểm tra được thiết kế rõ:

~~~text
User đang hành động trong B
    AND có membership hoặc quyền đại diện B phù hợp
    AND A đã cấp grant cho user hoặc nhóm được chọn trong B
    AND grant còn hiệu lực cho đúng tài nguyên và hành động
    AND các điều kiện thực thi của A được đáp ứng
~~~

Mô hình ở mục 5 phục vụ truy cập nội bộ và chưa triển khai luồng này. Muốn hỗ trợ B2B, cần bổ sung relation, điều kiện hoặc một quy trình ủy quyền tương ứng, đồng thời cập nhật kiểm thử.

Ở lớp dữ liệu, có thể dùng đường đọc chia sẻ được kiểm soát cho đúng object đã được cấp quyền. Không biến mọi truy vấn thành truy vấn không tenant scope chỉ vì có một số tài nguyên được chia sẻ.

### 9.4. Chia sẻ khác quyền hỗ trợ nền tảng

Nhân viên hỗ trợ của nhà cung cấp SaaS có thể cần xem dữ liệu của một tenant để xử lý sự cố. Đây là một loại quyền khác với membership của khách hàng.

Luồng hỗ trợ nên biểu diễn rõ actor thực, tenant được cấp, tập hành động, thời hạn và căn cứ ủy quyền theo chính sách vận hành. Không dùng một cờ platformAdmin để bỏ qua mọi ranh giới trong tất cả endpoint.

Nếu dịch vụ hành động thay người dùng, cần giữ cả danh tính dịch vụ và người được đại diện trong dấu vết. Credential dịch vụ đọc được graph không tự trở thành bằng chứng rằng người dùng cuối có quyền đọc tài liệu.

## 10. Ownership trong môi trường nhiều tenant

### 10.1. Owner của object và tenant chủ quản

Owner là một quan hệ quyền trên tài nguyên. Tenant chủ quản là phạm vi dữ liệu. Hai giá trị không đồng nhất.

Trong ví dụ, Minh là owner tài liệu thuộc A. Nếu tài khoản Minh cũng thuộc B, điều đó không làm tài liệu tự xuất hiện trong B hoặc cho admin B quản lý tài liệu.

Chuyển owner từ Minh sang Lan trong cùng A có thể là một thao tác quản trị tài nguyên. Chuyển tài liệu từ A sang B là một migration ranh giới dữ liệu, cần xem xét nhiều quan hệ hơn.

### 10.2. Di chuyển tài nguyên sang tenant khác

Giữ nguyên ID và chỉ đổi một tuple organization có thể để lại:

- Team editor của tenant cũ.
- Folder hoặc project parent thuộc tenant cũ.
- Owner không còn đủ điều kiện ở tenant mới.
- Link chia sẻ và đường truy cập file cũ.
- Cache, chỉ mục tìm kiếm hoặc dữ liệu audit đang gắn tenant cũ.

Một quy trình chuyển tenant cần xác định tập quan hệ được giữ, được chuyển hoặc bị thu hồi, cùng thứ tự cập nhật dữ liệu và graph.

Nếu không có transaction xuyên các hệ thống, có thể cần trạng thái tạm không phục vụ truy cập, cơ chế chuyển theo version hoặc một workflow có bước xác nhận nhất quán. Không khẳng định đã chuyển xong chỉ dựa trên việc một database ghi thành công.

Tác vụ chuyển cũng cần quyền rõ ràng ở cả phạm vi nguồn và đích theo chính sách của sản phẩm. Owner tài liệu chưa chắc có quyền xuất dữ liệu sang một khách hàng khác.

## 11. Cache, consistency và thu hồi tenant membership

### 11.1. Cache cần phản ánh phạm vi quyết định

Một khóa cache minh họa cho kết quả phân quyền có thể bao gồm:

~~~text
store_id
+ authorization_model_id
+ principal_id
+ active_tenant_context
+ resource_identity
+ relation_or_action
+ relevant_authorization_state
~~~

Đây là cấu trúc khái niệm. Những hệ thống dùng condition, contextual tuple hoặc mức bảo đảm phiên còn phải tính các đầu vào tương ứng.

Chỉ thêm tenant vào key chưa đủ nếu resource ID hoặc principal ID được chuẩn hóa sai. Ngược lại, resource ID duy nhất toàn cục cũng không làm active tenant trở nên thừa nếu quyết định phụ thuộc ngữ cảnh.

Cache dữ liệu cần được bảo vệ trước khi trả kết quả. Một object đã có trong cache không tự cho phép bỏ qua kiểm tra quyền của request hiện tại.

### 11.2. Thu hồi membership tổ chức

Trong model mục 5, xóa membership A của Lan sẽ làm mất org_participant A nếu Lan không còn đường participant khác, chẳng hạn admin A.

Dù tuple editor cũ còn tồn tại, can_edit và can_view sẽ không được suy ra cho Lan qua điều kiện org_participant khi đánh giá trên dữ liệu mới.

Đây là một đặc tính hữu ích của lớp eligibility, nhưng vẫn cần xử lý độ mới dữ liệu:

~~~text
Nguồn danh tính đã gỡ membership
    -> graph đã nhận thay đổi hay chưa?
    -> truy vấn có đọc cache cũ không?
    -> ứng dụng có giữ kết quả Allow cũ không?
    -> tác vụ dài có đánh giá lại quyền không?
~~~

Trong OpenFGA, HIGHER_CONSISTENCY bỏ qua cache của engine để truy vấn database; lựa chọn này không cập nhật thay một quan hệ còn chưa được đồng bộ tới database. [Query Consistency Modes](https://openfga.dev/docs/interacting/consistency).

Cam kết thu hồi cần tính cả pipeline dữ liệu, cache và những điểm thực thi, không chỉ một tham số trong lệnh Check.

### 11.3. Phiên, tác vụ nền và sự kiện

Một request trực tiếp, một job export chạy sau vài phút và một webhook không nhất thiết có cùng ngữ cảnh sẵn có.

Với tác vụ theo tenant, thông điệp cần mang hoặc tham chiếu tới phạm vi được producer xác thực, actor, object và action phù hợp. Consumer phải kiểm tra đường nhận thông điệp đáng tin, dựng lại ngữ cảnh và đánh giá quyền còn hiệu lực theo yêu cầu của thao tác.

Không dùng tenant mặc định khi thiếu context. Một job được phép chạy toàn nền tảng cần được nhận diện như một tác vụ có phạm vi toàn nền tảng, với quyền và logic riêng.

Khi một job phục vụ nhiều tenant, cần giữ phạm vi từng đơn vị công việc. Không để context của tenant trước còn trong biến toàn cục, thread local, connection hoặc cache rồi bị sử dụng cho tenant tiếp theo.

## 12. Bảo vệ các đường đọc ngoài endpoint chính

### 12.1. Truy vấn danh sách và tìm kiếm

Một endpoint mở tài liệu có kiểm tra can_view không bảo đảm endpoint tìm kiếm hoặc danh sách tài liệu cũng giữ đúng tenant scope.

Cần áp dụng phạm vi theo ngữ cảnh đã kiểm chứng và quyền object phù hợp. Không tải mọi tài liệu từ graph hoặc database chung rồi chỉ ẩn chúng ở giao diện.

Các thông tin như tiêu đề, số lượng kết quả, tên tác giả và đoạn trích cũng có thể là dữ liệu cần giới hạn. Việc che phần nội dung chính chưa đủ nếu metadata của tenant khác vẫn xuất hiện.

Nếu dùng một truy vấn liệt kê các object có quyền trong graph, vẫn phải giữ đúng store, context và ánh xạ object sang dữ liệu nghiệp vụ. Không lấy một danh sách quyền được tính không có active tenant rồi dùng nó cho endpoint chỉ phục vụ một tenant.

### 12.2. File và URL tải xuống

Một tài liệu có thể tham chiếu tới file trong object storage. Việc PDP cho phép đọc document không có nghĩa mọi đường tải file liên quan đều đã được bảo vệ.

Backend cần xác định file thuộc đúng tài liệu và tenant, rồi kiểm tra hành động trước khi tải hoặc tạo URL truy cập. Đường dẫn có prefix tenant chỉ là cách tổ chức tên nếu cơ chế truy cập không thực thi phạm vi ấy.

URL tải xuống có thời hạn cũng tạo một cửa sổ sử dụng quyền. Khi người dùng bị thu hồi membership, khả năng thu hồi URL phụ thuộc cơ chế lưu trữ và cách phát hành URL, không tự được giải quyết bằng việc xóa tuple trong graph.

### 12.3. Cùng phạm vi từ kiểm tra đến sử dụng

Một lỗi tích hợp thường gặp là kiểm tra quyền trên document A nhưng repository hoặc storage lại đọc object được chọn từ một tham số khác.

Cần gắn kết quả kiểm tra với đối tượng chuẩn hóa đã lấy từ nguồn tin cậy. Khi có thay đổi resource tenant, ownership hoặc parent giữa lúc kiểm tra và lúc sử dụng, phải xử lý theo cơ chế nhất quán của hệ thống.

Lớp lọc dữ liệu, ràng buộc database và phân quyền graph hỗ trợ các khía cạnh khác nhau. Không giả định một lớp bảo vệ có thể che mọi sai lệch định danh ở lớp khác.

## 13. Audit và điều tra sự cố tenant isolation

Một bản ghi quyết định cần cho phép phân biệt tenant của request, tenant chủ tài nguyên và store thực sự được truy vấn.

Ví dụ schema audit do bài học đề xuất:

~~~json
{
  "decision_id": "decision-705",
  "actor_id": "user:lan",
  "acting_service": "document-api",
  "active_tenant": "a",
  "resource_tenant": "a",
  "resource": "document:a-api-design",
  "requested_relation": "can_view",
  "authorization_store": "shared-production-store",
  "authorization_model": "model-release-17",
  "access_path": "INTERNAL_TENANT",
  "decision": "ALLOWED",
  "enforcement_outcome": "DOCUMENT_RETURNED"
}
~~~

Các giá trị chỉ phục vụ minh họa. ID store và model trong triển khai thực phải lấy từ cấu hình và lần đánh giá thực tế, không điền một nhãn mới nhất sau khi request đã hoàn tất.

Với luồng chia sẻ liên tenant, có thể bổ sung ID grant hoặc thông tin tham chiếu tới căn cứ chia sẻ. Không coi mọi trường hợp active_tenant khác resource_tenant là vi phạm nếu hệ thống đã cho phép một luồng cộng tác cụ thể.

Sự kiện ghi quan hệ cần nêu actor, tenant, object nguồn và đích, relation, nguồn thay đổi và kết quả ghi. Nếu pipeline đồng bộ có độ trễ, nên phân biệt nguồn chuẩn đã commit với graph đã áp dụng.

Dữ liệu audit tập trung có thể chứa thông tin của nhiều tenant. Quyền đọc log cũng phải theo phạm vi: admin A không tự được xem log của B, còn auditor nền tảng cần một quyền riêng phù hợp.

Khi điều tra, cần kiểm tra cả những khả năng:

- Request chọn sai tenant hoặc store.
- Graph có cạnh chia sẻ sai phạm vi.
- Người dùng có nhiều membership khiến lỗi bị che khuất.
- PDP đánh giá đúng nhưng repository đọc sai object.
- Cache giữ dữ liệu hoặc quyết định từ ngữ cảnh trước.
- Chia sẻ B2B hợp lệ bị phân loại nhầm là lỗi.
- Membership đã thu hồi ở nguồn nhưng chưa có hiệu lực trên đường thực thi.

Không ghi token, credential hoặc toàn bộ nội dung khách hàng vào audit chỉ để có thêm ngữ cảnh. Giữ những định danh và bằng chứng cần thiết trong phạm vi được kiểm soát.

## 14. Ma trận kiểm thử cần thiết

Những kiểm thử dưới đây là đề xuất cho thiết kế trong bài, chưa phải kết quả chạy một hệ thống cụ thể. Cần có cả kiểm thử model, dữ liệu quan hệ và lớp tích hợp thực thi.

| Tình huống | Điều cần khẳng định |
| --- | --- |
| Lan có quyền tài liệu A, request trong A | Được can_view và được đọc đúng tài liệu |
| Lan có quyền A nhưng request nội bộ đang ở B | Request không sử dụng quyền A để vượt phạm vi B |
| Bảo chỉ thuộc B và chỉ có team B | Không được đọc tài liệu A |
| Hai tenant có cùng local document ID | Ánh xạ và truy vấn không nhầm object |
| User có membership A và B, chỉ có quyền trong B | Không tự có quyền trên tài nguyên A |
| Cố chia sẻ nội bộ tài liệu A cho team B | API từ chối trước khi ghi quan hệ |
| Chèn cạnh sai vào dữ liệu kiểm thử | Phát hiện model nào có thể Allow và kiểm tra cơ chế bảo vệ bổ sung |
| Một document có hai organization | Bị chặn ở đường ghi hoặc bị phát hiện theo quy trình kiểm tra dữ liệu |
| Chỉ có org membership, không có quyền tài liệu | Không được đọc mọi tài liệu trong tổ chức |
| Owner rời organization và không còn participant khác | Các quyền can_* không tiếp tục qua điều kiện participant |
| Admin A gọi API quản trị object B | Không được dùng quyền admin A ở phạm vi B |
| Client tự chọn storeId hoặc modelId khác | Backend sử dụng mapping và cấu hình được kiểm soát |
| Cache Allow được tạo ở ngữ cảnh A | Không tái sử dụng sai cho ngữ cảnh B |
| Chia sẻ B2B chỉ cấp viewer | Không tự có editor, can_share hoặc quyền chuyển ownership |
| Grant B2B hết hiệu lực | Đường chia sẻ tương ứng không còn cấp quyền theo cam kết freshness |
| Engine timeout hoặc lỗi đánh giá | Không cho thực hiện thao tác khi chưa có kết quả cho phép hợp lệ |
| Job chạy sau khi actor bị thu hồi quyền | Xử lý theo quy định đánh giá lại của tác vụ |
| Chuyển tài nguyên từ A sang B | Không giữ các grant cũ trái chính sách đích |

Ca user nhiều tenant là bắt buộc đối với những sản phẩm hỗ trợ nhiều membership. Nếu chỉ kiểm tra user A riêng và user B riêng, điều kiện giao với membership tenant có thể che một cạnh sai thay vì chứng minh toàn bộ graph được cách ly.

Kiểm thử trực tiếp graph có thể cho thấy một quan hệ sai vẫn tạo Allow. Khi thiết kế dựa một phần vào validation của nguồn chuẩn, cần kiểm thử chính cơ chế ngăn quan hệ đó và bảo đảm không có đường ghi khác bỏ qua validation.

Ngoài quyết định phân quyền, cần kiểm tra nội dung thực sự trả về, object storage, endpoint danh sách, kết quả tìm kiếm và audit. Một lần Check đúng không chứng minh toàn bộ request dùng đúng tài nguyên.

## 15. Những lỗi tư duy dễ dẫn đến truy cập sai tenant

| Suy luận sai | Vấn đề | Điều cần kiểm chứng |
| --- | --- | --- |
| Có tenant ID trong mọi object là đã cách ly | ID không tự ràng buộc đường quan hệ | Cấu trúc graph, đường ghi và điểm thực thi |
| User là member A nên đọc được mọi dữ liệu A | Membership chỉ là một điều kiện eligibility | Quyền trên từng object và action |
| Có giao với member A thì mọi cạnh đều thuộc A | User nhiều tenant có thể đi qua cạnh sai | Tenant của team, parent và tài nguyên ở các cạnh liên quan |
| Tách store thì không cần kiểm tra tenant | Backend vẫn có thể định tuyến nhầm | Mapping tin cậy và phạm vi credential |
| Có owner thì được chuyển tài nguyên sang tenant khác | Ownership object không bằng quyền di chuyển dữ liệu khách hàng | Quyền nguồn, quyền đích và chính sách migration |
| Có chia sẻ B2B thì bỏ lọc tenant cho mọi endpoint | Mở rộng phạm vi ngoài tài nguyên được cấp | Luồng chia sẻ rõ ràng cho đúng object |
| Chỉ cần sửa graph khi thu hồi quyền | Cache, phiên và job có thể giữ trạng thái cũ | Freshness trên toàn đường thực thi |

## 16. Bài tập vận dụng

### Tình huống 1: Cạnh sai nhưng membership đúng

Hà là participant của A và B, là member team Backend B. Một lỗi đồng bộ ghi team Backend B thành editor tài liệu A.

Theo model mục 5, hãy chỉ ra vì sao org_participant A không đủ để chặn quyền của Hà. Xác định đường ghi cần ràng buộc tenant và cách phát hiện dữ liệu graph sai đã tồn tại.

### Tình huống 2: Chuyển ngữ cảnh khi người dùng thuộc nhiều tổ chức

Lan có quyền chỉnh sửa tài liệu A nhưng đang mở workspace B. Một request nội bộ gửi document ID của A.

Hãy xác định các điểm chặn trong tenant context, repository lookup và authorization context. Sau đó phân tích trường hợp có một endpoint cộng tác B2B được thiết kế riêng: những điều kiện nào phải thay đổi và những điều kiện nào vẫn cần giữ?

### Tình huống 3: Store đúng, database sai

Backend chọn đúng store của A và nhận Allow cho một tài liệu A. Repository chỉ truy vấn theo local document ID, vốn có thể trùng giữa A và B.

Giải thích vì sao kết quả phân quyền đúng vẫn có thể dẫn đến trả sai dữ liệu. Đề xuất cách gắn định danh được kiểm tra với truy vấn và file thực sự được sử dụng.

### Tình huống 4: Thu hồi đối tác

A đã chia sẻ viewer cho một nhóm đối tác của B. A muốn dừng chia sẻ ngay sau khi hợp đồng kết thúc.

Hãy lập danh sách những dữ kiện và trạng thái liên quan: grant, membership của nhóm, bản chiếu graph, cache quyết định, URL tải xuống đã phát hành và tác vụ export đang chạy. Xác định thời điểm nào hệ thống có thể xác nhận việc thu hồi theo đúng cam kết.

ReBAC giúp biểu diễn quyền theo quan hệ tài nguyên một cách linh hoạt. Trong multi-tenant, tính linh hoạt đó cần đi cùng ranh giới dữ liệu rõ ràng: xác định đúng tenant, giữ đúng cấu trúc graph và thực thi trên chính đối tượng đã được kiểm tra.
