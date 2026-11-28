# Xây bộ lọc tùy chọn và nhóm điều kiện

Trong ứng dụng thực tế, một màn hình tìm kiếm thường có nhiều tiêu chí mà người dùng có thể để trống: tên, trạng thái, khoảng tuổi, thành phố hoặc ngày tạo. Nếu viết riêng một câu Cypher cho mọi tổ hợp tiêu chí, số lượng query tăng nhanh và khó bảo trì. Cypher-DSL cho phép xây dựng câu truy vấn từ các thành phần có kiểu, thêm điều kiện khi đầu vào có giá trị và kết hợp chúng thành các nhóm `AND`/`OR`.

Với Spring Data Neo4j (SDN), bạn có thể render một `Statement` từ Cypher-DSL rồi thực thi qua `Neo4jClient`. Cách tổ chức tốt là tách ba việc: xác định bộ lọc hợp lệ, xây cây điều kiện và bind giá trị tham số. Cấu trúc Cypher được tạo từ DSL; dữ liệu người dùng được truyền dưới dạng parameter.

## 1. Bộ lọc tùy chọn là gì?

Giả sử ứng dụng tìm `Person` theo các tiêu chí:

- Tên có chứa một đoạn văn bản nếu người dùng nhập tên.
- Tuổi lớn hơn hoặc bằng `minAge` nếu có cận dưới.
- Tuổi nhỏ hơn hoặc bằng `maxAge` nếu có cận trên.
- Trạng thái `active` nếu người dùng chọn trạng thái.
- Thành phố thuộc một trong các thành phố được chọn.

Người dùng có thể chỉ nhập tên, chỉ chọn trạng thái, kết hợp nhiều tiêu chí hoặc không chọn gì. Một bộ lọc tùy chọn không nên tạo điều kiện so sánh với `null` một cách vô tình. Thay vào đó, chỉ thêm điều kiện khi tiêu chí tương ứng có giá trị hợp lệ.

Ví dụ, nếu người dùng nhập tên và chọn `active = true`, điều kiện có ý nghĩa là:

~~~cypher
MATCH (p:Person)
WHERE p.name CONTAINS $name
  AND p.active = $active
RETURN p;
~~~

Nếu người dùng chỉ nhập tên, điều kiện `p.active = $active` không xuất hiện trong truy vấn. Điều này khác với việc bind `$active` thành `null`, vì phép so sánh với `null` trong Cypher không hoạt động như một bộ lọc bị bỏ qua.

## 2. Tạo điều kiện từ Cypher-DSL

Cypher-DSL biểu diễn pattern và điều kiện bằng các đối tượng Java. Ví dụ:

~~~java
import org.neo4j.cypherdsl.core.Condition;
import org.neo4j.cypherdsl.core.Node;
import org.neo4j.cypherdsl.core.Statement;
import org.neo4j.cypherdsl.core.renderer.Renderer;

import static org.neo4j.cypherdsl.core.Cypher.match;
import static org.neo4j.cypherdsl.core.Cypher.node;
import static org.neo4j.cypherdsl.core.Cypher.parameter;

Node person = node("Person").named("p");

Condition nameCondition =
    person.property("name").contains(parameter("name"));

Statement statement = match(person)
    .where(nameCondition)
    .returning(person)
    .build();

String cypher = Renderer.getDefaultRenderer().render(statement);
~~~

Trong ví dụ:

- `node("Person").named("p")` tạo node pattern có label `Person` và alias `p`.
- `person.property("name")` tham chiếu property `name`.
- `parameter("name")` tạo tham số `$name`, không nhúng giá trị trực tiếp vào câu truy vấn.
- `contains(...)` tạo điều kiện tìm chuỗi con.
- `where(...)` gắn điều kiện vào pattern; `returning(...)` xác định dữ liệu trả về.
- `Renderer` chuyển `Statement` thành chuỗi Cypher để thực thi.

