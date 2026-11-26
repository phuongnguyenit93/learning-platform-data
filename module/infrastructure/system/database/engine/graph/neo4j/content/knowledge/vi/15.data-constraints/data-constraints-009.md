# Phối hợp ràng buộc với MERGE để hạn chế trùng lặp khi ghi đồng thời

## 1. Bài toán: hai yêu cầu tạo cùng một thực thể

Neo4j lưu dữ liệu theo **property graph**: node đại diện cho thực thể, relationship đại diện cho liên kết, còn property lưu thông tin của từng đối tượng. Trong hệ thống có nhiều luồng xử lý, một thực thể nghiệp vụ có thể được ghi đồng thời bởi nhiều request HTTP, worker xử lý hàng đợi hoặc tác vụ nhập dữ liệu.

Ví dụ, dịch vụ đồng bộ khách hàng nhận hai thông điệp có cùng mã **externalId = 'crm-2048'**. Mục tiêu là **chỉ có một node Customer** cho mã này, dù hai thông điệp được xử lý gần như cùng lúc.

Cypher có lệnh **MERGE** để tìm một mẫu đồ thị đã tồn tại hoặc tạo mẫu đó nếu chưa có:

~~~cypher
MERGE (c:Customer {externalId: $externalId})
RETURN c;
~~~

MERGE rất phù hợp với thao tác **upsert** (tìm hoặc tạo). Tuy nhiên, chỉ viết MERGE **không thay thế** được quy tắc toàn vẹn dữ liệu khi nhiều giao dịch đồng thời cùng tìm và tạo một khóa chưa tồn tại.

Giải pháp thực tế là phối hợp:

1. **Chọn một khóa nghiệp vụ ổn định** dùng để nhận diện node.
2. **Tạo uniqueness constraint** trên đúng nhãn và property của khóa đó.
3. **MERGE theo khóa đã được ràng buộc**, sau đó mới ghi các property có thể thay đổi.
4. **Thiết kế giao dịch và chính sách xử lý lỗi/retry** cho các tình huống cạnh tranh.
5. **Kiểm tra kết quả bằng truy vấn và thử tải đồng thời**, không suy luận từ việc một lần chạy tuần tự thành công.

Bài học tập trung vào mô hình dữ liệu, Cypher, constraint và luồng ghi đồng thời trong Neo4j; ví dụ Java Driver minh họa cách áp dụng trong ứng dụng.

## 2. MERGE làm gì và không bảo đảm điều gì?

### 2.1. Tìm toàn bộ mẫu, nếu chưa thấy thì tạo

~~~cypher
MERGE (c:Customer {externalId: 'crm-2048'})
RETURN c.externalId AS externalId;
~~~

Trong một lần thực thi:

- Nếu tìm thấy node **Customer** khớp mẫu, MERGE dùng node đó.
- Nếu không tìm thấy, MERGE tạo node **Customer** mang property **externalId** tương ứng.

Chạy lại tuần tự cùng câu lệnh thường sẽ trả về node vừa tạo. Đây là hành vi thuận tiện cho thao tác ghi lặp lại. Nhưng câu lệnh không có nghĩa rằng cơ sở dữ liệu đã được yêu cầu **cấm mọi node Customer trùng externalId**.

Không nên hiểu MERGE là một constraint. **MERGE quyết định cách truy vấn xử lý một mẫu; constraint quyết định trạng thái dữ liệu nào được phép tồn tại.**

### 2.2. Tại sao vẫn có nguy cơ trùng trong ghi đồng thời?

Giả sử ban đầu chưa có Customer mang mã **crm-2048**. Hai giao dịch **T1** và **T2** đều muốn MERGE cùng khóa này.

| Thời điểm minh họa | Giao dịch T1 | Giao dịch T2 |
|---|---|---|
| 1 | Tìm Customer theo externalId | Tìm Customer theo externalId |
| 2 | Chưa thấy bản ghi khớp | Chưa thấy bản ghi khớp |
| 3 | Chuẩn bị tạo Customer | Chuẩn bị tạo Customer |
| 4 | Cạnh tranh ghi dữ liệu | Cạnh tranh ghi dữ liệu |

