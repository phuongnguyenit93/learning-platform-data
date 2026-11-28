# Kiểm soát label, loại relationship và cấu trúc truy vấn động

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt giá trị dữ liệu với các thành phần cấu trúc của Cypher như label, relationship type, property key và hướng quan hệ.
- Giải thích vì sao bind một parameter thông thường không thể thay thế trực tiếp mọi thành phần trong pattern.
- Dùng dynamic label và dynamic relationship type trong Neo4j 5.26 trở lên.
- Giới hạn label, relationship type và property được phép qua allowlist của ứng dụng.
- Dùng Neo4jClient để bind tham số và chạy truy vấn có token động an toàn.
- Tổ chức query template cố định khi cần thay đổi hướng quan hệ hoặc cấu trúc câu lệnh.
- Tránh Cypher injection, lộ dữ liệu giữa tenant và truy cập vượt quyền.
- Kiểm thử query động, quyền truy cập và hiệu năng theo phiên bản Neo4j.

## 1. Label, relationship type và query structure là gì?

Trong Neo4j, label phân loại node, còn relationship type mô tả loại liên kết giữa hai node. Một node có thể mang nhiều label, nhưng mỗi relationship chỉ có một type.

Ví dụ:

~~~cypher
(:Person {personId: 'p-100'})
    -[:REPORTS_TO {since: date('2024-01-01')}]->
(:Person {personId: 'p-200'})
~~~

Trong pattern này:

- `Person` là label của node.
- `REPORTS_TO` là relationship type.
- `personId` và `since` là property key.
- `'p-100'`, `'p-200'` và ngày là giá trị dữ liệu.
- Mũi tên `->` là hướng relationship.

Ứng dụng có thể cần tìm nhiều loại node hoặc loại relationship tùy chức năng. Ví dụ màn hình quản trị cho phép tìm `Person` hoặc `Team`, còn màn hình đồ thị quan hệ cho phép chọn `KNOWS` hoặc `REPORTS_TO`.

Rủi ro xuất hiện khi ứng dụng ghép trực tiếp dữ liệu request vào chuỗi Cypher. Nếu một giá trị được chèn vào vị trí cú pháp, người dùng có thể làm thay đổi pattern hoặc thêm clause ngoài dự kiến.

Cần phân biệt ba lớp kiểm soát:

1. **Parameter binding:** giữ giá trị dữ liệu tách khỏi câu query.
2. **Allowlist:** chỉ cho phép ứng dụng chọn những label, type và property mà nghiệp vụ đã định nghĩa.
3. **Database authorization:** giới hạn tài khoản Neo4j chỉ đọc hoặc ghi đúng phần graph cần thiết.

Parameter binding giúp ngăn dữ liệu trở thành cú pháp query. Allowlist quyết định lựa chọn đó có hợp lệ với nghiệp vụ hay không. Quyền database giới hạn tác động nếu ứng dụng có lỗi.

## 2. Parameter thông thường không thay thế trực tiếp label hoặc relationship type

Với dữ liệu thông thường, hãy luôn dùng parameter:

~~~cypher
MATCH (p:Person)
WHERE p.personId = $personId
RETURN p
~~~

Giá trị `personId` được bind riêng khi thực thi. Không cần ghép giá trị vào chuỗi query.

Tuy nhiên, cú pháp sau không hợp lệ:

~~~cypher
MATCH (n:$label)
RETURN n
~~~

Parameter `$label` đang được đặt ở vị trí token label theo cách thông thường. Cypher không diễn giải nó như tên label.

Tương tự, cú pháp này cũng không hợp lệ:

~~~cypher
MATCH (a)-[r:$relationshipType]->(b)
RETURN a, r, b
~~~

Lý do là label và relationship type trong pattern vốn là thành phần cấu trúc của query. Cách bind giá trị property như `$personId` không tự động áp dụng cho mọi thành phần cú pháp.

Từ Neo4j 5.26, Cypher bổ sung cú pháp dynamic label và dynamic relationship type. Cú pháp này cho phép biểu diễn token động qua expression và parameter mà không cần ghép chuỗi query.

## 3. Dùng dynamic label và relationship type từ Neo4j 5.26

### Dynamic label trong MATCH

Cú pháp:

~~~cypher
MATCH (n:$($label))
RETURN n
~~~