Cypher-DSL xây dựng cấu trúc truy vấn dưới dạng object trước khi render. Vì vậy, ứng dụng có thể thêm hoặc bỏ một biểu thức mà không phải nối chuỗi Cypher thủ công.

## 3. Kết hợp điều kiện bằng `AND` và `OR`

Một điều kiện tổng hợp thường gồm các nhóm nhỏ. Ví dụ, người dùng muốn tìm người đang hoạt động và ở Hà Nội hoặc Thành phố Hồ Chí Minh:

~~~java
Condition cityGroup =
    person.property("city").isEqualTo(parameter("hanoi"))
        .or(person.property("city").isEqualTo(parameter("hcmc")));

Condition activeCondition =
    person.property("active").isEqualTo(parameter("active"));

Condition combined = cityGroup.and(activeCondition);
~~~

Ý nghĩa logic là:

~~~cypher
WHERE (p.city = $hanoi OR p.city = $hcmc)
  AND p.active = $active
~~~

Nhóm thành phố dùng `OR` vì chỉ cần khớp một lựa chọn. Nhóm trạng thái kết hợp với nhóm thành phố bằng `AND` vì cả hai yêu cầu đều phải đúng.

Hãy tạo nhóm logic trước rồi mới kết hợp với điều kiện bên ngoài. Điều này làm rõ ý định và tránh lỗi do đọc nhầm thứ tự ưu tiên giữa `AND` và `OR`.

## 4. Hàm gom danh sách điều kiện

Khi số bộ lọc thay đổi theo request, có thể lưu điều kiện vào `List<Condition>`. Hai helper sau lần lượt kết hợp tất cả điều kiện bằng `AND` hoặc kết hợp các lựa chọn bằng `OR`:

~~~java
import java.util.List;

import org.neo4j.cypherdsl.core.Condition;

static Condition allOf(List<Condition> conditions) {
    if (conditions.isEmpty()) {
        throw new IllegalArgumentException("At least one condition is required");
    }

    Condition result = conditions.get(0);
    for (int i = 1; i < conditions.size(); i++) {
        result = result.and(conditions.get(i));
    }
    return result;
}

static Condition anyOf(List<Condition> conditions) {
    if (conditions.isEmpty()) {
        throw new IllegalArgumentException("At least one alternative is required");
    }

    Condition result = conditions.get(0);
    for (int i = 1; i < conditions.size(); i++) {
        result = result.or(conditions.get(i));
    }
    return result;
}
~~~

Không gọi helper với danh sách rỗng. `allOf` không nên tự trả về một điều kiện giả như `true`, và `anyOf` cũng không nên tự trả về `false` nếu ứng dụng chưa định nghĩa rõ ý nghĩa của trường hợp không có lựa chọn. Caller cần quyết định bỏ hẳn nhóm điều kiện hay trả về tập kết quả rỗng.

## 5. Xây dựng truy vấn với các bộ lọc tùy chọn

Ví dụ dưới đây dùng một record làm đầu vào tìm kiếm:

~~~java
import java.util.List;

public record PersonFilter(
    String nameContains,
    Integer minAge,
    Integer maxAge,
    Boolean active,
    List<String> cities
) {
}
~~~

Service xây dựng danh sách điều kiện và map tham số tương ứng:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.neo4j.cypherdsl.core.Condition;
import org.neo4j.cypherdsl.core.Node;
import org.neo4j.cypherdsl.core.Statement;
import org.neo4j.cypherdsl.core.renderer.Renderer;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;

import static org.neo4j.cypherdsl.core.Cypher.match;
import static org.neo4j.cypherdsl.core.Cypher.node;
import static org.neo4j.cypherdsl.core.Cypher.parameter;

@Repository
public class PersonSearchRepository {

    private final Neo4jClient neo4jClient;
    private final Renderer renderer = Renderer.getDefaultRenderer();