Khi **không có uniqueness constraint**, không có một quy tắc toàn vẹn ở cấp cơ sở dữ liệu buộc số node mang cùng khóa phải bằng một. Tùy kế hoạch thực thi và cách các giao dịch đan xen, có thể xuất hiện nhiều node cùng khóa. Thao tác đơn lẻ được thực hiện trong giao dịch không tự động giải quyết tính duy nhất của một khóa nghiệp vụ qua tất cả các giao dịch.

Khi **có uniqueness constraint**, Neo4j phải duy trì bất biến: **không được có hai node cùng nhãn Customer và cùng giá trị externalId không-null**. Cơ chế điều phối ghi có thể khiến một giao dịch chờ và tìm thấy node đã tạo; trong một số tình huống xung đột, một giao dịch có thể nhận lỗi và cần được xử lý lại. Điều phải bảo đảm ở đây là **không commit được hai node vi phạm constraint**, chứ không phải mọi request cạnh tranh đều chắc chắn thành công ngay lần đầu.

## 3. Khai báo uniqueness constraint trước khi triển khai MERGE

### 3.1. Tạo ràng buộc cho khóa nghiệp vụ

Ví dụ một khách hàng được nhận diện duy nhất bằng **externalId**:

~~~cypher
CREATE CONSTRAINT customer_external_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.externalId IS UNIQUE;
~~~

Constraint quy định rằng hai node cùng nhãn **Customer** không được có cùng giá trị property **externalId** khi property đó tồn tại.

Để quan sát các constraint đang có:

~~~cypher
SHOW CONSTRAINTS;
~~~

Hãy tạo constraint bằng migration hoặc bước quản trị schema được kiểm soát, trước khi cho phép nhiều worker cùng ghi. **IF NOT EXISTS** hỗ trợ chạy lại câu lệnh tạo schema trong trường hợp phù hợp, nhưng không thay thế việc kiểm tra constraint thực tế có đúng loại, nhãn và property mà ứng dụng cần.

### 3.2. Dữ liệu đã trùng thì sao?

Nếu cơ sở dữ liệu đã chứa nhiều Customer có cùng externalId, việc thêm uniqueness constraint tương ứng sẽ thất bại. Kiểm tra trước:

~~~cypher
MATCH (c:Customer)
WHERE c.externalId IS NOT NULL
WITH c.externalId AS externalId, count(c) AS soLuong
WHERE soLuong > 1
RETURN externalId, soLuong
ORDER BY soLuong DESC, externalId
LIMIT 20;
~~~

Tìm các bản ghi trùng là bước **phát hiện**. Cách hợp nhất dữ liệu phải theo nghiệp vụ: một node có thể đang giữ relationship, lịch sử giao dịch hoặc metadata không được phép mất. Không nên tự động DETACH DELETE các node trùng mà chưa xét tác động đến các relationship.

### 3.3. Uniqueness không đồng nghĩa property bắt buộc tồn tại

Với uniqueness constraint thông thường, các node **không có property externalId** không bị coi là trùng khóa chỉ vì cùng thiếu property. Điều này tạo ra hai quy tắc khác nhau:

- **Tính duy nhất:** khi có externalId, không được trùng giá trị với node Customer khác.
- **Tính bắt buộc:** mọi Customer đều phải có externalId.

Nếu bài toán cần đồng thời cả hai, hãy xem xét **node key constraint** hoặc kết hợp ràng buộc tồn tại property tùy phiên bản và edition Neo4j; các loại constraint này có yêu cầu hỗ trợ và cú pháp riêng. Ngoài ra, ứng dụng vẫn nên kiểm tra đầu vào trước khi gọi MERGE.

Một tham số khóa là **null** không phải là "khóa rỗng hợp lệ" cho mẫu MERGE: MERGE dùng property null trong mẫu sẽ báo lỗi. Dữ liệu thiếu mã định danh cần được từ chối hoặc định tuyến xử lý trước khi xây dựng truy vấn ghi.