`$label` là parameter được đánh giá trong expression `$()` để xác định label cần match.

Ví dụ:

~~~cypher
MATCH (n:$($label))
WHERE n.tenantId = $tenantId
  AND n.externalId = $externalId
RETURN n.externalId AS id,
       n.displayName AS displayName
~~~

Ứng dụng bind ba giá trị `label`, `tenantId` và `externalId`. Label được truyền theo dynamic token syntax; hai giá trị còn lại là property parameters thông thường.

### Dynamic relationship type trong MATCH

Cú pháp:

~~~cypher
MATCH (a)-[r:$($relationshipType)]->(b)
RETURN a, type(r) AS relationshipType, b
~~~

Ví dụ:

~~~cypher
MATCH (source:Person {
    tenantId: $tenantId,
    personId: $sourceId
})-[r:$($relationshipType)]->(target:Person {
    tenantId: $tenantId
})
RETURN target.personId AS targetId,
       type(r) AS relationshipType
~~~

Parameter `relationshipType` chọn loại quan hệ tại runtime. Hướng relationship vẫn được xác định bởi pattern `->`.

Expression dynamic phải trả về một `STRING NOT NULL` hoặc danh sách string không null. Với một relationship pattern, relationship chỉ có đúng một type; truyền danh sách có nhiều type sẽ không khớp relationship nào. Trong use case thông thường, hãy bind một string lấy từ `RelationshipKind`.

Dynamic token syntax không có nghĩa là mọi chuỗi do người dùng gửi đều nên được chấp nhận. Ứng dụng vẫn phải kiểm tra lựa chọn theo quyền và nghiệp vụ trước khi bind.

### Dynamic label và relationship type trong CREATE hoặc MERGE

Neo4j 5.26 trở lên cũng hỗ trợ dynamic token trong `CREATE` và `MERGE`.

~~~cypher
CREATE (n:$($label) {
    tenantId: $tenantId,
    externalId: $externalId,
    displayName: $displayName
})
RETURN labels(n) AS labels,
       n.externalId AS externalId
~~~

~~~cypher
MATCH (a:Person {
    tenantId: $tenantId,
    personId: $sourceId
})
MATCH (b:Person {
    tenantId: $tenantId,
    personId: $targetId
})
MERGE (a)-[r:$($relationshipType)]->(b)
ON CREATE SET r.createdAt = $createdAt
RETURN type(r) AS relationshipType
~~~

Với các thao tác ghi, allowlist và authorization đặc biệt quan trọng. Một label hoặc relationship type có cú pháp hợp lệ vẫn có thể không được phép tạo trong use case hiện tại.

Dynamic token syntax được giới thiệu ở Neo4j 5.26. Nếu ứng dụng phải chạy trên server cũ hơn, hãy dùng query template cố định được chọn từ allowlist; không quay lại ghép dữ liệu request vào Cypher.

## 4. Allowlist label ở application layer

Giả sử API hỗ trợ tìm hai loại node: `Person` và `Team`. Hãy biểu diễn lựa chọn này bằng enum:

~~~java
import java.util.Arrays;

public enum NodeKind {

    PERSON("Person"),
    TEAM("Team");

    private final String label;

    NodeKind(String label) {
        this.label = label;
    }

    public String label() {
        return label;
    }

    public static NodeKind fromApi(String value) {
        return Arrays.stream(values())
            .filter(kind -> kind.name().equalsIgnoreCase(value))
            .findFirst()
            .orElseThrow(() ->
                new IllegalArgumentException("Unsupported node kind")
            );
    }
}
~~~

API nhận một lựa chọn nghiệp vụ như `PERSON`. Ứng dụng chuyển nó thành enum và lấy label cố định từ enum.

Không dùng trực tiếp `request.getLabel()` làm label cho query. Ví dụ:

~~~java
// Không an toàn: request quyết định trực tiếp cấu trúc query.
String query = "MATCH (n:" + request.getLabel() + ") RETURN n";
~~~

Thay vào đó, chuyển giá trị đầu vào thành một lựa chọn đã được xác nhận:

~~~java
NodeKind kind = NodeKind.fromApi(request.getKind());
String label = kind.label();
~~~

