# Kiểm thử QBE, Querydsl và bộ lọc nhiều điều kiện

Một bộ lọc động có thể trả về những bản ghi nhìn qua đều hợp lý nhưng vẫn sai nghiệp vụ: một điều kiện bị bỏ qua, một nhóm OR làm rộng phạm vi tenant, hoặc giá trị `false` bị hiểu nhầm thành không lọc. Chỉ kiểm tra truy vấn chạy không lỗi hoặc kết quả không rỗng thường không phát hiện được các lỗi này.

Trong chương **Kiểm thử** của module **SPRING_DATA_COMMONS**, bài học này trình bày cách kiểm thử Query by Example, Querydsl và bộ lọc nhiều điều kiện bằng dữ liệu đối chứng và kết quả kỳ vọng rõ ràng. Các abstraction truy vấn, phân trang, sắp xếp và metadata của Spring Data cần được kiểm chứng trên đúng store hỗ trợ chúng; không giả định rằng mọi module đều cung cấp cùng khả năng QBE hoặc Querydsl.

## 1. Viết hợp đồng bộ lọc trước khi viết assertion

Một hợp đồng tìm kiếm cần trả lời:

- Điều kiện nào luôn bắt buộc?
- Điều kiện nào được bỏ qua khi không có đầu vào?
- Các điều kiện kết hợp bằng AND hay OR, có nhóm ngoặc nào?
- `null`, chuỗi rỗng, chuỗi toàn khoảng trắng và `false` có ý nghĩa gì?
- Các cận khoảng có bao gồm giá trị bằng cận không?
- Kết quả có thứ tự nào và được phân trang ra sao?

Ví dụ trong bài chọn quy tắc:

```text
Phạm vi bắt buộc:
    tenantId = tenant hiện tại

Các bộ lọc tùy chọn:
    name: chứa chuỗi sau khi trim, không phân biệt hoa thường
    city: bằng chính xác giá trị sau khi trim
    active: null là không lọc; true và false đều là giá trị lọc
    minAge, maxAge: cận bao gồm nếu được cung cấp

Một chế độ lựa chọn:
    khi activeOrVip = true, thêm nhóm (active = true OR vip = true)

Mọi điều kiện được cung cấp kết hợp bằng AND,
riêng activeOrVip có một nhóm OR nằm bên trong.
```

`tenantId` được truyền riêng từ ngữ cảnh phạm vi đã xác định của ứng dụng. Không để một bộ lọc tùy chọn rỗng làm biến mất điều kiện này.

Đây là hợp đồng của ứng dụng minh họa, không phải các quy tắc chuẩn hóa đầu vào mà Spring Data tự động áp dụng cho mọi truy vấn.

## 2. Chọn fixture có khả năng phân biệt đúng và sai

Dùng một bảng dữ liệu nhỏ, có chủ đích. `code` là nhãn duy nhất trong fixture để đọc kết quả dễ hơn; ID persistence vẫn được quản lý theo mapping của entity.

| code | tenantId | name | city | active | vip | age |
| --- | ---: | --- | --- | --- | --- | ---: |
| A | 42 | Lan Nguyen | Hanoi | true | false | 25 |
| B | 42 | LAN Tran | Danang | false | true | 17 |
| C | 42 | Mai | Hanoi | false | true | 25 |
| D | 42 | An | null | false | false | 40 |
| E | 7 | Lan Ngo | Hanoi | true | true | 35 |
| F | 42 | Lan Le | Hanoi | false | false | 21 |
| G | 42 | Lan Pham | Danang | true | false | 18 |
| H | 42 | Lan Do | Hanoi | null | true | 19 |
| I | 7 | Khach ngoai | Hue | false | true | 45 |
| J | 42 | Thanh Lan | Hanoi | true | false | 60 |

Các bản ghi được chọn để bắt những lỗi khác nhau:

- E gần giống một kết quả hợp lệ theo tên và thành phố nhưng thuộc tenant khác.
- I thỏa điều kiện VIP ở tenant khác, giúp phát hiện OR đặt sai nhóm.
- F có `active = false`, phân biệt lọc false với bỏ qua bộ lọc.
- H có `active = null`, phân biệt null với false.
- B nằm dưới cận 18, G bằng đúng cận, H nằm ngay phía trên.
- A và C có cùng tuổi, giúp kiểm tra khóa sắp xếp phụ.
- J có chuỗi Lan ở cuối, giúp phân biệt contains với startsWith.