## 4. Viết MERGE đúng theo khóa nhận diện

### 4.1. MERGE trên khóa, cập nhật property còn lại

~~~cypher
MERGE (c:Customer {externalId: $externalId})
ON CREATE SET
    c.name = $name,
    c.createdAt = datetime(),
    c.source = 'crm'
ON MATCH SET
    c.name = $name,
    c.lastSyncedAt = datetime()
RETURN c.externalId AS externalId,
       c.name AS name,
       c.createdAt AS createdAt;
~~~

Với constraint ở phần trước, mẫu **Customer + externalId** vừa thể hiện đúng định danh, vừa được bảo vệ khỏi trùng khóa khi cạnh tranh ghi.

- **ON CREATE** chỉ chạy khi MERGE tạo node mới.
- **ON MATCH** chỉ chạy khi MERGE khớp node hiện có.
- **createdAt** được thiết lập khi tạo, tránh ghi lại thời điểm tạo trong mỗi lần đồng bộ.
- **name** là thông tin có thể đổi, được cập nhật khi gặp lại khách hàng.

Các trường có thể thay đổi được ghi bằng SET; chúng không tham gia mẫu nhận diện của MERGE.

### 4.2. Phản ví dụ: đưa cả dữ liệu biến động vào MERGE

~~~cypher
MERGE (c:Customer {
    externalId: $externalId,
    name: $name
})
RETURN c;
~~~

Giả sử đã có Customer **externalId = 'crm-2048', name = 'Lan'**, còn request mới mang **name = 'Lan Nguyễn'**. Mẫu MERGE trên **cả hai property** không khớp node cũ, nên có thể cố tạo node khác.

- **Nếu không có constraint:** dễ tạo hai node có cùng externalId, khác name.
- **Nếu có uniqueness constraint trên externalId:** thao tác tạo vi phạm constraint và thất bại; MERGE không tự hiểu rằng **name** chỉ là trường cần cập nhật.

Viết đúng:

~~~cypher
MERGE (c:Customer {externalId: $externalId})
SET c.name = $name
RETURN c;
~~~

Điểm khác biệt là **khóa nhận diện không đổi**, còn dữ liệu mô tả được cập nhật.

### 4.3. Chuẩn hóa khóa trước khi MERGE

Hai chuỗi **'User@Example.com'** và **'user@example.com'** khác nhau khi so sánh chuỗi chính xác. Constraint trên property thông thường bảo vệ **giá trị được lưu**, không tự suy diễn rằng hai cách viết đó là cùng một danh tính.

Nếu nghiệp vụ coi email không phân biệt hoa thường, có thể lưu một khóa chuẩn hóa riêng:

~~~cypher
MERGE (u:AppUser {emailNormalized: toLower(trim($email))})
ON CREATE SET u.emailOriginal = $email,
              u.createdAt = datetime()
RETURN u.emailNormalized AS emailKey;
~~~

Cần tạo uniqueness constraint tương ứng trên **AppUser.emailNormalized**, đồng thời thống nhất quy tắc chuẩn hóa ở mọi dịch vụ ghi. Một phép chuẩn hóa phù hợp với email không tự động phù hợp với số điện thoại, mã đơn hàng hoặc định danh phân biệt chữ hoa và chữ thường.

## 5. Mô hình nhiều tenant: khóa tổng hợp

Trong hệ thống đa khách hàng tổ chức, mã **externalId = '001'** có thể xuất hiện hợp lệ ở hai tenant khác nhau. Khi đó, định danh đúng là cặp **(tenantId, externalId)** chứ không chỉ externalId.

~~~cypher
CREATE CONSTRAINT customer_tenant_external_unique IF NOT EXISTS
FOR (c:TenantCustomer)
REQUIRE (c.tenantId, c.externalId) IS UNIQUE;
~~~

MERGE dùng đúng cặp khóa:

~~~cypher
MERGE (c:TenantCustomer {
    tenantId: $tenantId,
    externalId: $externalId
})
ON CREATE SET c.createdAt = datetime()
SET c.name = $name
RETURN c.tenantId AS tenantId,
       c.externalId AS externalId;