Nếu giá trị không nằm trong allowlist, từ chối request trước khi gửi query. Không cố "làm sạch" bằng cách xóa dấu cách hoặc dấu câu rồi tiếp tục dùng tên token tùy ý; cách đó có thể biến một đầu vào không hợp lệ thành lựa chọn ngoài dự kiến.

Allowlist cũng giúp giới hạn phạm vi nghiệp vụ. Một tài khoản ứng dụng có thể được phép truy vấn `Person` và `Team`, nhưng không có nghĩa API tìm kiếm công khai được quyền chọn label nội bộ như `Credential`, `AuditRecord` hoặc `PaymentSecret`.

## 5. Bind dynamic label bằng Neo4jClient

`Neo4jClient` cung cấp fluent API để bind parameter vào query. Ví dụ dưới đây giả định các loại node được tìm kiếm đều có `tenantId`, `externalId` và `displayName`.

~~~java
import java.util.Collection;
import java.util.Map;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;

@Repository
public class GraphSearchRepository {

    private final Neo4jClient client;

    public GraphSearchRepository(Neo4jClient client) {
        this.client = client;
    }

    public Collection<Map<String, Object>> search(
            NodeKind kind,
            String tenantId,
            String searchText,
            int requestedLimit
    ) {
        int limit = Math.max(1, Math.min(requestedLimit, 100));

        return client.query("""
                MATCH (n:$($label))
                WHERE n.tenantId = $tenantId
                  AND n.displayName CONTAINS $searchText
                RETURN n.externalId AS id,
                       n.displayName AS displayName
                ORDER BY displayName
                LIMIT $limit
                """)
            .bind(kind.label()).to("label")
            .bind(tenantId).to("tenantId")
            .bind(searchText).to("searchText")
            .bind(limit).to("limit")
            .fetch()
            .all();
    }
}
~~~

Các điểm cần chú ý:

- Query template vẫn được khai báo rõ ràng trong code.
- `label` đến từ enum đã được allowlist.
- `tenantId`, `searchText` và `limit` được bind thành dữ liệu.
- Kết quả chỉ trả hai field cần thiết, không trả toàn bộ node.
- `limit` được giới hạn ở application layer để tránh request lấy lượng dữ liệu quá lớn.

Ví dụ này dùng cùng property contract cho `Person` và `Team`. Nếu các label có cấu trúc property khác nhau, hãy định nghĩa DTO/query template riêng theo từng loại thay vì giả định mọi node đều có cùng schema.

## 6. Allowlist relationship type

Tạo enum riêng cho loại quan hệ mà một use case được phép truy vấn:

~~~java
import java.util.Arrays;

public enum RelationshipKind {

    KNOWS("KNOWS"),
    REPORTS_TO("REPORTS_TO");

    private final String type;

    RelationshipKind(String type) {
        this.type = type;
    }

    public String type() {
        return type;
    }

    public static RelationshipKind fromApi(String value) {
        return Arrays.stream(values())
            .filter(kind -> kind.name().equalsIgnoreCase(value))
            .findFirst()
            .orElseThrow(() ->
                new IllegalArgumentException(
                    "Unsupported relationship kind"
                )
            );
    }
}
~~~

Repository có thể nhận enum này và bind type:

~~~java
public Collection<Map<String, Object>> findOutgoingPeople(
        RelationshipKind relationshipKind,
        String tenantId,
        String sourcePersonId
) {
    return client.query("""
            MATCH (source:Person {
                tenantId: $tenantId,
                personId: $sourcePersonId
            })-[r:$($relationshipType)]->(target:Person {
                tenantId: $tenantId
            })
            RETURN target.personId AS targetId,
                   type(r) AS relationshipType
            ORDER BY targetId
            """)
        .bind(relationshipKind.type()).to("relationshipType")
        .bind(tenantId).to("tenantId")
        .bind(sourcePersonId).to("sourcePersonId")
        .fetch()
        .all();
}
~~~

Enum ngăn API chọn một relationship type không thuộc chức năng. Dynamic token syntax giữ type nằm trong parameter, không được ghép vào chuỗi query.

Cần xác định rõ mỗi loại relationship có ý nghĩa gì. Ví dụ `REPORTS_TO` có thể được phép trong màn hình sơ đồ tổ chức, còn `OWNS_CREDENTIAL` không được phép xuất hiện trong chức năng tìm quan hệ công khai dù query có thể chạy được.

## 7. Hướng relationship và các phần query structure khác

