# REMOVE để bỏ thuộc tính hoặc nhãn trong Neo4j

> **Chương:** Tạo và cập nhật  
> **Mô-đun:** `DATABASE_ENGINE_GRAPH_NEO4J` — sử dụng Neo4j để mô hình hóa dữ liệu liên kết theo *property graph*, truy vấn quan hệ và đường đi bằng Cypher.

Trong hệ thống đồ thị, dữ liệu không chỉ được tạo và cập nhật; đôi khi chúng ta cần **bỏ một thuộc tính không còn phù hợp** hoặc **gỡ một nhãn phân loại** khỏi nút. Ví dụ, một nhân viên không còn biệt danh, một quan hệ tham gia dự án không còn thông tin tạm thời, hay một người thôi thuộc nhóm `:Contractor` nhưng vẫn là `:Person`. Câu lệnh **`REMOVE`** của Cypher xử lý những thay đổi này.

Mấu chốt của bài học: `REMOVE` **không xóa nút, quan hệ hoặc toàn bộ đồ thị**. Nó loại bỏ **thuộc tính** khỏi nút/quan hệ, hoặc **nhãn** khỏi nút. Khi muốn xóa bản thân thành phần đồ thị, phải dùng những thao tác khác như `DELETE` hay `DETACH DELETE`, với tác động và rủi ro riêng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt thuộc tính nút, thuộc tính quan hệ, nhãn nút và kiểu quan hệ trong mô hình property graph.
2. Sử dụng `MATCH ... REMOVE` để bỏ một hay nhiều thuộc tính khỏi nút hoặc quan hệ hiện có.
3. Sử dụng `REMOVE n:Label` để gỡ nhãn và hiểu tác động lên các câu truy vấn dùng nhãn.
4. Phân biệt `REMOVE n.property`, `SET n.property = null`, `SET n += {property: null}` và `SET n = map`.
5. Hiểu sự khác nhau giữa `REMOVE` với `DELETE`, `DETACH DELETE` và `SET` khi thay đổi dữ liệu.
6. Đánh giá ảnh hưởng của ràng buộc (*constraint*), index, truy vấn hàng loạt, giao dịch và các lớp Java Driver/Spring Data Neo4j.
7. Xây dựng quy trình gỡ thuộc tính/nhãn an toàn, có thể kiểm tra trước và sau khi ghi.

## 2. Nhắc lại mô hình property graph

Xét đồ thị sau:

~~~text
(:Person:Employee {
    personId: 'P001',
    name: 'An',
    nickname: 'An Neo',
    department: 'Engineering'
})
         |
         | [:WORKS_ON {
         |    role: 'Backend',
         |    temporaryNote: 'Chuyển giao dữ liệu'
         | }]
         v
(:Project {projectId: 'PR001', title: 'Atlas'})
~~~

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| Nút (*node*) | `(p)` | Một thực thể người, dự án, khóa học... |
| Nhãn nút (*label*) | `:Person`, `:Employee` | Phân loại nút, có thể nhiều nhãn trên một nút |
| Thuộc tính nút | `p.nickname` | Dữ liệu khóa–giá trị gắn với nút |
| Quan hệ (*relationship*) | `(p)-[r]->(pr)` | Kết nối có hướng giữa hai nút |
| Kiểu quan hệ (*relationship type*) | `:WORKS_ON` | Ý nghĩa của quan hệ, mỗi quan hệ có một kiểu |
| Thuộc tính quan hệ | `r.temporaryNote` | Dữ liệu khóa–giá trị của chính kết nối |

Hai lệnh sau thay đổi những thứ **khác nhau**:

~~~cypher
MATCH (p:Person {personId: 'P001'})
REMOVE p.nickname
RETURN p;
~~~

~~~cypher
MATCH (p:Person {personId: 'P001'})
REMOVE p:Employee
RETURN p;
~~~

Lệnh thứ nhất loại bỏ thuộc tính `nickname`; lệnh thứ hai bỏ nhãn `Employee`. Nút `Person` và các quan hệ vẫn tồn tại nếu không có thao tác xóa khác.

### 2.1. Bảng hành vi nhanh

| Cú pháp | Tác động | Thành phần được giữ |
|---|---|---|
| `REMOVE p.nickname` | Bỏ thuộc tính `nickname` của nút `p` | Nút, các nhãn, các thuộc tính khác, quan hệ |
| `REMOVE r.temporaryNote` | Bỏ thuộc tính của quan hệ `r` | Quan hệ, hai đầu mút, các thuộc tính khác |
| `REMOVE p:Employee` | Gỡ nhãn `Employee` khỏi nút `p` | Nút, nhãn khác, thuộc tính và quan hệ |
| `DELETE p` | Xóa nút nếu không còn quan hệ gắn với nó | Không thuộc phạm vi `REMOVE` |
| `DETACH DELETE p` | Xóa nút cùng mọi quan hệ gắn với nút đó | Không thuộc phạm vi `REMOVE` |

Không có cách dùng `REMOVE` để “gỡ” trực tiếp kiểu của một quan hệ `WORKS_ON`. Nếu cần đổi kiểu quan hệ, cần mô hình hóa lại mối liên kết, thường bằng tạo quan hệ thuộc kiểu mới và xử lý quan hệ cũ trong một giao dịch thích hợp.

## 3. REMOVE một thuộc tính của nút

Cú pháp cơ bản:

~~~cypher
MATCH (p:Person {personId: $personId})
REMOVE p.nickname
RETURN p.personId AS personId,
       p.name AS name,
       p.nickname AS nickname;
~~~

Ý nghĩa:

1. `MATCH` tìm nút được nhận diện bằng `personId`.
2. `REMOVE p.nickname` bỏ **khóa thuộc tính `nickname`** khỏi nút đã khớp.
3. `RETURN` đọc lại các trường. Sau khi gỡ, `p.nickname` được đọc thành `null` vì khóa đó không còn tồn tại.