~~~

Giá trị **tenantId** phải luôn có mặt và đáng tin cậy trong request. Nếu chỉ MERGE theo externalId, ứng dụng có thể nhầm hai khách hàng thuộc hai tenant thành một thực thể.

**Lưu ý với composite uniqueness:** nếu một thành phần của khóa vắng mặt, constraint duy nhất tổng hợp không tự đảm bảo rằng node đã có đủ mọi thành phần. Cần kiểm tra đầu vào và cân nhắc thêm ràng buộc bắt buộc tồn tại property theo khả năng của phiên bản/edition.

Đừng đồng thời tạo một constraint **externalId duy nhất toàn cục** cho cùng nhãn nếu nghiệp vụ cho phép externalId trùng giữa các tenant: hai quy tắc sẽ mâu thuẫn.

## 6. Phối hợp MERGE node với MERGE relationship

Trong property graph, việc chống trùng node chưa tự động xử lý mọi nguy cơ trùng relationship. Ví dụ cần ghi rằng một người dùng thuộc một nhóm:

~~~cypher
CREATE CONSTRAINT app_user_id_unique IF NOT EXISTS
FOR (u:AppUser)
REQUIRE u.userId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT team_id_unique IF NOT EXISTS
FOR (t:Team)
REQUIRE t.teamId IS UNIQUE;
~~~

Sau khi schema đã sẵn sàng, trong một transaction:

~~~cypher
MERGE (u:AppUser {userId: $userId})
MERGE (t:Team {teamId: $teamId})
MERGE (u)-[m:MEMBER_OF]->(t)
ON CREATE SET m.joinedAt = datetime()
RETURN u.userId AS userId,
       t.teamId AS teamId,
       m.joinedAt AS joinedAt;
~~~

Thứ tự này có chủ đích:

1. MERGE từng **node theo khóa được ràng buộc**.
2. Khi đã có biến **u** và **t** trỏ đến hai node cụ thể, MERGE relationship giữa chúng.
3. Đặt **joinedAt** khi tạo mới để không thay đổi thời điểm gia nhập mỗi lần nhận sự kiện lặp.

Tránh dùng một MERGE cho **toàn bộ đường nối** khi định danh của hai đầu mút cần được kiểm soát riêng:

~~~cypher
// KHÔNG phải cách thông dụng để upsert hai node đã có định danh riêng.
MERGE (u:AppUser {userId: $userId})
      -[:MEMBER_OF]->
      (t:Team {teamId: $teamId});
~~~

MERGE tìm hoặc tạo **toàn bộ mẫu**. Khi đường nối chưa có, nó có thể cố tạo các thành phần không mong muốn; constraint có thể khiến câu lệnh thất bại thay vì tự ghép đúng các node tồn tại. MERGE node riêng trước giúp biểu đạt rõ ý định.

**Giới hạn concurrency của relationship:** uniqueness constraint trên **AppUser.userId** và **Team.teamId** chỉ bảo vệ các node, không đồng nghĩa có quy tắc duy nhất cho từng cặp đầu mút và loại relationship. Nếu nghiệp vụ bắt buộc **không bao giờ có hai MEMBER_OF cho cùng một cặp**, cần thiết kế thêm cơ chế bảo vệ phù hợp: chẳng hạn định danh riêng cho membership, ràng buộc property relationship khi phiên bản Neo4j hỗ trợ và/hoặc điều phối giao dịch. Không nên kết luận rằng mọi mẫu MERGE relationship song song đều bảo đảm duy nhất nếu không có constraint tương ứng.

## 7. Ghi đồng thời: dữ liệu đúng vẫn có thể phát sinh lỗi tạm thời

### 7.1. Phân biệt bất biến dữ liệu và kết quả từng request

Giả sử có uniqueness constraint trên **Customer.externalId**, và hai luồng đều chạy:

~~~cypher
MERGE (c:Customer {externalId: 'crm-2048'})
ON CREATE SET c.name = 'Lan'
RETURN c.externalId;
~~~