Nếu tất cả fixture đều active, cùng tenant và cùng thành phố, một bộ lọc bỏ quên nửa số điều kiện vẫn có thể vượt qua test.

### 2.1. Môi trường chạy ví dụ

Ví dụ code chọn **Spring Data JPA trên cơ sở dữ liệu quan hệ** có hỗ trợ các thao tác được dùng. Entity `Customer` có các thuộc tính trong bảng, cùng ID và version nếu mapping dùng version. `active` và `vip` dùng `Boolean`, `age` dùng `Integer`, `tenantId` dùng `Long`, để probe có thể biểu diễn giá trị không được cung cấp bằng `null`.

Repository minh họa:

```java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                QuerydslPredicateExecutor<Customer> {
}
```

Trong ví dụ JPA này, repository có khả năng thực thi QBE qua các interface được `JpaRepository` kế thừa, đồng thời bổ sung Querydsl executor. Không suy ra rằng việc thêm cùng các interface vào repository của một store bất kỳ sẽ luôn hoạt động.

Các đoạn test phía dưới giả định repository thật đã được inject, fixture được nạp vào kho test riêng và thay đổi đã được đồng bộ trước truy vấn. Nếu dùng JPA, cần flush rồi clear khi phù hợp để tránh chỉ quan sát các entity trong persistence context. Entity mapping, cấu hình test và generated Q-type không được triển khai thành một dự án hoàn chỉnh trong bài.

## 3. QBE: kiểm thử probe và matcher cùng với kết quả

QBE gồm probe mang dữ liệu và `ExampleMatcher` diễn đạt cách khớp. Các giá trị `null` thường được bỏ qua theo cấu hình mặc định, còn thuộc tính primitive có giá trị mặc định vẫn có thể bị đưa vào tiêu chí nếu không bị bỏ qua.