Ví dụ, giả sử trước truy vấn:

~~~text
(:Person {
  personId: 'P001',
  name: 'Nguyễn An',
  nickname: 'An Neo',
  department: 'Engineering'
})
~~~

Sau `REMOVE p.nickname`:

~~~text
(:Person {
  personId: 'P001',
  name: 'Nguyễn An',
  department: 'Engineering'
})
~~~

Chỉ có `nickname` biến mất. Khóa nghiệp vụ `personId`, tên `name` và bộ phận `department` vẫn được giữ.

### 3.1. Nếu thuộc tính không tồn tại thì sao?

`REMOVE p.nickname` trên một nút đã không còn `nickname` không cần tạo ra thuộc tính nào. Nói cách khác, lặp lại thao tác gỡ một thuộc tính đã vắng mặt không làm nút bị xóa hay tự sinh dữ liệu mới.

Vì vậy, xét riêng **trạng thái thuộc tính**, thao tác gỡ một khóa có thể lặp lại mà vẫn cho kết quả “không có khóa đó”. Tuy nhiên, điều này không thay thế yêu cầu kiểm tra giao dịch, quyền ghi hoặc ràng buộc dữ liệu.

### 3.2. Nếu MATCH không tìm được nút

~~~cypher
MATCH (p:Person {personId: 'P-DOES-NOT-EXIST'})
REMOVE p.nickname
RETURN p;
~~~

Nếu không tìm được nút, không có dòng nào đến `REMOVE` và câu truy vấn không tạo nút. Đây là khác biệt với `MERGE`, vốn có thể tạo mẫu mới khi không có mẫu phù hợp.

Nếu muốn biết có bao nhiêu nút được chọn để thao tác, có thể dùng:

~~~cypher
MATCH (p:Person {personId: $personId})
REMOVE p.nickname
RETURN count(p) AS matchedNodes;
~~~

`matchedNodes` là số nút được khớp và xử lý, **không nhất thiết là số thuộc tính thực sự bị loại bỏ**: một số nút có thể vốn đã không có `nickname`.

## 4. REMOVE nhiều thuộc tính trong một truy vấn

`REMOVE` cho phép liệt kê nhiều phần tử phân cách bằng dấu phẩy:

~~~cypher
MATCH (p:Person {personId: 'P001'})
REMOVE p.nickname, p.temporaryPhone, p.legacyCode
RETURN p.personId AS personId, properties(p) AS remainingProperties;
~~~

Truy vấn bỏ ba khóa nếu chúng tồn tại, giữ nguyên các thuộc tính không được chỉ định. Hàm `properties(p)` trả map các thuộc tính còn lại của nút.

Ví dụ với dữ liệu sản phẩm:

~~~cypher
MATCH (pr:Product {sku: 'SKU001'})
REMOVE pr.oldPrice, pr.importBatchId
SET pr.updatedAt = datetime()
RETURN pr.sku AS sku, properties(pr) AS properties;
~~~

Ở đây:

- `REMOVE` bỏ hai trường đã lỗi thời.
- `SET` ghi thời điểm cập nhật.
- Hai thao tác xảy ra trong cùng câu truy vấn và cùng giao dịch của truy vấn.

**Lưu ý:** cập nhật `updatedAt` như trên khiến timestamp đổi mỗi lần chạy, dù các thuộc tính cần gỡ đã không còn. Nếu nghiệp vụ cần tránh tác động khi không có thay đổi, hãy kiểm tra trước hoặc có cơ chế điều kiện phù hợp.

### 4.1. Có thể trộn thuộc tính và nhãn trong REMOVE

Một câu lệnh có thể chứa cả chỉ định bỏ thuộc tính và nhãn:

~~~cypher
MATCH (p:Person {personId: 'P001'})
REMOVE p.nickname, p:Contractor
RETURN labels(p) AS labels,
       properties(p) AS properties;
~~~

Nút vẫn mang các nhãn khác như `Person`, `Employee` nếu chúng đã tồn tại. Cần hiểu rõ cả hai thay đổi trước khi gộp trong một truy vấn.

## 5. REMOVE thuộc tính của quan hệ

Thuộc tính không chỉ nằm trên nút. Một quan hệ cũng có thể chứa `role`, `since`, `notes` hoặc dữ liệu khác.

Giả sử:

~~~text
(:Person {personId: 'P001'})
   -[:WORKS_ON {
       role: 'Backend',
       temporaryNote: 'Phụ trách giai đoạn thử nghiệm',
       startedOn: 2026-01-15
   }]->
(:Project {projectId: 'PR001'})
~~~

Để bỏ ghi chú tạm thời khỏi **chính quan hệ**, trước tiên tìm quan hệ và đặt vào biến `r`:

~~~cypher
MATCH (p:Person {personId: 'P001'})
      -[r:WORKS_ON]->
      (pr:Project {projectId: 'PR001'})
REMOVE r.temporaryNote
RETURN p.personId AS personId,
       pr.projectId AS projectId,
       properties(r) AS relationProperties;
~~~

Sau truy vấn, `r.role` và `r.startedOn` vẫn tồn tại. Quan hệ `WORKS_ON` và hai nút đầu mút không bị xóa.

### 5.1. Quan hệ có thể bị khớp nhiều lần

Nếu cơ sở dữ liệu có nhiều quan hệ `WORKS_ON` cùng kiểu, hướng và cặp đầu mút, `MATCH` có thể trả nhiều kết quả; `REMOVE r.temporaryNote` sẽ áp dụng cho **từng quan hệ được khớp**.

Với hệ thống cần phân biệt các phân công theo mã, có thể thêm khóa nhận diện quan hệ:

~~~cypher
MATCH (:Person {personId: $personId})
      -[r:WORKS_ON {assignmentId: $assignmentId}]->
      (:Project {projectId: $projectId})
REMOVE r.temporaryNote
RETURN r.assignmentId AS assignmentId,
       properties(r) AS properties;
~~~

Cách này chỉ chọn quan hệ có `assignmentId` yêu cầu, nhưng vẫn cần bảo đảm tính duy nhất của khóa nghiệp vụ và thiết kế ràng buộc phù hợp nếu hệ thống có ghi đồng thời.

### 5.2. Vì sao không REMOVE kiểu quan hệ?

Trong property graph, `:WORKS_ON` là **kiểu** của quan hệ, khác với một nhãn nút. Cú pháp `REMOVE r:WORKS_ON` không phải cách đổi kiểu quan hệ. Nếu muốn ngừng một kết nối, hãy quyết định theo nghiệp vụ:

- Chỉ bỏ thông tin phụ: `REMOVE r.temporaryNote`.
- Đánh dấu kết nối không còn hiệu lực: `SET r.active = false` hoặc `SET r.endedOn = date()`.
- Thật sự xóa kết nối: `DELETE r`.
- Chuyển sang kiểu kết nối khác: tạo quan hệ kiểu mới với thuộc tính cần giữ và xử lý quan hệ cũ trong cùng giao dịch.

Đừng xóa quan hệ khi chỉ có yêu cầu xóa một trường dữ liệu.

## 6. REMOVE nhãn khỏi nút

Một nút Neo4j có thể mang nhiều nhãn. Ví dụ:

~~~text
(:Person:Employee:Contractor {
  personId: 'P001',
  name: 'An'
})
~~~

Khi An chuyển từ nhân sự hợp đồng sang nhân viên chính thức, doanh nghiệp có thể muốn gỡ nhãn `Contractor`:

~~~cypher
MATCH (p:Person {personId: 'P001'})
REMOVE p:Contractor
RETURN labels(p) AS labels;
~~~

Sau truy vấn, nút vẫn mang `Person` và `Employee` (nếu có trước đó), và tất cả quan hệ của nút vẫn tồn tại. Không có nút mới được tạo.

### 6.1. Bỏ nhiều nhãn

~~~cypher
MATCH (p:Person {personId: 'P001'})
REMOVE p:Contractor:TemporaryStaff
RETURN labels(p) AS labels;
~~~

Có thể dùng danh sách nhãn như trên để gỡ nhiều nhãn của cùng nút. Nếu nhãn không tồn tại trên nút, thao tác gỡ nhãn đó không làm phát sinh một nút hoặc nhãn mới.

### 6.2. Nhãn khác thuộc tính

Hai câu lệnh dưới đây không tương đương:

~~~cypher
MATCH (p:Person {personId: 'P001'})
REMOVE p:Manager
RETURN labels(p) AS labels;
~~~

~~~cypher
MATCH (p:Person {personId: 'P001'})
REMOVE p.role
RETURN properties(p) AS properties;
~~~

- `REMOVE p:Manager` bỏ **phân loại** `Manager`. Các thuộc tính như `role` không tự biến mất.
- `REMOVE p.role` bỏ **thuộc tính** `role`. Nhãn `Manager` nếu đang có vẫn tồn tại.

Nếu ứng dụng sử dụng cả hai để biểu diễn quyền hạn hoặc chức danh, cần chính sách cập nhật đồng bộ để tránh dữ liệu mâu thuẫn.

### 6.3. Chuyển nhãn với SET và REMOVE

Giả sử trước đây một người có nhãn `:Candidate` và giờ được tuyển dụng. Có thể thực hiện:

~~~cypher
MATCH (p:Person {personId: $personId})
REMOVE p:Candidate
SET p:Employee
RETURN p.personId AS personId, labels(p) AS labels;
~~~

`REMOVE` gỡ phân loại cũ; `SET` thêm phân loại mới. Việc dùng cùng một truy vấn giúp mô tả rõ thao tác chuyển trạng thái.

Truy vấn này **không tạo mới** nút nếu chưa tìm được người. Nếu nghiệp vụ cần tạo người mới, đó là tác vụ `CREATE`/`MERGE` riêng.

### 6.4. Truy vấn theo nhãn sau khi REMOVE

Trước khi bỏ nhãn `Employee`:

~~~cypher
MATCH (p:Employee {personId: 'P001'})
RETURN p.name AS name;
~~~

Sau khi bỏ nhãn đó, câu truy vấn `MATCH (p:Employee ...)` không còn tìm thấy nút P001 (trừ khi nhãn được gắn lại). Tuy nhiên:

~~~cypher
MATCH (p:Person {personId: 'P001'})
RETURN p.name AS name, labels(p) AS labels;
~~~

vẫn tìm được nút nếu nó tiếp tục có nhãn `Person`. Nếu bỏ tất cả nhãn, nút trở thành **nút không nhãn**, vẫn có thể tồn tại cùng thuộc tính và quan hệ của nó.

## 7. REMOVE so với SET null và thay thế bản đồ thuộc tính

Trong Cypher, giá trị `null` **không được lưu** như một giá trị thuộc tính thông thường. Một phép gán thuộc tính thành `null` có tác dụng loại bỏ thuộc tính đó.

### 7.1. Hai cách bỏ một thuộc tính

Hai câu sau cho cùng trạng thái cuối đối với thuộc tính `nickname`:

~~~cypher
MATCH (p:Person {personId: 'P001'})
REMOVE p.nickname
RETURN p.nickname AS nickname;
~~~

~~~cypher
MATCH (p:Person {personId: 'P001'})
SET p.nickname = null
RETURN p.nickname AS nickname;
~~~