Có nhiều kết quả thực thi hợp lệ tùy cạnh tranh và cơ chế khóa:

- Luồng đầu tạo node, luồng sau tìm thấy cùng node.
- Một luồng phải chờ tài nguyên hoặc một giao dịch bị yêu cầu thử lại.
- Một giao dịch trả lỗi xung đột/ràng buộc; ứng dụng xử lý lỗi và kiểm tra lại theo khóa.

Trong mọi tình huống **mà constraint còn hiệu lực**, không thể commit hai Customer có cùng **externalId = 'crm-2048'**. Đó là bảo đảm dữ liệu cần ưu tiên.

Không được hứa rằng hai request đồng thời luôn trả thành công ngay lần đầu. Đặc biệt, nếu câu MERGE tham chiếu nhiều property có constraint duy nhất khác nhau, việc khớp một phần có thể tạo ra lỗi ràng buộc cần xử lý như một vấn đề dữ liệu.

### 7.2. Tránh nhập nhằng khi có nhiều constraint

Giả sử tồn tại hai constraint riêng biệt:

~~~cypher
CREATE CONSTRAINT employee_id_unique IF NOT EXISTS
FOR (e:Employee)
REQUIRE e.employeeId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT employee_email_unique IF NOT EXISTS
FOR (e:Employee)
REQUIRE e.emailNormalized IS UNIQUE;
~~~

Một câu lệnh sau có thể khó xử lý:

~~~cypher
MERGE (e:Employee {
    employeeId: $employeeId,
    emailNormalized: $emailNormalized
});
~~~

Ví dụ đã có node với **employeeId = 'E-7'**, nhưng email vừa đổi. MERGE không khớp **toàn bộ mẫu**, rồi cố tạo node mang ID đã tồn tại, dẫn tới vi phạm constraint. Hoặc email đã thuộc về một nhân viên khác.

Nên chọn một định danh làm khóa chính cho MERGE, sau đó cập nhật email theo chính sách nghiệp vụ:

~~~cypher
MERGE (e:Employee {employeeId: $employeeId})
ON CREATE SET e.createdAt = datetime()
SET e.emailNormalized = toLower(trim($email))
RETURN e.employeeId;
~~~

Nếu email mới đã được node khác sử dụng, **email uniqueness constraint** sẽ báo vi phạm. Đây là tín hiệu xung đột nghiệp vụ cần giải quyết; **không** retry vô hạn cùng dữ liệu sai.

### 7.3. Mọi request đều cần xác định lại trạng thái sau lỗi

Một chiến lược xử lý có thể chia theo loại lỗi:

| Nhóm kết quả | Hành động gợi ý |
|---|---|
| Commit thành công | Trả khóa nghiệp vụ và dữ liệu cần thiết cho caller |
| Lỗi tạm thời do khóa/giao dịch, được driver nhận diện là transient | Retry toàn bộ transaction với số lần/thời gian giới hạn, có backoff phù hợp |
| Lỗi uniqueness vì có tiến trình khác ghi cùng định danh | Đọc lại theo **đúng khóa nghiệp vụ**, kiểm tra node hiện tại; quyết định coi là kết quả thành công hay xử lý xung đột |
| Lỗi uniqueness của khóa **khác**, ví dụ email đã thuộc người khác | Trả lỗi nghiệp vụ hoặc đưa vào quy trình giải quyết xung đột |
| Giá trị khóa null/không hợp lệ | Từ chối đầu vào, không chạy MERGE |

**Retry phải an toàn khi thực thi lại**: một lần thử có thể đã ghi hoặc một lần thử khác đã tạo node. Vì vậy, MERGE theo khóa bền vững và các cập nhật có chủ đích quan trọng hơn thao tác CREATE mù.

Nếu transaction vừa tạo node vừa gọi dịch vụ bên ngoài, không thực hiện tác dụng phụ ngoài cơ sở dữ liệu bên trong callback mà driver có thể chạy lại; có thể phát sinh nhiều lần gửi email, trừ tiền hoặc gọi API. Hãy tách các tác dụng phụ và dùng cơ chế idempotency/outbox khi cần.