Dynamic relationship type chỉ làm type trở thành động. Hướng quan hệ vẫn là một phần của pattern:

- `-[r:TYPE]->` là outgoing.
- `<-[r:TYPE]-` là incoming.
- `-[r:TYPE]-` là undirected.

Không thể bind một parameter thông thường để thay `->` thành `<-`. Nếu API cho phép chọn hướng, hãy chuyển lựa chọn thành enum rồi chọn một trong các query template cố định.

Ví dụ:

~~~java
public enum TraversalDirection {
    OUTGOING,
    INCOMING,
    UNDIRECTED
}
~~~

~~~java
private static final String OUTGOING_QUERY = """
    MATCH (source:Person {
        tenantId: $tenantId,
        personId: $personId
    })-[r:$($relationshipType)]->(target:Person {
        tenantId: $tenantId
    })
    RETURN target.personId AS targetId,
           type(r) AS relationshipType
    """;

private static final String INCOMING_QUERY = """
    MATCH (source:Person {
        tenantId: $tenantId,
        personId: $personId
    })<-[r:$($relationshipType)]-(target:Person {
        tenantId: $tenantId
    })
    RETURN target.personId AS targetId,
           type(r) AS relationshipType
    """;

private static final String UNDIRECTED_QUERY = """
    MATCH (source:Person {
        tenantId: $tenantId,
        personId: $personId
    })-[r:$($relationshipType)]-(target:Person {
        tenantId: $tenantId
    })
    RETURN target.personId AS targetId,
           type(r) AS relationshipType
    """;

private static String queryFor(TraversalDirection direction) {
    return switch (direction) {
        case OUTGOING -> OUTGOING_QUERY;
        case INCOMING -> INCOMING_QUERY;
        case UNDIRECTED -> UNDIRECTED_QUERY;
    };
}

public Collection<Map<String, Object>> findPeople(
        TraversalDirection direction,
        RelationshipKind relationshipKind,
        String tenantId,
        String personId
) {
    return client.query(queryFor(direction))
        .bind(relationshipKind.type()).to("relationshipType")
        .bind(tenantId).to("tenantId")
        .bind(personId).to("personId")
        .fetch()
        .all();
}
~~~

`queryFor` chỉ chọn giữa ba chuỗi query hằng số trong source code. Không có phần nào của request được nối vào query string.

Cùng cách này áp dụng cho những lựa chọn cấu trúc khác như:

- Có hoặc không có `OPTIONAL MATCH`.
- Một trong các pattern đường đi đã định nghĩa.
- Một trong các thứ tự sắp xếp được hỗ trợ.
- Một trong các nhánh `UNION` đã được kiểm soát.
- Một trong các procedure hoặc clause được ứng dụng cho phép.

Khi query có nhiều tổ hợp cấu trúc, hãy tạo query builder với các lựa chọn kiểu enum hoặc dùng Cypher DSL phù hợp. Không tạo một ngôn ngữ truy vấn tùy ý bằng cách nhận cả đoạn Cypher từ client.

## 8. Dynamic property key và sắp xếp

Property key cũng cần được xử lý riêng. Cú pháp như sau không hợp lệ:

~~~cypher
MATCH (n:Person)
WHERE n.$propertyName = $value
RETURN n
~~~

Cypher hỗ trợ truy cập property động bằng dấu ngoặc vuông:

~~~cypher
MATCH (n:Person)
WHERE n[$propertyName] = $value
RETURN n.personId AS personId
~~~

Với Neo4j hỗ trợ dynamic property access, `$propertyName` là giá trị được bind. Khi cập nhật:

~~~cypher
MATCH (n:Person {
    tenantId: $tenantId,
    personId: $personId
})
SET n[$propertyName] = $value
RETURN n.personId AS personId
~~~

Tuy nhiên, không nên cho client tự chọn mọi property. Hãy giới hạn bằng enum:

~~~java
public enum EditablePersonProperty {

    DISPLAY_NAME("displayName"),
    STATUS("status");

    private final String propertyName;

    EditablePersonProperty(String propertyName) {
        this.propertyName = propertyName;
    }

    public String propertyName() {
        return propertyName;
    }
}
~~~