Cả hai khiến khóa `nickname` không còn trên nút. `REMOVE` diễn đạt trực tiếp ý định **bỏ thuộc tính**, còn `SET ... = null` đặc biệt hữu ích khi giá trị cần xóa được tính qua một biểu thức.

### 7.2. Xóa một khóa thông qua map patch

~~~cypher
MATCH (p:Person {personId: 'P001'})
SET p += {nickname: null}
RETURN properties(p) AS properties;
~~~

Khi dùng `SET p += map`, các thuộc tính **không xuất hiện trong map** được giữ nguyên; các khóa có giá trị `null` bị gỡ. Kết quả với `nickname` tương tự `REMOVE p.nickname`.

Với tham số:

~~~json
{
  "personId": "P001",
  "patch": {
    "nickname": null,
    "department": "Platform"
  }
}
~~~

~~~cypher
MATCH (p:Person {personId: $personId})
SET p += $patch
RETURN properties(p) AS properties;
~~~

Truy vấn có thể đồng thời **gỡ `nickname`** và **cập nhật `department`**, nhưng phải chắc chắn rằng `null` trong giao thức có nghĩa “xóa trường”, không phải “nguồn không gửi giá trị”.

### 7.3. Đừng nhầm SET = map với REMOVE có chọn lọc

~~~cypher
MATCH (p:Person {personId: 'P001'})
SET p = {personId: 'P001', name: 'Nguyễn An'}
RETURN properties(p) AS properties;
~~~

`SET p = map` **thay thế toàn bộ bản đồ thuộc tính**: mọi khóa cũ không có trong map mới sẽ biến mất. Đây là tác động rộng hơn nhiều so với `REMOVE p.nickname`.

| Cách viết | Các khóa cũ không được đề cập |
|---|---|
| `REMOVE p.nickname` | Giữ nguyên, trừ `nickname` |
| `SET p.nickname = null` | Giữ nguyên, trừ `nickname` |
| `SET p += {nickname: null}` | Giữ nguyên, trừ `nickname` |
| `SET p = {name: 'An'}` | **Bị xóa toàn bộ**, trừ khóa `name` trong map mới |

Nếu chỉ cần gỡ một thuộc tính, `REMOVE` thường rõ ý định nhất. Dùng `SET = map` chỉ khi thực sự muốn thay toàn bộ trạng thái thuộc tính và đã bảo đảm các khóa cần giữ vẫn có trong map.

## 8. REMOVE khác DELETE và DETACH DELETE

Ba nhóm thao tác rất dễ bị nhầm lẫn:

~~~cypher
// Bỏ trường nickname; vẫn giữ nút và quan hệ
MATCH (p:Person {personId: 'P001'})
REMOVE p.nickname;
~~~

~~~cypher
// Xóa quan hệ cụ thể; hai nút đầu mút vẫn được giữ
MATCH (p:Person {personId: 'P001'})
      -[r:WORKS_ON]->
      (pr:Project {projectId: 'PR001'})
DELETE r;
~~~

~~~cypher
// Xóa nút cùng tất cả quan hệ trực tiếp gắn với nút
MATCH (p:Person {personId: 'P001'})
DETACH DELETE p;
~~~

`DELETE p` không thể xóa một nút còn quan hệ gắn với nó nếu chưa xử lý các quan hệ liên quan; `DETACH DELETE p` xử lý xóa nút và các quan hệ gắn vào nút đó.

| Câu lệnh | Xóa thuộc tính | Gỡ nhãn nút | Xóa nút | Xóa quan hệ |
|---|---:|---:|---:|---:|
| `REMOVE p.nickname` | Có, một khóa | Không | Không | Không |
| `REMOVE p:Employee` | Không | Có | Không | Không |
| `DELETE r` | Cùng với quan hệ | Không | Không | Có |
| `DELETE p` | Cùng với nút | Cùng với nút | Có nếu không còn quan hệ | Không tự xóa quan hệ |
| `DETACH DELETE p` | Cùng với nút | Cùng với nút | Có | Có, các quan hệ gắn với nút |

**Nguyên tắc:** khi yêu cầu chỉ là “người dùng bỏ số điện thoại” hoặc “nhân viên không còn thuộc một phân loại”, không dùng `DELETE` vì nó thay đổi cả thực thể hoặc kết nối.

## 9. Ràng buộc, index và dữ liệu bắt buộc

Neo4j có thể dùng **constraint** và **index** để bảo vệ và tìm dữ liệu. Khi gỡ thuộc tính hoặc nhãn, cần biết ràng buộc nào đang áp dụng.

### 9.1. Gỡ thuộc tính khóa nghiệp vụ

Giả sử có constraint:

~~~cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;
~~~

Constraint duy nhất đảm bảo mỗi giá trị `personId` không trùng giữa các nút mang nhãn `Person`, nhưng **ràng buộc duy nhất đơn thuần không đảm bảo mọi nút đều phải có `personId`**. Vì thế:

~~~cypher
MATCH (p:Person {personId: 'P001'})
REMOVE p.personId;
~~~

có thể làm mất khả năng nhận diện nút bằng khóa nghiệp vụ nếu không có thêm constraint về sự hiện diện của thuộc tính. Đây là **rủi ro dữ liệu**, dù thao tác có thể hợp lệ về mặt cú pháp.

Khi mô hình yêu cầu khóa luôn tồn tại, hãy dùng constraint phù hợp với phiên bản/phiên bản sản phẩm Neo4j đang triển khai và chính sách cấp ứng dụng. Những ràng buộc về sự tồn tại hoặc kiểu dữ liệu có thể khiến `REMOVE` thất bại thay vì cho phép thiếu trường.

### 9.2. Gỡ nhãn làm thay đổi phạm vi constraint/index