## 8. Ví dụ từ Java Driver

Java Driver cho phép chạy Cypher trong managed transaction. Đoạn sau minh họa cách dùng **MERGE** nhất quán với constraint **customer_external_id_unique** đã được tạo sẵn:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.Values;

public final class CustomerWriter {
    private final Driver driver;

    public CustomerWriter(Driver driver) {
        this.driver = driver;
    }

    public String upsertCustomer(String externalId, String name) {
        if (externalId == null || externalId.isBlank()) {
            throw new IllegalArgumentException("externalId is required");
        }

        try (Session session =
                 driver.session(SessionConfig.forDatabase("neo4j"))) {

            return session.executeWrite(tx -> {
                var result = tx.run(
                    """
                    MERGE (c:Customer {externalId: $externalId})
                    ON CREATE SET c.createdAt = datetime()
                    SET c.name = $name
                    RETURN c.externalId AS externalId
                    """,
                    Values.parameters(
                        "externalId", externalId,
                        "name", name
                    )
                );
                return result.single().get("externalId").asString();
            });
        }
    }
}
~~~

Những điểm cần lưu ý:

- **Driver** thường được quản lý và tái sử dụng ở cấp ứng dụng; **Session** nên có vòng đời ngắn, không chia sẻ tùy tiện giữa các thread.
- **executeWrite** dùng transaction được driver quản lý và hỗ trợ retry đối với những lỗi tạm thời mà driver xác định là có thể retry, theo cấu hình. Không phải mọi lỗi constraint đều được tự động retry.
- **Values.parameters** truyền giá trị theo tham số, tránh ghép chuỗi Cypher từ input.
- **RETURN c.externalId** trả về khóa nghiệp vụ, giúp caller không phụ thuộc vào ID nội bộ của graph.
- **SET c.name = $name** cho phép request ghi sau cập nhật tên; nếu có xung đột cập nhật, ứng dụng phải quyết định chính sách nguồn dữ liệu ưu tiên, version hoặc timestamp.

Trong ứng dụng Spring Data Neo4j, các thao tác repository hoặc transaction cũng cần tuân thủ cùng các ràng buộc dữ liệu ở cơ sở dữ liệu. Tên phương thức như **save** hay cấu trúc entity phía Java không thay thế uniqueness constraint cho tình huống ghi đồng thời.

## 9. Nhập dữ liệu lặp lại và xử lý theo lô

Nguồn CSV, sự kiện từ message broker hoặc đồng bộ CRM thường có tình trạng **ít nhất một lần gửi** (*at-least-once delivery*). Cùng bản ghi có thể đến nhiều lần, thậm chí đồng thời trên các worker.

Một mẫu Cypher có thể dùng UNWIND để cập nhật nhiều khách hàng:

~~~cypher
UNWIND $rows AS row
MERGE (c:Customer {externalId: row.externalId})
ON CREATE SET c.createdAt = datetime()
SET c.name = row.name,
    c.lastSyncedAt = datetime()
RETURN count(c) AS soDongDaXuLy;
~~~

Ý nghĩa của kết quả: **soDongDaXuLy** đếm số hàng dữ liệu đầu vào được xử lý qua truy vấn, **không** phải số Customer mới tạo. Nếu danh sách chứa 100 dòng với 20 khóa trùng, con số này không phản ánh số node khác nhau.

Với dữ liệu nhập theo lô:

1. Kiểm tra **externalId** không null/rỗng và chuẩn hóa định dạng khóa trước khi nhập.
2. Nếu có nhiều dòng cùng khóa nhưng giá trị khác nhau, xác định quy tắc chọn dòng cuối theo phiên bản hoặc thời gian sự kiện; không dựa vào thứ tự xử lý ngẫu nhiên.
3. Ghi theo các lô có kích thước hợp lý để giới hạn thời gian transaction và giảm cạnh tranh trên tập khóa nóng.
4. Không xóa uniqueness constraint chỉ để tăng tốc nhập: điều đó đánh đổi bất biến dữ liệu lấy hiệu năng tạm thời.
5. Nếu tải lớn, điều chỉnh kích thước lô và mức độ song song dựa trên số khóa trùng, contention, hiệu năng ghi và giới hạn tài nguyên.