    public PersonSearchRepository(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public Collection<Map<String, Object>> search(PersonFilter filter) {
        Node person = node("Person").named("p");
        List<Condition> conditions = new ArrayList<>();
        Map<String, Object> parameters = new HashMap<>();

        if (filter.nameContains() != null && !filter.nameContains().isBlank()) {
            conditions.add(
                person.property("name").contains(parameter("name"))
            );
            parameters.put("name", filter.nameContains().trim());
        }

        if (filter.minAge() != null) {
            conditions.add(
                person.property("age").gte(parameter("minAge"))
            );
            parameters.put("minAge", filter.minAge());
        }

        if (filter.maxAge() != null) {
            conditions.add(
                person.property("age").lte(parameter("maxAge"))
            );
            parameters.put("maxAge", filter.maxAge());
        }

        if (filter.active() != null) {
            conditions.add(
                person.property("active").isEqualTo(parameter("active"))
            );
            parameters.put("active", filter.active());
        }

        if (filter.cities() != null && !filter.cities().isEmpty()) {
            List<Condition> cityAlternatives = new ArrayList<>();
            int index = 0;

            for (String city : filter.cities()) {
                if (city != null && !city.isBlank()) {
                    String parameterName = "city" + index++;
                    cityAlternatives.add(
                        person.property("city").isEqualTo(parameter(parameterName))
                    );
                    parameters.put(parameterName, city.trim());
                }
            }

            if (!cityAlternatives.isEmpty()) {
                conditions.add(anyOf(cityAlternatives));
            }
        }

        // Không có bộ lọc: use case tìm kiếm này chọn trả về danh sách rỗng.
        if (conditions.isEmpty()) {
            return List.of();
        }

        Statement statement = match(person)
            .where(allOf(conditions))
            .returning(person)
            .build();

        String cypher = renderer.render(statement);
        return neo4jClient.query(cypher)
            .bindAll(parameters)
            .fetch()
            .all();
    }
}
~~~

Ví dụ minh họa cách xây dựng điều kiện và thực thi kết quả dạng record qua `Neo4jClient`. Trong ứng dụng thực tế, có thể thay kiểu kết quả `Collection<Map<String, Object>>` bằng DTO hoặc mapper riêng để không đưa kiểu dữ liệu driver ra khỏi tầng repository.

Hai helper `allOf` và `anyOf` ở phần trước cần được đặt trong cùng lớp `PersonSearchRepository`, hoặc trong một utility class có thể gọi được từ repository. Các đoạn code được tách riêng để làm rõ từng trách nhiệm.

Luồng xử lý gồm:

1. Tạo node pattern và các collection chứa điều kiện/tham số.
2. Kiểm tra từng field của `PersonFilter`.
3. Nếu field có giá trị, thêm một `Condition` và thêm giá trị vào map bằng đúng tên parameter.
4. Các thành phố được gom thành nhóm `OR`, sau đó nhóm đó được thêm vào danh sách điều kiện tổng.
5. `allOf` kết hợp các nhóm bằng `AND`.
6. Render `Statement` rồi bind map tham số khi thực thi.

Tên parameter được tạo từ hằng số hoặc quy tắc nội bộ của ứng dụng. Giá trị request chỉ được đặt trong map; không dùng nội dung request để tạo trực tiếp tên parameter hoặc đoạn cú pháp Cypher.

## 6. Nhóm điều kiện lồng nhau

Một bộ lọc có thể có nhiều nhóm logic. Ví dụ: tìm người đang hoạt động, tuổi từ 18 đến 30 và ở Hà Nội hoặc Đà Nẵng:

~~~java
Condition ageGroup =
    person.property("age").gte(parameter("minAge"))
        .and(person.property("age").lte(parameter("maxAge")));

Condition cityGroup =
    person.property("city").isEqualTo(parameter("cityA"))
        .or(person.property("city").isEqualTo(parameter("cityB")));

Condition finalCondition =
    person.property("active").isEqualTo(parameter("active"))
        .and(ageGroup)
        .and(cityGroup);
~~~

Logic mong muốn:

~~~cypher
WHERE p.active = $active
  AND (p.age >= $minAge AND p.age <= $maxAge)
  AND (p.city = $cityA OR p.city = $cityB)
~~~

Các nhóm có thể được lồng sâu hơn, nhưng nên đặt tên biến theo ý nghĩa nghiệp vụ như `ageGroup`, `locationGroup`, `statusGroup`. Cây điều kiện có tên rõ ràng dễ đọc và kiểm thử hơn một biểu thức `and(...).or(...).and(...)` dài.

## 7. Phân biệt nhóm điều kiện tùy chọn và nhóm điều kiện bắt buộc

Không phải bộ lọc nào cũng nên được bỏ qua khi trống. Một số điều kiện là ràng buộc bảo mật hoặc phạm vi dữ liệu, ví dụ tenant ID, quyền truy cập hoặc trạng thái bản ghi được phép xem. Các điều kiện này phải luôn được thêm vào truy vấn.

Ví dụ:

~~~java
conditions.add(
    person.property("tenantId").isEqualTo(parameter("tenantId"))
);
parameters.put("tenantId", currentTenantId);
~~~

`tenantId` lấy từ ngữ cảnh xác thực phía server, không lấy từ giá trị tùy ý của request. Các tiêu chí tìm kiếm như tên hoặc thành phố có thể là tùy chọn; điều kiện phân vùng dữ liệu và quyền truy cập phải được áp dụng nhất quán.

Nếu một nhóm `OR` là tùy chọn, chỉ thêm nhóm đó khi có ít nhất một lựa chọn hợp lệ. Nếu không có lựa chọn nào, hãy quyết định bỏ nhóm theo đúng nghiệp vụ. Không tạo một nhóm rỗng rồi kỳ vọng DSL tự hiểu rằng nhóm đó không ràng buộc kết quả.

## 8. Xử lý khoảng giá trị và đầu vào không hợp lệ

Với khoảng tuổi, nếu `minAge` lớn hơn `maxAge`, bộ lọc không hợp lệ. Nên xác thực trước khi tạo Cypher:

~~~java
if (filter.minAge() != null
        && filter.maxAge() != null
        && filter.minAge() > filter.maxAge()) {
    throw new IllegalArgumentException("minAge must not exceed maxAge");
}
~~~

Tương tự, cần quy định:

- Chuỗi rỗng hoặc chỉ có khoảng trắng được xem là không có bộ lọc hay là giá trị hợp lệ.
- Danh sách thành phố có phần tử trùng lặp có cần loại bỏ không.
- Có giới hạn số lựa chọn trong một nhóm `OR` hay không.
- Giá trị tuổi âm hoặc ngoài miền nghiệp vụ có được chấp nhận không.
- Property có thể không tồn tại trên node thì điều kiện so sánh có cần xử lý riêng không.

Xác thực ở tầng ứng dụng giúp tránh tạo query vô nghĩa và làm rõ hợp đồng API. Việc bind parameter bảo vệ giá trị đầu vào khỏi bị diễn giải thành cú pháp, nhưng không thay thế validation nghiệp vụ.

## 9. Khi không có bộ lọc nào

Nếu tất cả tiêu chí tùy chọn đều trống, có ba chính sách phổ biến:

| Chính sách | Cách thực hiện | Khi phù hợp |
|---|---|---|
| Trả danh sách rỗng | Dừng trước khi render và thực thi query | Search endpoint yêu cầu ít nhất một tiêu chí |
| Trả danh sách mặc định có giới hạn | Tạo query không có `WHERE`, thêm `ORDER BY` và `LIMIT` | Màn hình mặc định hiển thị một số bản ghi gần đây |
| Từ chối request | Ném lỗi validation | API yêu cầu người dùng cung cấp ít nhất một bộ lọc |

Không nên mặc định thực hiện `MATCH (p:Person) RETURN p` không giới hạn khi người dùng gửi request rỗng. Trên graph lớn, điều đó có thể tạo truy vấn tốn kém và trả về lượng dữ liệu ngoài dự kiến.

## 10. Kiểm tra Cypher được render

Trong lúc phát triển, hãy render statement và kiểm tra cấu trúc Cypher trước khi thực thi. Với mỗi tổ hợp filter, xác nhận:

- Điều kiện không được chọn đã bị loại khỏi `WHERE`.
- Mọi parameter xuất hiện trong Cypher đều có giá trị tương ứng trong map bind.
- Các nhóm `OR` được kết hợp đúng với nhóm `AND`.
- Không có tên label, relationship type hoặc đoạn cú pháp lấy trực tiếp từ input.
- Query không có bộ lọc tuân theo chính sách đã chọn.

Bạn có thể viết unit test cho phần xây dựng `Statement` mà không cần kết nối Neo4j. Kiểm tra Cypher render và map tham số riêng giúp phát hiện lỗi cấu trúc trước khi kiểm thử tích hợp.

## 11. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Thêm điều kiện ngay cả khi giá trị là `null` | Query không lọc như mong muốn hoặc không trả kết quả | Chỉ thêm điều kiện khi filter có giá trị |
| Dùng một chuỗi `WHERE` nối thủ công | Khó kiểm soát cú pháp và dễ tạo lỗi injection | Dùng `Condition` và parameter của Cypher-DSL |
| Ghép `AND`/`OR` mà không tạo nhóm | Logic truy vấn khác với yêu cầu nghiệp vụ | Tạo từng nhóm điều kiện rồi kết hợp nhóm |
| Gọi `allOf` hoặc `anyOf` với danh sách rỗng | Không có điều kiện hợp lệ để kết hợp | Kiểm tra danh sách trước khi tạo nhóm |
| Quên thêm giá trị vào parameter map | Cypher có placeholder nhưng thiếu giá trị bind | Quản lý condition và parameter cùng một nhánh |
| Lấy tenant hoặc quyền truy cập từ request | Có thể mở rộng phạm vi dữ liệu trái phép | Lấy điều kiện bảo mật từ context phía server |
| Cho phép request rỗng chạy query không giới hạn | Tải quá nhiều node và gây áp lực hệ thống | Chọn chính sách empty-filter rõ ràng |
| Dùng DSL nhưng không kiểm tra query đã render | Không phát hiện sai cấu trúc hoặc tham số | Kiểm tra statement và map bind trong unit test |

## 12. Tự kiểm tra

1. Vì sao nên bỏ qua điều kiện khi filter tương ứng không có giá trị thay vì bind `null`?
2. Khi nào dùng `AND`, khi nào dùng `OR` trong bộ lọc nhiều lựa chọn?
3. Vì sao nên tạo nhóm thành phố bằng `OR` trước khi kết hợp với các tiêu chí bắt buộc bằng `AND`?
4. `allOf` và `anyOf` cần xử lý thế nào khi danh sách điều kiện rỗng?
5. Vì sao tenant ID và điều kiện quyền truy cập không nên là filter tùy chọn từ request?
6. Có những chính sách nào khi người dùng gửi bộ lọc hoàn toàn rỗng?
7. Vì sao nên kiểm tra Cypher được render và parameter map trong unit test?

Cypher-DSL giúp xây dựng bộ lọc theo cấu trúc thay vì nối chuỗi. Hãy chỉ thêm điều kiện có giá trị, nhóm các lựa chọn thay thế bằng `OR`, kết hợp các nhóm bắt buộc bằng `AND` và bind mọi giá trị riêng khỏi cú pháp. Cách tổ chức này làm truy vấn linh hoạt, dễ kiểm thử và rõ ràng về logic nghiệp vụ.