Nếu một constraint hoặc index được định nghĩa cho `:Employee(employeeId)`, việc bỏ nhãn `Employee` khỏi một nút sẽ khiến nút không còn thuộc phạm vi truy vấn/index theo nhãn đó. Điều này **không xóa thuộc tính `employeeId`** của nút.

Ví dụ:

~~~cypher
MATCH (p:Person {personId: 'P001'})
REMOVE p:Employee
RETURN labels(p) AS labels, p.employeeId AS employeeId;
~~~

Có thể còn `employeeId` nhưng không có nhãn `Employee`. Khi gắn nhãn lại bằng `SET p:Employee`, các constraint dành cho nhãn đó tiếp tục được áp dụng; dữ liệu không hợp lệ có thể gây lỗi lúc gắn nhãn.

### 9.3. Không dùng REMOVE để né constraint

Về mặt kỹ thuật, việc bỏ nhãn hoặc bỏ thuộc tính có thể thay đổi tập dữ liệu chịu một constraint nhất định. Nhưng **không nên dùng việc này làm đường tắt để xử lý xung đột dữ liệu**. Hãy xác định thực thể, quy tắc nghiệp vụ và chính sách chuẩn hóa trước khi thay đổi các thuộc tính/nhãn liên quan đến tính toàn vẹn.

### 9.4. Thiết kế khóa ổn định

Một truy vấn cập nhật thường bắt đầu bằng:

~~~cypher
MATCH (p:Person {personId: $personId})
REMOVE p.legacyCode
RETURN p.personId AS personId;
~~~

`personId` nên là khóa ổn định. Tránh tìm đối tượng bằng `name` khi tên không duy nhất. Nếu một `MATCH` khớp nhiều nút, `REMOVE` có thể tác động đến tất cả nút khớp, không tự chọn “nút đúng”.

## 10. REMOVE khi đồng bộ dữ liệu

Trong hệ thống tích hợp, thông tin có thể cần được gỡ vì:

- Nguồn chính thức xác nhận một trường không còn hiệu lực.
- Một nhãn phân loại thay đổi theo trạng thái nghiệp vụ.
- Dữ liệu tạm thời được dọn sau khi hoàn thành tác vụ.
- Quy định lưu trữ yêu cầu không giữ một loại thông tin nhất định.

Tuy nhiên, “giá trị trong nguồn là `null`” và “nguồn **yêu cầu xóa** thuộc tính” không luôn đồng nghĩa.

### 10.1. Phân biệt field thiếu, null và yêu cầu xóa

Xét ba thông điệp từ nguồn:

~~~json
{"personId": "P001", "department": "Data"}
~~~

~~~json
{"personId": "P001", "nickname": null}
~~~

~~~json
{"personId": "P001", "removeFields": ["nickname"]}
~~~

Tùy giao thức:

1. Không có `nickname` có thể nghĩa “không thay đổi nickname”.
2. `nickname: null` có thể nghĩa “xóa nickname” **hoặc** “không biết nickname”.
3. `removeFields` diễn đạt một yêu cầu xóa có chủ đích.

Ứng dụng cần quy định rõ giao thức trước khi biến đầu vào thành Cypher. Nếu để client gửi một map bất kỳ rồi chạy `SET p += $patch`, các giá trị `null` có thể vô tình làm mất thuộc tính quan trọng.

### 10.2. Kiểm soát danh sách trường được phép xóa

Ví dụ dịch vụ chỉ cho phép gỡ `nickname` và `temporaryPhone`, không cho phép gỡ `personId`, `createdAt`, `verified` hoặc các trường do dịch vụ phân quyền quản lý.

Có thể dùng các câu lệnh cố định theo hành động:

~~~cypher
MATCH (p:Person {personId: $personId})
REMOVE p.nickname
RETURN p.personId AS personId;
~~~

~~~cypher
MATCH (p:Person {personId: $personId})
REMOVE p.temporaryPhone
RETURN p.personId AS personId;
~~~

Với nhiều trường tùy chọn, ứng dụng có thể kiểm soát danh sách trường ở phía ứng dụng và tạo câu lệnh phù hợp từ **tên trường đã xác thực theo danh sách cho phép**. Không ghép trực tiếp tên thuộc tính do người dùng tự nhập vào chuỗi Cypher không kiểm soát; tham số `$personId` truyền **giá trị**, không mặc nhiên biến một tên khóa không tin cậy thành thành phần cú pháp an toàn.

### 10.3. Đồng bộ trạng thái phân loại

Nếu một người chuyển từ `Contractor` sang `Employee`:

~~~cypher
MATCH (p:Person {personId: $personId})
REMOVE p:Contractor
SET p:Employee,
    p.employmentStatus = 'active',
    p.updatedAt = datetime()
RETURN p.personId AS personId,
       labels(p) AS labels,
       p.employmentStatus AS employmentStatus;
~~~

Ví dụ dùng `REMOVE` và `SET` để thay đổi **phân loại** và **thuộc tính trạng thái** trong một truy vấn. Cần quyết định nhất quán khi nào nhãn phản ánh vai trò, bộ phận hoặc quyền truy cập, đặc biệt nếu quyền ứng dụng phụ thuộc vào nhãn.

## 11. REMOVE hàng loạt với UNWIND

Trong công việc dọn dữ liệu, thường cần gỡ một trường cũ cho nhiều nút. `UNWIND` biến danh sách ID thành các dòng:

~~~json
{
  "personIds": ["P001", "P002", "P003"]
}
~~~

~~~cypher
UNWIND $personIds AS id
MATCH (p:Person {personId: id})
REMOVE p.legacyCode
RETURN count(DISTINCT p) AS matchedPersons;
~~~

Nếu ba ID là duy nhất và cả ba nút đều tồn tại, `matchedPersons` thường bằng `3`. Nếu một ID không tồn tại, chỉ những nút tìm thấy mới được xử lý.