Nếu nghiệp vụ yêu cầu **chỉ cập nhật khi sự kiện mới hơn**, SET vô điều kiện ở ví dụ là chưa đủ. Khi đó cần lưu version/timestamp và thiết kế một phép cập nhật có điều kiện trong transaction, đồng thời xử lý xung đột với các sự kiện đến không theo thứ tự.

## 10. Kiểm tra constraint và kết quả thực tế

### 10.1. Kiểm tra schema

~~~cypher
SHOW CONSTRAINTS;
~~~

Xác nhận constraint trên đúng **nhãn Customer**, **property externalId** và kiểu **UNIQUE**. Môi trường phát triển, staging và production phải có cùng migration schema theo yêu cầu ứng dụng.

### 10.2. Quan sát kế hoạch truy vấn

~~~cypher
EXPLAIN
MERGE (c:Customer {externalId: $externalId})
RETURN c.externalId;
~~~

EXPLAIN hiển thị kế hoạch mà không chạy câu lệnh ghi. Khi khóa có index/constraint phù hợp, kế hoạch có thể tận dụng cấu trúc tra cứu duy nhất; tên toán tử và hình dạng kế hoạch khác nhau tùy phiên bản Neo4j.

Không dùng **PROFILE** như một cách xem thử an toàn đối với truy vấn ghi trên dữ liệu thật, bởi PROFILE **thực thi** truy vấn.

### 10.3. Kiểm chứng số node cùng khóa

Sau khi hai hoặc nhiều worker cùng upsert một mã:

~~~cypher
MATCH (c:Customer {externalId: 'crm-2048'})
RETURN count(c) AS soNodeCungKhoa,
       collect(c.name) AS tenHienCo;
~~~

Với khóa hợp lệ, constraint đúng và một bản ghi đã được tạo thành công, kết quả mong muốn là **soNodeCungKhoa = 1**. Số lượng bằng 0 có thể có nghĩa tất cả lần ghi đều thất bại hoặc chưa commit. Nếu lớn hơn 1, cần kiểm tra lại schema/nhãn/property và trạng thái dữ liệu.

Trên một database dùng thử riêng, có thể mở hai phiên Neo4j hoặc chạy nhiều task Java song song, cùng MERGE một **externalId**, sau đó kiểm tra số node và ghi nhận lỗi hoặc retry. **Một lần chạy tuần tự thành công không chứng minh đúng dưới concurrency**; thử đồng thời giúp phát hiện lỗi quy trình dù constraint mới là thành phần thực thi bất biến duy nhất ở cấp cơ sở dữ liệu.

### 10.4. Kiểm tra trùng trên toàn nhãn

~~~cypher
MATCH (c:Customer)
WHERE c.externalId IS NOT NULL
WITH c.externalId AS externalId, count(*) AS n
WHERE n > 1
RETURN externalId, n
ORDER BY n DESC
LIMIT 20;
~~~

Nếu truy vấn phát hiện các nhóm trùng, cần đối chiếu đúng database và constraint đang triển khai. Cũng nên rà soát các node Customer **thiếu externalId** vì uniqueness constraint đơn thuần không chặn tình trạng thiếu khóa.