Không cho phép request cập nhật những field như `tenantId`, `ownerId`, `createdBy`, `role` hoặc metadata bảo mật thông qua một endpoint cập nhật property tổng quát. Những field đó cần use case riêng và authorization cụ thể.

Với `ORDER BY`, có thể dùng dynamic property expression như `n[$sortProperty]`, nhưng chỉ cho phép một danh sách property đã xác định. Nếu cần thứ tự tăng/giảm, hãy chuyển direction thành enum và chọn query template hoặc biểu thức cố định; không nối chuỗi `ASC` hay `DESC` trực tiếp từ request.

## 9. Repository @Query hay Neo4jClient?

Repository query phù hợp khi pattern và loại node đã biết trước:

~~~java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

// Giả sử Person là @Node entity trong cùng package.
public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (p:Person {
            tenantId: $tenantId,
            personId: $personId
        })
        RETURN p
        """)
    Optional<Person> findPerson(
        @Param("tenantId") String tenantId,
        @Param("personId") String personId
    );
}
~~~

Các giá trị `tenantId` và `personId` được bind như parameter. Label `Person` được cố định trong query.

Khi cần dynamic label hoặc relationship type, `Neo4jClient` thường phù hợp hơn vì service có thể chọn query template, bind dynamic token và ánh xạ kết quả theo nhu cầu.

| Cách tiếp cận | Dùng khi | Kiểm soát cần có |
|---|---|---|
| Repository `@Query` | Pattern cố định, method gắn với domain entity | Bind mọi giá trị dữ liệu |
| `Neo4jClient` với dynamic token | Label/type thay đổi trong phạm vi allowlist, server hỗ trợ Neo4j 5.26+ | Enum allowlist, bind token và property |
| Nhiều query template cố định | Server cũ hoặc cấu trúc pattern/hướng thay đổi | Chỉ chọn template từ enum hoặc map nội bộ |
| Cypher DSL/query builder | Query có nhiều tổ hợp cấu trúc được ứng dụng tạo | Builder chỉ nhận thành phần đã xác thực |

Dù dùng API nào, không để người dùng gửi raw query, raw pattern hoặc tên procedure tùy ý.

## 10. Cypher injection và các cách triển khai không an toàn

### Ghép label hoặc relationship type vào query

Không nên:

~~~java
String query = "MATCH (n:" + request.label() + ") RETURN n";
return client.query(query).fetch().all();
~~~

Khi dữ liệu request được nối trực tiếp vào query, người dùng có thể tác động đến cấu trúc Cypher. Việc chỉ kiểm tra chuỗi không rỗng hoặc xóa một số ký tự không phải cơ chế bảo vệ đáng tin cậy.

Nên dùng dynamic token parameter trên Neo4j 5.26+:

~~~java
return client.query("""
        MATCH (n:$($label))
        WHERE n.tenantId = $tenantId
        RETURN n.externalId AS id
        """)
    .bind(validatedKind.label()).to("label")
    .bind(tenantId).to("tenantId")
    .fetch()
    .all();
~~~

Hoặc chọn query template cố định qua allowlist khi server không hỗ trợ dynamic token.

### Ghép property value vào query

Không nên:

~~~java
String query = "MATCH (p:Person {name: '" + request.name() + "'}) RETURN p";
~~~

Nên:

~~~java
client.query("""
        MATCH (p:Person {name: $name})
        RETURN p.personId AS personId
        """)
    .bind(request.name()).to("name")
    .fetch()
    .all();
~~~

### Nhận raw query từ client

Không xây API như:

~~~json
{
  "cypher": "MATCH (n) RETURN n"
}
~~~

API công khai nên nhận filter có kiểu dữ liệu rõ ràng như `nodeKind`, `relationshipKind`, `direction`, `searchText` và `limit`. Server chịu trách nhiệm tạo query từ những lựa chọn đã được xác thực.

### Tự escape identifier bằng backtick

Cypher cho phép dùng backtick để quote identifier. Tuy nhiên, tự ghép identifier và tự escape backtick rất dễ bỏ sót trường hợp Unicode hoặc ký tự đặc biệt. Không chọn cách này khi có thể dùng parameterized dynamic token hoặc query template cố định.

## 11. Parameterization không thay thế authorization

Một truy vấn có parameter binding vẫn có thể truy cập sai dữ liệu nếu tài khoản database có quyền quá rộng hoặc query thiếu điều kiện phân quyền.

Với ứng dụng nhiều tenant, lấy tenant ID từ security context đã xác thực, không lấy từ một field request body mà client có thể tự sửa.

~~~java
public Collection<Map<String, Object>> findPeople(
        NodeKind kind,
        SearchRequest request
) {
    String tenantId = currentTenant.requireTenantId();

    return graphSearchRepository.search(
        kind,
        tenantId,
        request.searchText(),
        request.limit()
    );
}
~~~

Query phải đưa tenant scope vào pattern hoặc điều kiện lọc:

~~~cypher
MATCH (p:Person {
    tenantId: $tenantId,
    personId: $personId
})
RETURN p.personId AS personId,
       p.displayName AS displayName
~~~

Không dựa vào label động để phân tách tenant. Hai tenant có thể cùng sử dụng label `Person`; tenant boundary cần được kiểm tra bằng tenant key và/hoặc mô hình phân quyền database.

### Áp dụng least privilege ở Neo4j

Neo4j hỗ trợ role-based access control với quyền đọc, duyệt graph và ghi. Ở các phiên bản/edition hỗ trợ graph privileges, quyền có thể được giới hạn theo label, relationship type và property.

Ví dụ minh họa cho tài khoản chỉ đọc Person:

~~~cypher
GRANT ACCESS
ON DATABASE neo4j
TO app_reader;

GRANT TRAVERSE
ON GRAPH neo4j NODES Person
TO app_reader;

GRANT TRAVERSE
ON GRAPH neo4j RELATIONSHIPS KNOWS
TO app_reader;

GRANT READ {personId, displayName, tenantId}
ON GRAPH neo4j NODES Person
TO app_reader;
~~~

Cú pháp và khả năng áp dụng quyền phụ thuộc phiên bản Neo4j và edition đang triển khai. Hãy xác nhận các privilege được hỗ trợ trong môi trường thật trước khi đưa vào migration.

Tài khoản chạy ứng dụng không nên mặc định có quyền quản trị schema, tạo label/type mới, xóa database hoặc thực thi mọi procedure. Tách credential đọc và ghi nếu ứng dụng có các workload với quyền khác nhau.

## 12. Giới hạn kết quả và hiệu năng truy vấn động

Dynamic label và relationship type giúp tái sử dụng query template, nhưng không bảo đảm mọi pattern có hiệu năng như nhau.

Hãy lưu ý:

- Giới hạn kết quả bằng `LIMIT` và dùng pagination khi cần.
- Tránh `RETURN n` nếu client chỉ cần một vài property.
- Tạo index phù hợp cho các property lọc thường xuyên như `tenantId`, `personId` hoặc `externalId`.
- Dùng `EXPLAIN` và `PROFILE` để xem plan thực tế trên phiên bản Neo4j đang chạy.
- So sánh query động với query label/type cố định nếu đây là đường truy vấn có tải cao.
- Tránh tạo projection hoặc traversal không giới hạn độ sâu từ dữ liệu request.
- Đặt timeout và giới hạn concurrency cho tác vụ graph tốn tài nguyên.

Dynamic token syntax không xóa bỏ chi phí tìm kiếm. Đặc biệt, implementation và khả năng tận dụng index của dynamic label/type có thể khác giữa các phiên bản Neo4j. Hãy đo bằng query plan và dữ liệu gần với production thay vì suy luận từ cú pháp.

Tài liệu Cypher hiện hành mô tả các mốc hiệu năng cho dynamic `MATCH` như sau:

| Phiên bản Neo4j | Hành vi planner được tài liệu ghi nhận |
|---|---|
| 5.26 đến 2025.07 | Chưa tận dụng index scan/seek cho dynamic token; planner phải dùng `AllNodesScan` |
| 2025.08 đến 2025.10 | Có thể dùng token lookup index cho dynamic label/type, nhưng chưa dùng index trên property value |
| 2025.11 trở lên | Có thể dùng exact seek trên range index cho property value; chưa hỗ trợ full-text/spatial seek, tận dụng index order hoặc kết hợp nhiều index seek cho nhiều dynamic label |

Đây là mô tả planner của `MATCH` trong tài liệu phiên bản hiện hành; hãy kiểm tra đúng phiên bản server và query plan của ứng dụng trước khi áp dụng kết luận cho workload cụ thể.

Nếu một use case chỉ hỗ trợ hai label cố định và cần hiệu năng có thể dự đoán, hai query template tĩnh có thể dễ tối ưu hơn một query động tổng quát. Chọn cách phù hợp dựa trên số lượng loại token, khả năng bảo trì và kết quả đo.

## 13. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `MATCH (n:$label)` báo syntax error | Parameter được dùng trực tiếp ở vị trí label | Dùng `MATCH (n:$($label))` trên Neo4j 5.26+ |
| Dynamic token báo không hỗ trợ | Server Neo4j cũ hơn phiên bản hỗ trợ | Dùng query template cố định được chọn từ allowlist |
| Query chạy nhưng không có kết quả | Label hoặc relationship type không khớp dữ liệu | Kiểm tra enum mapping và token thực tế |
| Người dùng chọn được loại node không được phép | Chưa có allowlist ở application layer | Chuyển request thành enum và từ chối giá trị lạ |
| Truy vấn trả dữ liệu tenant khác | Query thiếu tenant predicate hoặc tenant lấy từ request không tin cậy | Lấy tenant từ security context và kiểm tra mọi pattern |
| `n.$property` báo lỗi | Property key được viết như một parameter thông thường | Dùng `n[$property]` nếu phiên bản hỗ trợ, kèm allowlist |
| Query thay đổi khi nhận input lạ | Ghép chuỗi input vào query structure | Dùng parameter hoặc template cố định |
| Query động chậm hơn dự kiến | Planner không chọn plan/index như query tĩnh | Dùng `PROFILE`, bổ sung index và benchmark |
| Tài khoản có thể ghi label/type ngoài chức năng | Database privilege quá rộng | Giới hạn quyền CREATE, SET LABEL và relationship type |
| API trả quá nhiều dữ liệu | Thiếu LIMIT, pagination hoặc projection field | Giới hạn đầu ra và chỉ trả field cần thiết |

## 14. Kiểm thử bảo mật cho query động

Một bộ test nên xác minh cả tính hợp lệ của lựa chọn và ranh giới dữ liệu:

1. Giá trị enum hợp lệ tạo đúng query và trả kết quả mong đợi.
2. Label không nằm trong allowlist bị từ chối trước khi gọi Neo4jClient.
3. Relationship type không nằm trong allowlist bị từ chối.
4. Direction không hợp lệ không được dùng để tạo query.
5. Chuỗi tìm kiếm chứa dấu nháy hoặc ký tự Cypher vẫn chỉ được coi là giá trị dữ liệu.
6. `tenantId` lấy từ security context được bind vào mọi query cần tenant isolation.
7. User không thể yêu cầu property nhạy cảm qua endpoint dynamic property.
8. Giới hạn `limit` được áp dụng ngay cả khi request gửi số rất lớn.
9. Tài khoản chỉ đọc không thể thực hiện thao tác ghi.
10. Query động được chạy trên đúng phiên bản Neo4j mà ứng dụng hỗ trợ.

Ví dụ unit test cho allowlist:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class NodeKindTest {

    @Test
    void acceptsSupportedKind() {
        assertThat(NodeKind.fromApi("PERSON"))
            .isEqualTo(NodeKind.PERSON);
    }

    @Test
    void rejectsUnknownKind() {
        assertThatThrownBy(() ->
            NodeKind.fromApi("AUDIT_RECORD")
        ).isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

Unit test xác nhận lựa chọn đầu vào. Integration test với Neo4j xác nhận cú pháp dynamic token được server hỗ trợ và query trả đúng graph. Test authorization cần chạy với credential/role tương ứng, không chỉ mock repository.

## 15. Checklist trước khi phát hành query động

- [ ] Mọi giá trị dữ liệu đều được bind thành parameter.
- [ ] Label và relationship type chỉ lấy từ allowlist.
- [ ] Dynamic token syntax chỉ dùng khi Neo4j server hỗ trợ.
- [ ] Direction và clause được chọn từ query template cố định.
- [ ] Property key động được giới hạn theo use case.
- [ ] Không nhận raw Cypher hoặc raw pattern từ client.
- [ ] Tenant ID đến từ security context đáng tin cậy.
- [ ] Query chỉ trả property mà người gọi được phép xem.
- [ ] Tài khoản Neo4j tuân theo least privilege.
- [ ] Có LIMIT, pagination và timeout phù hợp.
- [ ] Đã kiểm tra EXPLAIN/PROFILE trên dữ liệu gần production.
- [ ] Có unit test allowlist và integration test trên đúng phiên bản Neo4j.

## 16. Bài tập thực hành

Xây dựng API tìm kiếm graph cho ứng dụng có hai label `Person`, `Team` và hai relationship type `KNOWS`, `REPORTS_TO`.

Thực hiện:

1. Tạo enum `NodeKind` với hai label được phép.
2. Tạo enum `RelationshipKind` với hai type được phép.
3. Tạo enum `TraversalDirection` cho outgoing, incoming và undirected.
4. Viết API nhận loại node, từ khóa và giới hạn kết quả.
5. Dùng Neo4jClient và dynamic label syntax để tìm node.
6. Viết query dynamic relationship type để tìm hàng xóm của một Person.
7. Chọn hướng quan hệ bằng ba query template cố định.
8. Lấy tenant ID từ security context và bind vào mọi query.
9. Thêm giới hạn tối đa 100 kết quả.
10. Viết test từ chối label/type không nằm trong allowlist.
11. Thử chuỗi tìm kiếm có dấu nháy và xác nhận nó không làm thay đổi query.
12. Chạy integration test trên Neo4j 5.26+ và so sánh với query template tĩnh.
13. Dùng PROFILE để so sánh plan và thời gian thực thi.
14. Tạo một role chỉ đọc và xác minh tài khoản đó không thể ghi graph.

Câu hỏi tự kiểm tra:

- Vì sao `MATCH (n:$label)` không phải cách bind label hợp lệ?
- Cú pháp `MATCH (n:$($label))` được hỗ trợ từ phiên bản Neo4j nào?
- Dynamic token có thay thế allowlist không?
- Vì sao hướng relationship cần query template riêng?
- Khi nào nên dùng `@Query` và khi nào nên dùng `Neo4jClient`?
- Property key động được truy cập bằng cú pháp nào?
- Parameterization và authorization khác nhau ra sao?
- Vì sao tenant ID phải đến từ security context?
- RBAC có thể giới hạn quyền theo label và relationship type như thế nào?
- Cần kiểm tra gì bằng `EXPLAIN` và `PROFILE` trước khi phát hành?

## Kết luận

Kiểm soát label, relationship type và query structure đòi hỏi phân biệt rõ token Cypher với giá trị dữ liệu. Parameter binding là lựa chọn mặc định cho property values. Từ Neo4j 5.26, dynamic token syntax `:$($label)` và `:$($relationshipType)` cho phép dùng label/type động mà không ghép chuỗi query. Ứng dụng vẫn cần allowlist để giới hạn lựa chọn theo nghiệp vụ.

Với hướng quan hệ và các phần cấu trúc khác, hãy chọn giữa những query template cố định hoặc query builder chỉ nhận thành phần đã xác thực. Kết hợp Neo4jClient binding, tenant scoping, RBAC least privilege, giới hạn kết quả và kiểm thử trên đúng phiên bản server để query động an toàn và có thể vận hành.

## Tài liệu tham khảo

- [Neo4j Cypher Manual: Parameters](https://neo4j.com/docs/cypher-manual/current/syntax/parameters/)
- [Neo4j Cypher Manual: MATCH with dynamic node labels and relationship types](https://neo4j.com/docs/cypher-manual/25/clauses/match/)
- [Neo4j Cypher Manual: CREATE with dynamic node labels and relationship types](https://neo4j.com/docs/cypher-manual/current/clauses/create/)
- [Neo4j Cypher Manual: MERGE with dynamic node labels and relationship types](https://neo4j.com/docs/cypher-manual/current/clauses/merge/)
- [Neo4j Java Driver Manual: Further query mechanisms](https://neo4j.com/docs/java-manual/current/query-advanced/)
- [Spring Data Neo4j: Neo4jClient](https://docs.spring.io/spring-data/neo4j/reference/appendix/neo4j-client.html)
- [Neo4j Operations Manual: Role-based access control](https://neo4j.com/docs/operations-manual/current/authentication-authorization/manage-privileges/)
- [Neo4j Operations Manual: Write privileges](https://neo4j.com/docs/operations-manual/current/authentication-authorization/privileges-writes/)