QBE cũng không biểu diễn tùy ý các nhóm điều kiện lồng nhau như `x AND (y OR z)`. Khả năng so khớp chuỗi phụ thuộc store. Xem [các khái niệm và giới hạn QBE](https://docs.spring.io/spring-data/commons/reference/query-by-example.html).

### 3.1. Tạo Example chỉ từ các trường được phép lọc

Ví dụ bộ tạo QBE cho tập điều kiện đơn giản: tenant, tên, thành phố và active.

```java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

public final class CustomerExamples {

    private CustomerExamples() {
    }

    public static Example<Customer> search(
            long tenantId,
            String name,
            String city,
            Boolean active) {
        if (tenantId <= 0) {
            throw new IllegalArgumentException("tenantId không hợp lệ");
        }

        Customer probe = new Customer();
        probe.setTenantId(tenantId);
        probe.setName(normalize(name));
        probe.setCity(normalize(city));
        probe.setActive(active);

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
                .withIgnoreNullValues()
                .withIgnorePaths("id", "code", "vip", "age", "version")
                .withMatcher("name", match ->
                        match.contains().ignoreCase())
                .withMatcher("city", match -> match.exact());

        return Example.of(probe, matcher);
    }

    private static String normalize(String value) {
        if (value == null) {
            return null;
        }
        String normalized = value.strip();
        return normalized.isEmpty() ? null : normalized;
    }
}
```

Đoạn này giả định constructor và setter của entity dùng được cho probe, các trường chưa đặt không tự nhận giá trị nghiệp vụ khác. Các đường dẫn bị ignore phải đúng với entity cụ thể. Nếu entity không có version hoặc có thêm auditing metadata, điều chỉnh danh sách theo mapping thực tế.

Không dùng trực tiếp một entity vừa đọc từ database làm probe tìm kiếm rồi vô tình mang cả ID, version, thời điểm tạo hoặc các cờ mặc định vào điều kiện.

### 3.2. Kiểm thử trường hợp false được giữ lại

```java
Example<Customer> example = CustomerExamples.search(
        42L, "  lan  ", "Hanoi", false);

List<String> actual = codes(repository.findAll(example));

assertEquals(1, actual.size());
assertEquals(Set.of("F"), new HashSet<>(actual));
```

Theo fixture, F là bản ghi duy nhất thỏa tenant 42, tên chứa Lan, thành phố Hanoi và active false. Nếu bộ tạo lọc nhầm `false` thành “không cung cấp”, các bản ghi A, H hoặc J có thể xuất hiện ngoài ý muốn.

Các assertion dùng JUnit Jupiter. Hàm hỗ trợ chuyển kết quả thành nhãn fixture có thể viết:

```java
private static List<String> codes(Iterable<Customer> customers) {
    List<String> result = new ArrayList<>();
    customers.forEach(customer -> result.add(customer.getCode()));
    return result;
}
```

Các kiểu collection sử dụng import từ `java.util`. Vừa kiểm tra kích thước vừa so sánh tập nhãn giúp không che mất kết quả lặp. Nếu ứng dụng không có mã nghiệp vụ duy nhất phù hợp, dùng tập ID trả về từ fixture thay vì ép thêm một thuộc tính chỉ để phục vụ assertion.

### 3.3. Khi active không được cung cấp

```java
Example<Customer> example = CustomerExamples.search(
        42L, "LAN", "Hanoi", null);

List<String> actual = codes(repository.findAll(example));

assertEquals(4, actual.size());
assertEquals(Set.of("A", "F", "H", "J"), new HashSet<>(actual));
```

H được đưa vào vì không có điều kiện active, không phải vì null được coi bằng false hoặc true. J được đưa vào vì hợp đồng tên là contains, không phải chỉ khớp tiền tố.

Test này cũng kiểm chứng hành vi không phân biệt hoa thường cho những chuỗi ASCII đã chọn trên store của ví dụ. Nó chưa chứng minh tự động bỏ dấu tiếng Việt hoặc đáp ứng mọi quy tắc Unicode và collation.

### 3.4. Null trong đầu vào không mặc định là tìm cột null

Trong helper trên, city null có nghĩa bỏ qua điều kiện city. Nếu muốn tìm bản ghi có city null, cần một hợp đồng khác, chẳng hạn một chế độ tìm giá trị thiếu.

Một QBE riêng cho mục tiêu đó có thể dùng:

```java
Customer probe = new Customer();
probe.setTenantId(42L);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIncludeNullValues()
        .withIgnorePaths(
                "id", "code", "name", "active", "vip", "age", "version");

Example<Customer> cityIsNull = Example.of(probe, matcher);

assertEquals(List.of("D"), codes(repository.findAll(cityIsNull)));
```

Ở đây, những thuộc tính null không định dùng làm điều kiện được ignore rõ ràng; city vẫn nằm trong phần được xét. Nếu chỉ bật include-null trên một probe gần như rỗng, có thể vô tình yêu cầu nhiều cột khác cùng null.

### 3.5. Primitive và giá trị mặc định cần fixture đối chứng

Nếu một phiên bản entity dùng `boolean active`, probe mặc định đã có `false`; nó không biểu diễn được “chưa chọn active” giống `Boolean null`. Nếu có `int age`, giá trị 0 cũng có thể tham gia QBE khi không bị ignore.

Một ca không cung cấp các điều kiện tùy chọn phải xác nhận toàn bộ dữ liệu trong tenant được trả về theo chính sách đã chọn, thay vì chỉ xác nhận kết quả không rỗng.

Với helper này, tên toàn khoảng trắng, city null và active null phải trả A, B, C, D, F, G, H, J: đúng 8 bản ghi của tenant 42.

## 4. Đừng dùng matchingAny để thay cho nhóm OR tùy ý

Giả sử probe mang tenant 42 và tên Lan. Dùng `matchingAny()` làm các tiêu chí đó kết hợp theo ý nghĩa “khớp bất kỳ”, gần với:

```text
 tenantId = 42 OR name chứa Lan
```

Nó không có nghĩa:

```text
 tenantId = 42 AND một nhóm điều kiện tùy chọn nào đó
```

Bản ghi E thuộc tenant 7 nhưng có tên Lan là đối chứng để bắt lỗi mở rộng phạm vi. Chỉ có fixture trong tenant 42 thì lỗi này rất khó lộ ra.

Khi nghiệp vụ yêu cầu nhóm `(active OR vip)` bên trong phạm vi tenant, nên dùng cơ chế truy vấn biểu diễn đúng nhóm đó và được store hỗ trợ, chẳng hạn Querydsl ở ví dụ JPA này. Không viết test mong QBE cung cấp một khả năng mà abstraction không cam kết.

## 5. Querydsl: kiểm thử ý nghĩa biểu thức, không dựa vào chuỗi debug

Giả định dự án đã cấu hình Querydsl phù hợp bộ phiên bản và có generated type `QCustomer`. Q-type biểu diễn các thuộc tính của entity và phải được tạo từ mapping đúng; nó không tự xuất hiện chỉ vì repository kế thừa `QuerydslPredicateExecutor`.

Bộ lọc đầu vào:

```java
public record CustomerFilter(
        String name,
        String city,
        Boolean active,
        Integer minAge,
        Integer maxAge,
        boolean activeOrVip) {
}
```

Bộ tạo predicate:

```java
import com.querydsl.core.types.Predicate;
import com.querydsl.core.types.dsl.BooleanExpression;

public final class CustomerPredicates {

    private CustomerPredicates() {
    }

    public static Predicate search(long tenantId, CustomerFilter filter) {
        if (tenantId <= 0 || filter == null) {
            throw new IllegalArgumentException("Thiếu phạm vi hoặc bộ lọc");
        }
        if (filter.minAge() != null && filter.maxAge() != null
                && filter.minAge() > filter.maxAge()) {
            throw new IllegalArgumentException("Khoảng tuổi không hợp lệ");
        }

        QCustomer customer = QCustomer.customer;
        BooleanExpression predicate = customer.tenantId.eq(tenantId);

        String name = normalize(filter.name());
        if (name != null) {
            predicate = predicate.and(customer.name.containsIgnoreCase(name));
        }

        String city = normalize(filter.city());
        if (city != null) {
            predicate = predicate.and(customer.city.eq(city));
        }

        if (filter.active() != null) {
            predicate = predicate.and(customer.active.eq(filter.active()));
        }
        if (filter.minAge() != null) {
            predicate = predicate.and(customer.age.goe(filter.minAge()));
        }
        if (filter.maxAge() != null) {
            predicate = predicate.and(customer.age.loe(filter.maxAge()));
        }
        if (filter.activeOrVip()) {
            BooleanExpression selectedGroup = customer.active.isTrue()
                    .or(customer.vip.isTrue());
            predicate = predicate.and(selectedGroup);
        }

        return predicate;
    }

    private static String normalize(String value) {
        if (value == null) {
            return null;
        }
        String normalized = value.strip();
        return normalized.isEmpty() ? null : normalized;
    }
}
```

Các chính sách khác, ví dụ tuổi không được âm hoặc null có nghĩa là một trạng thái đặc biệt, có thể cần validation riêng. Không coi bộ tạo minh họa là validation đầy đủ của mọi domain.

### 5.1. Ca bắt lỗi nhóm AND/OR

```java
CustomerFilter filter = new CustomerFilter(
        null, null, null, 18, null, true);
Predicate predicate = CustomerPredicates.search(42L, filter);

List<String> actual = codes(repository.findAll(predicate));

assertEquals(5, actual.size());
assertEquals(Set.of("A", "C", "G", "H", "J"),
        new HashSet<>(actual));
```

Biểu thức cần đúng:

```text
 tenantId = 42
 AND age >= 18
 AND (active = true OR vip = true)
```

Trong tập này:

- C và H được chọn nhờ VIP.
- G được chọn vì bằng đúng cận tuổi 18.
- B bị loại do tuổi 17.
- D và F bị loại vì không active cũng không VIP.
- E và I bị loại do tenant khác.

Nếu viết nhầm chuỗi theo dạng `(tenant AND age AND active) OR vip`, các bản ghi E, I và B có thể lọt qua nhánh VIP. Fixture cho phép quan sát lỗi đó bằng kết quả, thay vì cố so sánh dấu ngoặc trong `predicate.toString()`.

Chuỗi debug của predicate không phải hợp đồng ổn định về SQL hoặc kết quả. Nó cũng không chứng minh được cách store xử lý null, collation hay mapping.

### 5.2. Ca biên cho khoảng tuổi

Với tenant 42 và không có nhóm active/VIP:

| minAge | maxAge | Kết quả theo fixture | Mục tiêu |
| ---: | ---: | --- | --- |
| 18 | 18 | G | Hai cận bao gồm |
| 17 | 18 | B, G | Kiểm tra đúng giá trị bằng từng cận |
| 19 | 25 | A, C, F, H | Không nhầm `>` với `>=` hoặc `<` với `<=` |
| null | 18 | B, G | Chỉ có cận trên |
| 60 | null | J | Chỉ có cận dưới |
| 25 | 18 | Từ chối đầu vào | Không âm thầm tạo truy vấn vô nghĩa |

Có thể viết các ca này dưới dạng parameterized test. Dữ liệu kỳ vọng phải được đưa vào từ bảng hợp đồng, không được tính bằng cách gọi lại chính helper tạo predicate.

### 5.3. Boolean false vẫn là điều kiện được cung cấp

Điều kiện cần kiểm tra là `filter.active() != null`, không phải chỉ kiểm tra nó có giá trị true.

Với active false và mọi bộ lọc khác bỏ trống trong tenant 42, tập kết quả là B, C, D, F. H không thuộc tập này, vì null khác false.

## 6. Kiểm thử phối hợp điều kiện theo lớp rủi ro

Với nhiều bộ lọc tùy chọn, không phải lúc nào cũng cần vét cạn toàn bộ tổ hợp. Có thể bắt đầu bằng ma trận có mục tiêu:

| Nhóm ca | Dữ liệu đầu vào | Điều được bảo vệ |
| --- | --- | --- |
| Cơ sở | Không có bộ lọc tùy chọn | Điều kiện tenant vẫn tồn tại |
| Đơn lẻ | Mỗi lần chỉ có một điều kiện | Không quên nhánh hoặc đọc nhầm thuộc tính |
| Phối hợp | Hai điều kiện có kết quả giao khác từng tập riêng | AND không bị thay bằng OR |
| Nhóm | Tenant và khoảng tuổi cùng `(active OR vip)` | Dấu ngoặc không làm rộng phạm vi |
| Giá trị đặc biệt | active false, null, chuỗi trắng | Không nhầm giá trị với sự vắng mặt |
| Cận | Dưới, bằng và trên cận | Đúng toán tử khoảng |
| Không khớp | Bộ lọc hợp lệ nhưng không có entity | Trả kết quả rỗng đúng kiểu |
| Lặp và phân trang | Có giá trị sort bằng nhau | Thứ tự ổn định và không lặp kết quả ngoài hợp đồng |

Nếu mở rộng bộ lọc bằng danh sách thành phố, phải quyết định rõ danh sách rỗng có nghĩa bỏ qua điều kiện hay không có kết quả. Không để hành vi mặc định của một phép `in(emptyList)` tình cờ trở thành chính sách nghiệp vụ.

Tương tự, nếu ký tự `%` hoặc `_` trong chuỗi tìm kiếm phải được hiểu là ký tự thường, cần một ca riêng trên store thật có fixture chứa ký tự đó và một fixture gần giống. Đừng suy ra chính sách escape của mọi store từ một test với tên chỉ có chữ cái.

## 7. Đối chiếu QBE và Querydsl trong phần hợp đồng tương đương

Có thể dùng cùng một yêu cầu đơn giản để kiểm tra hai cách thực thi, nhưng chỉ khi các điều kiện tương đương và đều được store hỗ trợ.

Ví dụ: tenant 42, name chứa Lan không phân biệt hoa thường, city Hanoi, active false.

```java
Example<Customer> example = CustomerExamples.search(
        42L, "lan", "Hanoi", false);

Predicate predicate = CustomerPredicates.search(42L,
        new CustomerFilter("lan", "Hanoi", false, null, null, false));

List<String> qbeCodes = codes(repository.findAll(example));
List<String> querydslCodes = codes(repository.findAll(predicate));

assertEquals(1, qbeCodes.size());
assertEquals(1, querydslCodes.size());
assertEquals(Set.of("F"), new HashSet<>(qbeCodes));
assertEquals(Set.of("F"), new HashSet<>(querydslCodes));
```

Chỉ so sánh `qbeCodes` với `querydslCodes` là chưa đủ: cả hai helper có thể cùng mắc một lỗi chuẩn hóa hoặc cùng bỏ quên active. Tập kỳ vọng F là điểm đối chiếu độc lập từ yêu cầu và fixture.

Không dùng test tương đương để ép QBE hỗ trợ khoảng tuổi hoặc nhóm OR lồng nhau. Khi hợp đồng khác nhau, hãy có bộ test riêng cho từng khả năng.

## 8. Kiểm thử count, exists và cardinality

Với predicate đã chọn được A, C, G, H, J, có thể kiểm tra:

```java
assertEquals(5L, repository.count(predicate));
assertTrue(repository.exists(predicate));
```

Với một điều kiện hợp lệ không khớp fixture, cần xác nhận count bằng 0, exists false và kết quả findAll rỗng. Không lấy kích thước từ cùng một truy vấn làm nguồn kỳ vọng duy nhất cho mọi assertion; nên có số lượng xác định từ fixture.

`findOne` không có nghĩa là chọn tùy ý một kết quả đầu tiên. Cần ba ca:

1. Không có kết quả: `Optional.empty()`.
2. Đúng một kết quả: trả entity đó.
3. Có nhiều kết quả: báo lỗi cardinality theo API.

Ví dụ Querydsl trên fixture:

```java
QCustomer customer = QCustomer.customer;

assertTrue(repository.findOne(
        customer.tenantId.eq(42L).and(customer.code.eq("Z")))
        .isEmpty());

assertEquals("A", repository.findOne(
        customer.tenantId.eq(42L).and(customer.code.eq("A")))
        .orElseThrow().getCode());

assertThrows(IncorrectResultSizeDataAccessException.class, () ->
        repository.findOne(customer.tenantId.eq(42L)));
```

`IncorrectResultSizeDataAccessException` thuộc `org.springframework.dao`. Cùng nguyên tắc cardinality áp dụng cho `QueryByExampleExecutor.findOne` khi Example có nhiều kết quả, theo [QBE executor API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/query/QueryByExampleExecutor.html) và [Querydsl executor API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/querydsl/QuerydslPredicateExecutor.html).

Nếu ứng dụng thật sự cần “kết quả đầu”, phải có API và thứ tự lựa chọn rõ ràng; không chuyển sang `findOne` rồi dựa vào dữ liệu test tình cờ chỉ có một dòng.

## 9. Phân trang và sort phải giữ nguyên bộ lọc

Dùng predicate nhóm ở phần trên và sort theo tuổi tăng dần, sau đó code tăng dần:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Sort sort = Sort.by("age").ascending()
        .and(Sort.by("code").ascending());

Page<Customer> first = repository.findAll(
        predicate, PageRequest.of(0, 2, sort));
Page<Customer> second = repository.findAll(
        predicate, PageRequest.of(1, 2, sort));
Page<Customer> third = repository.findAll(
        predicate, PageRequest.of(2, 2, sort));

assertEquals(List.of("G", "H"), codes(first.getContent()));
assertEquals(List.of("A", "C"), codes(second.getContent()));
assertEquals(List.of("J"), codes(third.getContent()));
assertEquals(5L, first.getTotalElements());
assertEquals(3, first.getTotalPages());
assertTrue(first.hasNext());
assertFalse(third.hasNext());
```

A và C cùng tuổi 25, nên code là khóa phụ quyết định thứ tự. Không kiểm thử thứ tự hai entity có cùng giá trị sort chính mà thiếu quy tắc phân xử.

Ngoài nội dung từng trang, kiểm tra rằng tổng số phần tử tính theo đúng bộ lọc, không phải toàn bộ tenant hoặc toàn bộ bảng. Nếu truy vấn có join tới quan hệ nhiều phần tử, cần fixture làm xuất hiện nguy cơ trùng entity và kiểm tra cả dữ liệu lẫn count theo hợp đồng truy vấn cụ thể.

Trong các test phân trang tĩnh này, fixture không thay đổi giữa các lần đọc. Việc dữ liệu đồng thời bị thêm hoặc sửa giữa các trang là một yêu cầu nhất quán khác, cần thiết kế và kiểm thử riêng.

## 10. Phân chia unit test và integration test

### 10.1. Unit test cho chính sách xây dựng đầu vào

Những quy tắc có thể kiểm tra nhanh mà không cần store:

- Chuỗi toàn khoảng trắng được chuẩn hóa thành không lọc.
- Min lớn hơn max bị từ chối.
- Thiếu phạm vi tenant hợp lệ bị từ chối.
- active false được giữ như giá trị được cung cấp.
- Chế độ “tìm city null” tách biệt với “không lọc city”.

Không cần khóa unit test vào toàn bộ biểu diễn chuỗi của Querydsl. Nếu mục tiêu là kiểm tra kết quả lọc thật, unit test một object predicate khác null không đủ.

### 10.2. Integration test cho ngữ nghĩa trên store

Cần repository thật để kiểm chứng:

- Matcher được dịch và thực thi đúng trên mapping của entity.
- Null, Boolean và kiểu số có ngữ nghĩa mong muốn.
- Các điều kiện AND/OR phối hợp đúng.
- So khớp chuỗi đáp ứng chính sách case, collation và ký tự đặc biệt đã chọn.
- Sort, page, count và cardinality nhất quán.

Mock trả về danh sách mong muốn cho `findAll(any(Predicate.class))` chỉ kiểm tra cách tầng dịch vụ tiêu thụ danh sách. Nó không kiểm tra việc predicate lọc đúng dữ liệu.

Cũng không nên dùng chính bộ tạo predicate để lọc fixture trong bộ nhớ rồi lấy kết quả đó làm oracle duy nhất. Khi cả kỳ vọng lẫn truy vấn dựa vào cùng một logic lỗi, test có thể vẫn xanh.

## 11. Những dấu hiệu cho thấy bộ test đang bỏ sót lỗi

| Dấu hiệu | Lỗi có thể bị che | Cải thiện fixture hoặc assertion |
| --- | --- | --- |
| Chỉ có dữ liệu thuộc một tenant | Quên điều kiện phạm vi hoặc OR làm rộng phạm vi | Thêm E và I ở tenant khác |
| Chỉ có active true | Bỏ qua active false | Thêm false và null, kiểm tra riêng từng chế độ |
| Chỉ kiểm tra kết quả không rỗng | Trả quá nhiều hoặc thiếu một phần dữ liệu | So sánh tập ID hoặc code kỳ vọng cùng số lượng |
| Tên chỉ xuất hiện ở đầu | Dùng startsWith thay contains vẫn qua | Thêm J với Lan ở cuối |
| Không có dữ liệu bằng cận | Dùng toán tử khoảng sai | Có tuổi 17, 18 và 19 quanh cận 18 |
| Không có giá trị sort bằng nhau | Thiếu khóa phụ vẫn khó lộ | Thêm A và C cùng tuổi |
| Dùng entity đã lưu làm probe | ID hoặc metadata làm truy vấn quá hẹp | Tạo probe mới và quản lý ignore paths |
| Chỉ so sánh QBE với Querydsl | Hai cách cùng sai vẫn khớp | Có kết quả kỳ vọng độc lập |
| So sánh predicate.toString | Phụ thuộc biểu diễn và chưa quan sát store | Chạy repository thật trên fixture đối chứng |
| Chỉ kiểm tra page content | Count query có thể bỏ sót điều kiện | Assertion totalElements và những trang tiếp theo |

Một bộ kiểm thử có ích phải cho thấy bản ghi nào được chọn và bản ghi nào phải bị loại, cùng lý do của từng nhóm. Khi QBE, Querydsl hoặc bộ lọc động được thay đổi, các đối chứng này giữ cho điều kiện nghiệp vụ, phạm vi truy vấn và kiểu kết quả tiếp tục thống nhất trên đúng store mà ứng dụng sử dụng.