**Lưu ý số liệu:** `matchedPersons` là số nút khác nhau được tìm thấy, **không phải số thuộc tính thực sự đã bị gỡ**. Một người có thể vốn không còn `legacyCode`.

### 11.1. Gỡ nhãn hàng loạt

~~~cypher
UNWIND $personIds AS id
MATCH (p:Person {personId: id})
REMOVE p:TemporaryStaff
RETURN count(DISTINCT p) AS matchedPersons;
~~~

Truy vấn không xóa nút hay các nhãn khác. Nếu có nhiều bản ghi trùng ID do thiếu constraint, một ID có thể khớp nhiều nút và tất cả bị tác động.

### 11.2. Giới hạn phạm vi bằng WHERE

Đôi khi cần gỡ trường lỗi thời chỉ cho một nhóm:

~~~cypher
MATCH (p:Person)
WHERE p.legacyCode IS NOT NULL
  AND p.department = 'Engineering'
REMOVE p.legacyCode
RETURN count(p) AS matchedPersons;
~~~

Việc lọc trước bằng `WHERE` giúp xác định nhóm người cần thao tác. `IS NOT NULL` chọn những nút hiện có giá trị thuộc tính; vì Neo4j không lưu thuộc tính null như giá trị thông thường, điều kiện này cũng giúp giới hạn nhóm có trường cần gỡ.

**Lưu ý:** `MATCH (p:Person)` có thể phải duyệt tập nút lớn nếu không có điều kiện/index thích hợp. Với hệ thống lớn, nên xem xét kế hoạch truy vấn, chia lô và thực hiện trong cửa sổ vận hành phù hợp.

### 11.3. Giao dịch, phạm vi ghi và lặp lại

`REMOVE` là thao tác ghi. Với hàng triệu bản ghi, một giao dịch duy nhất có thể gây tải lớn. Hãy chia lô với kích thước phù hợp, có chính sách retry và theo dõi tác động.

Lặp lại thao tác `REMOVE p.legacyCode` trên cùng nút đã gỡ trường không tạo thêm thay đổi nội dung của trường đó. Tuy nhiên, nếu cùng truy vấn còn cập nhật timestamp, bộ đếm hoặc trạng thái khác, toàn bộ giao dịch có thể không còn tính chất lặp lại không đổi.

## 12. Dùng REMOVE từ Neo4j Java Driver

Ứng dụng Java nên gửi giá trị định danh qua **tham số** và thực hiện ghi trong giao dịch được quản lý. Ví dụ phương thức gỡ biệt danh của một người:

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;

public final class PersonCleanupService {
    private final Driver driver;

    public PersonCleanupService(Driver driver) {
        this.driver = driver;
    }

    public long removeNickname(String personId) {
        String cypher = """
                MATCH (p:Person {personId: $personId})
                REMOVE p.nickname
                RETURN count(p) AS matched
                """;

        try (Session session = driver.session()) {
            return session.executeWrite(tx ->
                    tx.run(cypher, Map.of("personId", personId))
                      .single()
                      .get("matched")
                      .asLong()
            );
        }
    }
}
~~~

**Giải thích:**

- `MATCH` định danh nút bằng `personId`. Nếu không có nút, `count(p)` trả `0`.
- `REMOVE p.nickname` chỉ bỏ thuộc tính, không xóa nút hoặc quan hệ.
- `Map.of` nhận tham số `personId` **khác null**; ứng dụng cần xác thực định danh trước khi gọi.
- `executeWrite` chạy callback trong một giao dịch ghi do Driver quản lý; khi có lỗi tạm thời thích hợp, callback có thể được chạy lại. Không đặt hành động bên ngoài Neo4j không có cơ chế chống lặp bên trong callback.
- Kết quả trả về là số nút được tìm thấy, không phải số thuộc tính thực sự thay đổi. Trong hệ thống có khóa duy nhất, số này thường là `0` hoặc `1`.

`Driver` nên được quản lý theo vòng đời ứng dụng. Tùy hệ thống, cần chỉ định database, chính sách timeout, quyền ghi, giám sát và xử lý lỗi transaction.

### 12.1. Với Spring Data Neo4j

Spring Data Neo4j cung cấp lớp ánh xạ entity và repository. Khi nghiệp vụ cần xóa một thuộc tính hay nhãn bằng Cypher tùy biến, vẫn áp dụng cú pháp `REMOVE` thông thường trong truy vấn được cấu hình, ví dụ qua `@Query`.

Cần để ý rằng:

- Lệnh Cypher tác động trực tiếp tới dữ liệu lưu trữ, trong khi một entity Java đã nạp trước đó có thể còn trạng thái cũ trong bộ nhớ.
- Việc lưu lại entity cũ không có kiểm soát có thể tạo ra kết quả khác với thao tác `REMOVE` vừa chạy, tùy chiến lược ánh xạ và giao dịch.
- Nhãn có thể tham gia cách repository tìm/ánh xạ entity; bỏ nhãn có thể khiến truy vấn repository theo nhãn cũ không còn tìm thấy bản ghi.

Nên thiết kế giao dịch và vòng đời entity phù hợp khi kết hợp truy vấn `REMOVE` trực tiếp với các thao tác repository khác.

## 13. Quy trình thực hành có kiểm soát

Ví dụ sau được viết cho một **đồ thị thử nghiệm**. Các bước sử dụng một người, một dự án và một quan hệ, sau đó gỡ thuộc tính hoặc nhãn mà không xóa thành phần.

### Bước 1 — Chuẩn bị dữ liệu mẫu

Chạy một lần trên bộ dữ liệu thử nghiệm chưa có các khóa dưới đây:

~~~cypher
CREATE
  (p:Person:Employee:TemporaryStaff {
    personId: 'P-REMOVE-01',
    name: 'Lan',
    nickname: 'Lan Graph',
    legacyCode: 'OLD-01',
    department: 'Engineering'
  }),
  (pr:Project {
    projectId: 'PR-REMOVE-01',
    title: 'Tri thức đồ thị'
  }),
  (p)-[:WORKS_ON {
    role: 'Backend',
    temporaryNote: 'Đang chuyển giao'
  }]->(pr);
~~~

Không chạy lại `CREATE` trên dữ liệu thật với cùng khóa nghiệp vụ vì nó có thể tạo bản sao, hoặc bị từ chối khi có constraint.

### Bước 2 — Xem trạng thái trước thay đổi

~~~cypher
MATCH (p:Person {personId: 'P-REMOVE-01'})
      -[r:WORKS_ON]->
      (pr:Project {projectId: 'PR-REMOVE-01'})
RETURN labels(p) AS personLabels,
       properties(p) AS personProperties,
       type(r) AS relationType,
       properties(r) AS relationProperties,
       pr.title AS project;
~~~

Kết quả dự kiến có các nhãn `Person`, `Employee`, `TemporaryStaff`; người có `nickname` và `legacyCode`; quan hệ có `temporaryNote`.

### Bước 3 — Gỡ trường cũ và nhãn tạm

~~~cypher
MATCH (p:Person {personId: 'P-REMOVE-01'})
REMOVE p.nickname, p.legacyCode, p:TemporaryStaff
RETURN labels(p) AS labels, properties(p) AS properties;
~~~

Sau thao tác, `p.name`, `p.department` và `p.personId` vẫn được giữ. Nút có thể tiếp tục được tìm bằng nhãn `Person` và `Employee`.

### Bước 4 — Gỡ ghi chú tạm thời trên quan hệ

~~~cypher
MATCH (:Person {personId: 'P-REMOVE-01'})
      -[r:WORKS_ON]->
      (:Project {projectId: 'PR-REMOVE-01'})
REMOVE r.temporaryNote
RETURN type(r) AS relationType, properties(r) AS properties;
~~~

Quan hệ vẫn có `role = 'Backend'` và vẫn nối hai nút.

### Bước 5 — Xác minh sau thao tác

~~~cypher
MATCH (p:Person {personId: 'P-REMOVE-01'})
      -[r:WORKS_ON]->
      (pr:Project {projectId: 'PR-REMOVE-01'})
RETURN p.personId AS personId,
       labels(p) AS labels,
       keys(p) AS personPropertyKeys,
       type(r) AS relationType,
       keys(r) AS relationPropertyKeys,
       pr.projectId AS projectId;
~~~

Kỳ vọng:

- Vẫn có **một nút Person**, **một nút Project** và quan hệ `WORKS_ON` của ví dụ.
- Nút không còn nhãn `TemporaryStaff`.
- Nút không còn `nickname` và `legacyCode`.
- Quan hệ không còn `temporaryNote`, nhưng vẫn có `role`.

Các kết quả này giả định dữ liệu ban đầu duy nhất theo khóa, và không có thao tác khác đồng thời can thiệp vào bộ dữ liệu thử nghiệm.

## 14. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `REMOVE` chạy nhưng không thấy thay đổi | `MATCH` không khớp; hoặc trường/nhãn vốn không tồn tại | Kiểm tra khóa, nhãn, số dòng khớp và trạng thái trước |
| Một yêu cầu làm mất thuộc tính của nhiều nút | `MATCH` dùng tên không duy nhất hoặc điều kiện quá rộng | Dùng khóa nghiệp vụ; kiểm tra `RETURN count(*)` trước khi ghi |
| Sau khi gỡ nhãn không tìm thấy nút bằng truy vấn cũ | `MATCH` cũ lọc theo chính nhãn đã gỡ | Truy vấn bằng nhãn ổn định, định nghĩa lại cách chọn thực thể |
| Gỡ nhãn nhưng thuộc tính vai trò vẫn còn | Nhãn và thuộc tính là hai thành phần độc lập | Dùng `REMOVE n.role` nếu nghiệp vụ cũng yêu cầu xóa |
| Gỡ thuộc tính quan hệ nhưng quan hệ vẫn tồn tại | `REMOVE r.prop` chỉ xóa khóa thuộc tính | Dùng `DELETE r` chỉ khi cần xóa hẳn liên kết |
| Bị lỗi khi bỏ thuộc tính bắt buộc | Constraint yêu cầu thuộc tính tồn tại hoặc đáp ứng quy tắc | Kiểm tra schema/constraint và chính sách dữ liệu |
| Không còn tìm được nút theo ID sau khi dọn trường | Vô tình gỡ khóa nghiệp vụ hoặc map thay thế làm mất khóa | Bảo vệ định danh, kiểm tra `SET = map`/`+=` |
| Truy vấn `SET n = $map` làm mất các trường khác | Toán tử `=` thay tất cả thuộc tính | Dùng `REMOVE` cho trường cụ thể hoặc `+=` cho bản vá |
| Bản tin null vô tình xóa thuộc tính | Tự động dùng `SET n.field = $value` khi giá trị `null` | Định nghĩa rõ ngữ nghĩa null của API |
| Gỡ nhãn làm repository không tìm thấy entity | Truy vấn ứng dụng phụ thuộc nhãn cũ | Rà soát mapping và truy vấn sau khi đổi phân loại |
| Dọn dữ liệu khối lượng lớn làm tải hệ thống tăng | Một giao dịch ghi quá nhiều nút/quan hệ | Chia lô, dùng khóa/index, kiểm tra kế hoạch truy vấn |

## 15. Bài tập tự luyện

### Bài tập 1 — Gỡ hai thuộc tính khỏi nút