## 11. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
|---|---|---|
| Dùng CREATE cho event có thể gửi lại | Mỗi lần nhận có thể tạo node mới | MERGE theo khóa nghiệp vụ và tạo constraint |
| Chỉ dùng MERGE, bỏ uniqueness constraint | Có thể trùng node khi ghi cạnh tranh | Constraint duy nhất ở database trên đúng khóa |
| MERGE theo cả name, status hoặc thuộc tính thay đổi | Thay đổi mô tả khiến mẫu không khớp, có thể tạo trùng hoặc lỗi | MERGE khóa ổn định, SET dữ liệu biến động |
| Khóa không chuẩn hóa nhất quán | Các biểu diễn khác nhau thành các giá trị khác nhau | Chuẩn hóa trước khi ghi, ràng buộc khóa đã chuẩn hóa |
| Composite key thiếu tenantId | Ghép nhầm thực thể giữa các tenant | Constraint và MERGE trên cùng cặp tenantId + externalId |
| Hiểu UNIQUE là NOT NULL | Vẫn có node thiếu khóa | Kiểm tra đầu vào và cân nhắc constraint tồn tại/node key |
| Cho rằng constraint node ngăn trùng mọi relationship | Vẫn có thể có nhiều relationship có cùng ý nghĩa | Thiết kế định danh và bảo vệ riêng cho relationship |
| Retry vô hạn mọi lỗi | Xung đột nghiệp vụ tồn tại mãi, tải hệ thống tăng | Phân loại lỗi, retry có giới hạn, kiểm tra sau xung đột |
| Thay đổi name bằng SET trong hai request và nghĩ có thứ tự cố định | Ghi sau có thể ghi đè giá trị mong muốn | Quy tắc version/updatedAt hoặc điều kiện cập nhật |
| Tạo constraint sau khi đã nhập dữ liệu trùng | Migration thất bại | Phát hiện và hợp nhất trùng trước khi tạo constraint |

## 12. Tình huống luyện tập

**Tình huống A — đồng bộ cùng mã khách hàng.** Hai worker đồng thời nhận thông điệp cho **externalId = 'crm-2048'**, cùng chạy MERGE theo externalId. Cơ sở dữ liệu có uniqueness constraint phù hợp. Có được phép xuất hiện hai node đã commit cùng khóa không?

**Đáp án:** Không. Một hoặc cả hai request có thể cần chờ, retry hoặc xử lý lỗi, nhưng constraint phải ngăn trạng thái commit có hai node Customer cùng khóa không-null.

**Tình huống B — đổi tên khách hàng.** Một Customer đã có tên "Mai", bản đồng bộ mới là "Mai Phạm". Có nên đặt **name** trong map của MERGE không?

**Đáp án:** Không nếu name là dữ liệu có thể thay đổi. MERGE theo khóa ổn định (chẳng hạn externalId) rồi SET name.

**Tình huống C — hai tenant cùng mã ngoài.** Tenant A và tenant B đều có khách hàng mã **007**. Constraint trên property nào phù hợp?

**Đáp án:** Composite uniqueness trên **(tenantId, externalId)** cho nhãn được dùng; MERGE phải dùng đủ hai trường.

**Tình huống D — lỗi uniqueness khi cập nhật email.** Nhân viên E-7 thay email thành giá trị đã thuộc E-9. Có nên retry vô hạn cùng truy vấn?

**Đáp án:** Không. Đây là xung đột nghiệp vụ trên email, khác với lỗi tạm thời có thể tự hồi phục. Ứng dụng cần trả về lỗi hoặc xử lý quy tắc chuyển giao email.

**Tình huống E — relationship thành viên.** Các node User và Team đều có uniqueness constraint trên ID. Điều đó đã đủ chứng minh không có hai relationship MEMBER_OF giữa cùng cặp node dưới mọi lịch ghi đồng thời chưa?

**Đáp án:** Chưa. Uniqueness của ID node không tự định nghĩa uniqueness cho relationship. Cần cân nhắc bảo vệ riêng nếu nghiệp vụ yêu cầu bất biến này.

## 13. Ghi nhớ

**MERGE** giúp viết thao tác tìm hoặc tạo theo mẫu; **uniqueness constraint** thực thi quy tắc không cho phép dữ liệu trùng khóa. Khi ghi đồng thời, kết hợp hai thành phần này với **khóa nghiệp vụ ổn định**, **transaction có xử lý lỗi/retry hợp lý** và **kiểm tra schema** để bảo vệ dữ liệu Neo4j. Constraint bảo đảm trạng thái dữ liệu hợp lệ; còn kết quả và thứ tự cập nhật của từng request vẫn phải được ứng dụng thiết kế, theo dõi và xử lý.