**Yêu cầu:** cho nút `User` nhận diện bằng `userId = 'U001'`, xóa `middleName` và `temporaryEmail` nhưng giữ `userId`, `fullName`.

<details>
<summary>Đáp án tham khảo</summary>

~~~cypher
MATCH (u:User {userId: 'U001'})
REMOVE u.middleName, u.temporaryEmail
RETURN u.userId AS userId, properties(u) AS properties;
~~~

Các thuộc tính khác không bị thay đổi.

</details>

### Bài tập 2 — Gỡ nhãn đã không còn phù hợp

**Yêu cầu:** nút `(:Person:Candidate {personId: 'P002'})` đã trở thành nhân viên. Bỏ `Candidate`, thêm `Employee`, giữ `Person` và toàn bộ thuộc tính.

<details>
<summary>Đáp án tham khảo</summary>

~~~cypher
MATCH (p:Person {personId: 'P002'})
REMOVE p:Candidate
SET p:Employee
RETURN p.personId AS personId, labels(p) AS labels;
~~~

`REMOVE` bỏ một nhãn; `SET` thêm nhãn mới. Nút vẫn tồn tại.

</details>

### Bài tập 3 — Phân biệt REMOVE và DELETE

Cho quan hệ:

~~~text
(:Student {studentId: 'S001'})
  -[:ENROLLED_IN {status: 'completed', note: 'Manual import'}]->
(:Course {courseId: 'C001'})
~~~

**Câu hỏi:** viết truy vấn chỉ xóa `note`, giữ quan hệ và trạng thái `completed`.

<details>
<summary>Đáp án tham khảo</summary>

~~~cypher
MATCH (:Student {studentId: 'S001'})
      -[r:ENROLLED_IN]->
      (:Course {courseId: 'C001'})
REMOVE r.note
RETURN properties(r) AS properties;
~~~

`DELETE r` sẽ xóa toàn bộ quan hệ, nên không phù hợp với yêu cầu.

</details>

### Bài tập 4 — Lỗi do thay toàn bộ map

Giả sử nút `Employee` có:

~~~text
{employeeId: 'E001', name: 'Bình', department: 'Data', createdAt: ...}
~~~

Cần bỏ `department` nhưng giữ các trường khác. So sánh:

~~~cypher
MATCH (e:Employee {employeeId: 'E001'})
SET e = {employeeId: 'E001', name: 'Bình'};
~~~

và:

~~~cypher
MATCH (e:Employee {employeeId: 'E001'})
REMOVE e.department;
~~~

**Câu hỏi:** truy vấn nào bảo toàn `createdAt`?

<details>
<summary>Đáp án</summary>

Truy vấn `REMOVE e.department` chỉ bỏ trường `department`, giữ `createdAt`. Truy vấn `SET e = {...}` thay toàn bộ tập thuộc tính; vì map mới thiếu `createdAt`, thuộc tính này cũng bị loại bỏ.

</details>

### Bài tập 5 — Đếm nút đã xử lý

Giả sử cần bỏ `legacyFlag` của các nút `Product` có `sku` trong `$skus`. Viết truy vấn trả **số sản phẩm khác nhau đã khớp**, tránh nhầm với số thuộc tính thật sự bị xóa.

<details>
<summary>Đáp án tham khảo</summary>

~~~cypher
UNWIND $skus AS sku
MATCH (p:Product {sku: sku})
REMOVE p.legacyFlag
RETURN count(DISTINCT p) AS matchedProducts;
~~~

`matchedProducts` chỉ đếm các nút khớp, kể cả nút vốn đã không có `legacyFlag`. Muốn đo số trường thực sự bị gỡ, cần kiểm tra giá trị/hiện diện của thuộc tính trước khi thao tác và xây dựng thống kê riêng.

</details>

## 16. Tổng kết

| Mục đích | Cú pháp Cypher gợi ý |
|---|---|
| Gỡ thuộc tính nút | `MATCH (n:Label {id: $id}) REMOVE n.oldField` |
| Gỡ nhiều thuộc tính | `REMOVE n.fieldA, n.fieldB` |
| Gỡ thuộc tính quan hệ | `MATCH (a)-[r:TYPE]->(b) REMOVE r.note` |
| Gỡ một nhãn nút | `REMOVE n:OldLabel` |
| Gỡ nhiều nhãn | `REMOVE n:LabelA:LabelB` |
| Đổi nhãn phân loại | `REMOVE n:OldLabel SET n:NewLabel` |
| Gỡ thuộc tính bằng phép gán null | `SET n.field = null` |
| Gỡ một khóa qua map patch | `SET n += {field: null}` |
| Thay toàn bộ thuộc tính | `SET n = $fullSnapshot` — cần cân nhắc kỹ |
| Xóa hẳn một quan hệ | `DELETE r` |
| Xóa nút và quan hệ gắn với nó | `DETACH DELETE n` — khác hoàn toàn `REMOVE` |

**Ghi nhớ:** `REMOVE` là công cụ **gỡ thuộc tính hoặc nhãn** mà vẫn giữ cấu trúc nút và quan hệ. Vì nhãn quyết định phạm vi truy vấn và có liên hệ với index/constraint, còn thuộc tính có thể chứa khóa định danh, hãy chọn đúng đối tượng, đúng trường và đúng quy tắc nghiệp vụ trước khi ghi. Khi dùng Neo4j trong nhập liệu, Java Driver hay Spring Data Neo4j, nên nhận diện nút/quan hệ bằng khóa ổn định, sử dụng tham số, kiểm soát transaction và kiểm tra dữ liệu sau thao tác.

Từ kiến thức này, bạn có thể tiếp tục phân biệt `REMOVE` với `DELETE`, học các thao tác ghi phức tạp bằng `MERGE`/`SET` và tối ưu truy vấn cập nhật với index, constraint, `EXPLAIN` và quản trị giao dịch.
