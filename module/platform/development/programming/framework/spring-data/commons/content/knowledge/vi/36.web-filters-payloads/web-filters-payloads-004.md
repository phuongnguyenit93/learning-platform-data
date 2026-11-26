# Giới hạn thuộc tính được lọc và loại trường nhạy cảm

Một endpoint tìm kiếm không nên mặc nhiên cho phép client lọc theo mọi property của entity. Domain có thể chứa mã tenant, quyền hạn, thông tin xác thực, điểm đánh giá nội bộ hoặc metadata mà người gọi không được dùng làm điều kiện truy vấn.

Bài học thuộc chương **Bộ lọc và payload web** của module **SPRING_DATA_COMMONS**. Mục tiêu là xây dựng hợp đồng lọc có giới hạn, minh họa bằng Querydsl Web Support, đồng thời phân biệt quyền lọc với quyền đọc, sắp xếp và ghi dữ liệu. Commons cung cấp abstraction; khả năng thực thi Querydsl, Query by Example và projection phải được đối chiếu với store đang sử dụng.

## 1. Một property có nhiều quyền sử dụng khác nhau

Xét domain tài khoản có các thuộc tính:

```text
id
displayName
status
tenantId
passwordHash
recoveryToken
mfaSecret
roles
internalRiskScore
deleted
createdBy
lastModifiedBy
```

Việc một property tồn tại trong Java không có nghĩa nó được phép xuất hiện trong mọi hợp đồng HTTP.

Cần trả lời riêng bốn câu hỏi:

| Loại quyền | Câu hỏi |
| --- | --- |
| Lọc | Client được dùng property này để chọn bản ghi không? |
| Sắp xếp | Client được dùng property này để quyết định thứ tự không? |
| Đọc | Property này có được xuất hiện trong response không? |
| Ghi | Client được cung cấp giá trị để thay đổi property này không? |

Ví dụ chính sách cho một API danh bạ tài khoản nội bộ đã có phân quyền:

| Thuộc tính | Lọc | Sort | Response danh bạ | Payload sửa tên |
| --- | --- | --- | --- | --- |
| `id` | Không trong bộ lọc chung này | Có | Có | Không |
| `displayName` | Có | Có | Có | Có |
| `status` | Có, với tập giá trị cho phép | Không | Có | Không |
| `tenantId` | Server xác định | Không | Không | Không |
| `passwordHash`, `recoveryToken`, `mfaSecret` | Không | Không | Không | Không |
| `roles`, `internalRiskScore` | Không | Không | Không | Không |
| `deleted`, `createdBy`, `lastModifiedBy` | Không nhận tùy ý từ client | Không | Không | Không |

Đây là một hợp đồng minh họa, không phải quy tắc rằng status hay tên hiển thị luôn được công khai trong mọi hệ thống. Một API quản trị có thể có các quyền khác và nên thể hiện chúng qua hợp đồng riêng.

## 2. Ẩn field trong JSON chưa ngăn được lọc theo field đó

Giả sử response chỉ gồm:

```json
{
  "id": 42,
  "displayName": "Lan",
  "status": "ACTIVE"
}
```

Nếu endpoint vẫn chấp nhận một điều kiện trên field nội bộ, kết quả có thể khác nhau tùy giá trị field đó. Client có thể quan sát danh sách rỗng hay không rỗng hoặc tổng số phần tử, dù field không được serialize.

Vì vậy:

- DTO hoặc projection đầu ra kiểm soát biểu diễn được công khai.
- Allowlist bộ lọc kiểm soát property được dùng để truy vấn.
- Chính sách phạm vi dữ liệu kiểm soát bản ghi người gọi được tiếp cận.
- Chính sách ghi kiểm soát những thay đổi được phép thực hiện.

Một annotation ẩn JSON không thay thế ba chính sách còn lại. Tương tự, không cho lọc theo `roles` chưa đồng nghĩa đã ngăn client gửi `roles` trong một payload cập nhật khác.

## 3. Chọn danh sách cho phép thay vì chỉ liệt kê trường cấm

### 3.1. Danh sách loại trừ dễ bỏ sót khi domain thay đổi

Một cách cấu hình có thể là loại:

```text
passwordHash, recoveryToken, mfaSecret
```

Cách này thể hiện được một số điều cấm hiện tại. Nhưng nếu sau đó domain thêm `internalRiskScore`, property mới có thể vô tình đi vào một cơ chế binding rộng.

Với một endpoint có tập bộ lọc nhỏ, cách dễ kiểm soát hơn là công bố đúng những trường được phép:

```text
Các field lọc:
- displayName
- status

Các field khác:
- Không được dùng làm bộ lọc của endpoint này.
```

Thêm property vào entity lúc đó không tự mở rộng hợp đồng tìm kiếm.

### 3.2. Hợp đồng còn gồm toán tử và số lượng giá trị

“Cho phép lọc displayName” vẫn chưa đủ rõ. Cần xác định:

| Nội dung | Chính sách minh họa |
| --- | --- |
| Tên tham số | `displayName` |
| Toán tử | Chứa chuỗi, không phân biệt hoa thường |
| Số giá trị | Đúng một nếu được truyền |
| Chuỗi rỗng | Từ chối |
| Độ dài | Từ 2 đến 80 ký tự |
| Status | Một giá trị trong `ACTIVE`, `SUSPENDED` |
| Không truyền bộ lọc | Trả dữ liệu trong phạm vi được phép, theo chính sách endpoint |

Không tự cho phép biểu thức toán tử tùy ý, regex hay đường dẫn lồng nhau chỉ vì field gốc có trong danh sách.

Một phép tìm “contains” có thể đắt hơn phép so sánh bằng. Chính sách property cần đi cùng giới hạn giá trị và đánh giá khả năng truy vấn của store; không mặc định mọi phép lọc đều dùng được cùng một kiểu index.

## 4. Giới hạn property bằng QuerydslBindings

Các ví dụ Querydsl dưới đây giả định:

- Mã ví dụ dùng Java 17 trở lên.
- Ứng dụng dùng Spring MVC và đã đăng ký Querydsl Web Support phù hợp.
- Có dependency Querydsl tương thích và Q-type đã được sinh.
- Domain `Account` có Q-type `QAccount`, với `displayName` là chuỗi và `status` là enum.
- Store và repository thực sự hỗ trợ thực thi Querydsl; Spring Data JPA là một bối cảnh minh họa có thể sử dụng.
- Các đoạn mã thể hiện từng phần tích hợp, không phải một ứng dụng độc lập đã bao gồm mapping và cấu hình dữ liệu.

### 4.1. Customizer chỉ mở hai property

```java
import org.springframework.data.querydsl.binding.QuerydslBinderCustomizer;
import org.springframework.data.querydsl.binding.QuerydslBindings;

public class PublicAccountBindings
        implements QuerydslBinderCustomizer<QAccount> {

    @Override
    public void customize(
            QuerydslBindings bindings,
            QAccount root) {

        bindings.excludeUnlistedProperties(true);
        bindings.including(root.displayName, root.status);

        bindings.bind(root.displayName)
                .first((path, value) ->
                        path.containsIgnoreCase(value));

        bindings.bind(root.status)
                .first((path, value) ->
                        path.eq(value));
    }
}
```

`excludeUnlistedProperties(true)` hạn chế các property không được công bố hoặc binding tường minh. `including(...)` thể hiện tập property được phép. Binding trên từng path xác định cách diễn giải giá trị.

Các API này được mô tả trong [QuerydslBindings](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/querydsl/binding/QuerydslBindings.html). Điểm mở rộng `customize(bindings, root)` thuộc [QuerydslBinderCustomizer](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/querydsl/binding/QuerydslBinderCustomizer.html).

Không nên hiểu danh sách hiện tại là bất biến trước mọi thay đổi cấu hình: nếu sau này thêm một binding tường minh cho property khác, cần đánh giá nó như một thay đổi của hợp đồng HTTP.

### 4.2. Gắn customizer vào đúng tham số của endpoint

Chữ ký handler có thể sử dụng:

```java
import com.querydsl.core.types.Predicate;

import org.springframework.data.domain.Pageable;
import org.springframework.data.querydsl.binding.QuerydslPredicate;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.web.PagedModel;
import org.springframework.util.MultiValueMap;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/api/accounts")
PagedModel<AccountSummary> search(
        @QuerydslPredicate(
                root = Account.class,
                bindings = PublicAccountBindings.class)
        Predicate clientPredicate,
        @RequestParam
        MultiValueMap<String, String> parameters,
        @PageableDefault(size = 20, sort = "id")
        Pageable pageable) {

    requireAllowedParameters(parameters);

    return new PagedModel<>(
            queries.search(
                    clientPredicate,
                    checkedPageable(pageable)));
}
```

Đoạn handler được đặt trong controller có `queries` là service của ứng dụng. Hai helper được giải thích ở các phần sau. Ví dụ dùng `org.springframework.data.web.PagedModel` nên cần Spring Data Commons từ 3.3 trở lên.

`root = Account.class` chỉ rõ domain để tạo predicate; response DTO không nhất thiết đủ thông tin để suy ra domain đó. Thuộc tính `bindings` chọn customizer cho tham số này; xem [QuerydslPredicate API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/querydsl/binding/QuerydslPredicate.html).

Khai báo một lớp customizer nhưng không đưa nó vào cơ chế cấu hình đang dùng sẽ không tự đảm bảo endpoint đã áp dụng chính sách mong muốn.

### 4.3. .first không phải kiểm tra đầu vào đơn trị

Binding `.first(...)` sử dụng giá trị đầu khi có nhiều giá trị. Nếu hợp đồng yêu cầu chỉ một status, cần kiểm tra request như:

```http
GET /api/accounts?status=ACTIVE&status=SUSPENDED
```

Không để frontend tưởng cả hai giá trị đều được áp dụng trong khi binder chỉ dùng một giá trị. Kiểm tra cardinality của raw parameters là một phần riêng của hợp đồng.

## 5. Property không được bind có thể bị bỏ qua, không tự trả 400

Một điểm quan trọng: chặn một property khỏi binding không có nghĩa mọi request chứa property đó tự động bị từ chối ở tầng HTTP.

Ví dụ:

```http
GET /api/accounts?internalRiskScore=10
```

Nếu binder bỏ qua property này, predicate từ client có thể trở thành rỗng. Endpoint có thể trả toàn bộ kết quả **trong phạm vi server cho phép**, thay vì trả lỗi.

[Mã nguồn QuerydslPredicateBuilder](https://raw.githubusercontent.com/spring-projects/spring-data-commons/main/src/main/java/org/springframework/data/querydsl/binding/QuerydslPredicateBuilder.java) thể hiện việc bỏ qua path không khả dụng. Vì thế phải phân biệt:

| Mục tiêu | Cơ chế |
| --- | --- |
| Không dùng field cấm để tạo predicate | Chính sách `QuerydslBindings` |
| Báo lỗi khi request chứa tên không được phép | Kiểm tra raw parameter theo hợp đồng API |

Với API chọn chính sách từ chối, có thể dùng helper sau trong controller:

```java
import java.util.List;
import java.util.Set;

import org.springframework.http.HttpStatus;
import org.springframework.util.MultiValueMap;
import org.springframework.web.server.ResponseStatusException;

static void requireAllowedParameters(
        MultiValueMap<String, String> parameters) {

    Set<String> allowed = Set.of(
            "displayName", "status", "page", "size", "sort");

    for (String name : parameters.keySet()) {
        if (!allowed.contains(name)) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Unsupported query parameter");
        }
    }

    for (String name : List.of(
            "displayName", "status", "page", "size")) {

        List<String> values = parameters.get(name);

        if (values != null && values.size() != 1) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Expected a single parameter value");
        }
    }

    String displayName = parameters.getFirst("displayName");

    if (displayName != null
            && (displayName.isBlank()
                || displayName.length() < 2
                || displayName.length() > 80)) {

        throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Invalid displayName filter");
    }

    String status = parameters.getFirst("status");

    if (status != null
            && !Set.of("ACTIVE", "SUSPENDED").contains(status)) {

        throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Invalid status filter");
    }
}
```

Helper này chỉ thực hiện các kiểm tra thể hiện trong mã. Quy tắc parse page/size, giới hạn size và cách báo lỗi chuyển đổi kiểu cần được cấu hình nhất quán ở ứng dụng.

Argument resolver có thể thực hiện chuyển đổi trước khi đi vào thân handler. Vì vậy một lỗi chuyển kiểu vẫn cần được ánh xạ thành phản hồi phù hợp theo cấu hình xử lý lỗi của ứng dụng; không giả định mọi lỗi đều đi qua helper.

Nếu API đổi tên tham số phân trang, dùng qualifier hoặc alias cho bộ lọc, allowlist raw parameters cũng phải thay đổi tương ứng. Không bỏ toàn bộ `sort` chỉ để làm danh sách kiểm tra tên ngắn hơn.

## 6. Điều kiện phạm vi dữ liệu phải do server áp đặt

Loại `tenantId` khỏi danh sách bộ lọc không tự thêm điều kiện tenant vào truy vấn.

Cần đảm bảo:

```text
Điều kiện cuối
    = phạm vi dữ liệu server cho phép
      AND các điều kiện client được phép cung cấp
```

Ví dụ repository có hỗ trợ Querydsl:

```java
import org.springframework.data.querydsl.QuerydslPredicateExecutor;
import org.springframework.data.repository.CrudRepository;

interface AccountRepository
        extends CrudRepository<Account, Long>,
                QuerydslPredicateExecutor<Account> {
}
```

Phần xử lý trong service có thể gồm:

```java
import com.querydsl.core.BooleanBuilder;
import com.querydsl.core.types.Predicate;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

Page<AccountSummary> search(
        Predicate clientPredicate,
        Pageable pageable) {

    String tenantId = tenantContext.requireTenantId();
    QAccount account = QAccount.account;

    BooleanBuilder effective = new BooleanBuilder();
    effective.and(account.tenantId.eq(tenantId));
    effective.and(account.deleted.isFalse());
    effective.and(clientPredicate);

    return repository.findAll(effective, pageable)
            .map(value -> new AccountSummary(
                    value.getId(),
                    value.getDisplayName(),
                    value.getStatus()));
}
```

Giả định `tenantContext` lấy tenant hợp lệ từ ngữ cảnh đã được xác thực và kiểm tra quyền, không lấy tùy ý từ query parameter; trong domain ví dụ, tenant ID có kiểu chuỗi. Chính sách minh họa cho phép đọc danh bạ trong tenant hiện tại và loại bản ghi đã xóa mềm.

`AccountSummary` có thể được định nghĩa:

```java
record AccountSummary(
        Long id,
        String displayName,
        AccountStatus status) {
}
```

`AccountStatus` là enum của domain. Các getter và Q-path trong ví dụ phải khớp mapping thực tế.

Khi predicate client rỗng, điều kiện tenant và xóa mềm vẫn còn. Không đặt điều kiện bắt buộc này vào một binding mà client phải gửi tham số thì mới kích hoạt.

Không ghép phạm vi bằng OR:

```text
tenant hiện tại OR điều kiện client
```

Cách ghép đó có thể cho phép một điều kiện client làm rộng tập kết quả ngoài tenant. Cả nội dung và tổng số phần tử trong phản hồi phải dựa trên cùng phạm vi truy vấn.

## 7. Sort cần một danh sách cho phép riêng

Cấu hình `QuerydslBindings` không thay thế việc kiểm tra các property trong `Sort`.

Client vẫn có thể gửi:

```http
GET /api/accounts?sort=internalRiskScore,desc
```

Ngay cả khi field này không hiện trong JSON, thứ tự có thể tiết lộ quan hệ giữa các giá trị hoặc làm phát sinh truy vấn không mong muốn.

Helper minh họa chỉ cho sort theo id và tên:

```java
import java.util.Set;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

static Pageable checkedPageable(Pageable input) {
    Set<String> allowed = Set.of("id", "displayName");

    for (Sort.Order order : input.getSort()) {
        if (!allowed.contains(order.getProperty())
                || order.isIgnoreCase()) {

            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Unsupported sort");
        }
    }

    Sort sort = input.getSort();

    if (sort.getOrderFor("id") == null) {
        sort = sort.and(Sort.by("id").ascending());
    }

    return PageRequest.of(
            input.getPageNumber(),
            input.getPageSize(),
            sort);
}
```

Ví dụ này giả định nhận `Pageable` có phân trang từ cấu hình của handler. Nó chủ động không nhận tùy chọn ignore-case trong sort; nếu ứng dụng muốn hỗ trợ, cần chính sách tương ứng với kiểu dữ liệu và store.

Danh sách field lọc và field sort có thể khác nhau. Trong hợp đồng này, id được sort nhưng không nằm trong bộ lọc chung; status được lọc nhưng không được sort.

Không coi đường dẫn lồng nhau như `profile.privateEmail` hoặc `credentials.recoveryToken` là được phép chỉ vì có thể biểu diễn dưới dạng chuỗi. Hãy công bố đúng những path được chấp nhận.

## 8. Payload ghi dữ liệu cần hợp đồng riêng

### 8.1. Không bind trực tiếp payload sửa tên vào toàn bộ entity

Một endpoint sửa tên chỉ nên nhận dữ liệu cần cho use case đó:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

record UpdateDisplayNameRequest(
        @NotBlank
        @Size(max = 80)
        String displayName) {
}
```

Controller có thể dùng `@Valid @RequestBody UpdateDisplayNameRequest`, rồi service nạp bản ghi trong phạm vi được phép và chỉ gọi thao tác đổi tên.

Không chuyển toàn bộ map JSON lên entity bằng cách sao chép mọi property trùng tên. `roles`, `tenantId` hoặc metadata auditing không nên được thay đổi chỉ vì client gửi thêm key.

DTO chỉ có displayName giới hạn cấu trúc dữ liệu nhận vào. Việc báo lỗi hay bỏ qua JSON property không biết còn phụ thuộc cấu hình deserialization và hợp đồng API. Nếu muốn từ chối trường dư, cần cấu hình và xác nhận chính sách đó; không suy ra từ riêng định nghĩa record.

### 8.2. WebDataBinder không phải cấu hình Querydsl hoặc Jackson chung

Với property binding cho model attribute, có thể cấu hình:

```java
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

@InitBinder("profileForm")
void initProfileForm(WebDataBinder binder) {
    binder.setAllowedFields("displayName");
}
```

Đây là cấu hình cho cơ chế data binding tương ứng của Spring MVC. Nó không phải một allowlist chung tự áp dụng lên mọi bộ lọc Querydsl.

Đối với JSON `@RequestBody`, nội dung được đọc qua HTTP message converter. Không dùng `setAllowedFields` làm bằng chứng rằng Jackson đã bị giới hạn các property deserialize. Vai trò của binder được mô tả trong [InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html), còn cơ chế body nằm trong [RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html).

Thiết kế DTO theo use case vẫn cần thiết; constructor binding và property binding cũng không nên bị xem là cùng một đường xử lý.

### 8.3. Projection payload không tự hoàn tất chính sách ghi

Spring Data có cơ chế bind payload qua projection trong những cấu hình được hỗ trợ. Một interface chỉ đọc tên hiển thị giúp mô tả dữ liệu ứng dụng muốn truy cập, nhưng không tự quyết định quyền cập nhật tài khoản, cách xử lý field dư hoặc những field server sở hữu.

Service vẫn phải xác định bản ghi được sửa và ánh xạ tường minh những thay đổi được phép.

## 9. Áp dụng cùng nguyên tắc khi không dùng Querydsl

Nếu store không hỗ trợ đường thực thi Querydsl đang xét, có thể nhận một DTO bộ lọc riêng rồi chuyển sang derived query, Query by Example hoặc truy vấn phù hợp. Không thêm dependency Querydsl rồi mặc định mọi store nhận được cùng năng lực.

Với Query by Example:

- Tạo probe từ những field đã được chọn; không bind toàn bộ request vào entity rồi dùng ngay làm probe.
- Xét các property primitive vì giá trị mặc định của chúng có thể tham gia điều kiện.
- Dùng matcher phù hợp để loại path không muốn xét.
- Bảo đảm điều kiện phạm vi bắt buộc không biến thành một nhánh OR tùy chọn khi đổi sang kiểu matching-any.

Hành vi null, primitive và matcher được mô tả trong [Query by Example của Spring Data Commons](https://docs.spring.io/spring-data/commons/reference/query-by-example.html).

Nếu không thể biểu diễn đồng thời phạm vi bắt buộc và bộ lọc mong muốn bằng cơ chế đang dùng, cần chọn cách truy vấn khác được store hỗ trợ. Không giảm yêu cầu về phạm vi dữ liệu để giữ nguyên một abstraction.

Metadata như createdBy, lastModifiedBy hay deleted cũng là property domain cần có chính sách rõ ràng. Hỗ trợ auditing không tự ngăn việc chúng được nhận từ một DTO hoặc một bộ lọc cấu hình quá rộng.

## 10. Xác nhận chính sách theo hành vi của endpoint

Một hợp đồng có giới hạn nên được quan sát qua cả dữ liệu và lỗi HTTP:

| Tình huống | Kết quả mong muốn theo hợp đồng minh họa |
| --- | --- |
| `displayName=Lan` | Lọc theo contains không phân biệt hoa thường |
| `status=ACTIVE` | Áp dụng giá trị status được phép |
| `status=ACTIVE&status=SUSPENDED` | Từ chối vì bộ lọc này là đơn trị |
| Field nhạy cảm được gửi làm query | Không tham gia predicate; API nghiêm ngặt trả lỗi |
| Tên tham số không tồn tại | Không vô tình trở thành một truy vấn rộng mà client không biết |
| `sort=internalRiskScore,desc` | Từ chối theo chính sách sort |
| Đường dẫn nhạy cảm lồng nhau | Không được phép lọc hoặc sort |
| Không truyền bộ lọc | Vẫn giữ phạm vi tenant và điều kiện bắt buộc |
| Client gửi tenant khác | Không thay được phạm vi server xác định |
| Domain thêm một field nội bộ mới | Không tự mở field đó thành bộ lọc |
| Payload sửa tên chứa roles | Không làm roles thay đổi |
| Response dùng DTO không có bí mật | Bí mật không xuất hiện trong nội dung hoặc metadata lỗi |

Một field nhạy cảm phải được xét trên mọi đường sử dụng của nó. Hợp đồng rõ ràng kết hợp allowlist property, kiểm tra giá trị, điều kiện phạm vi do server quản lý, sort riêng và DTO theo use case sẽ giữ các abstraction của Spring Data trong đúng ranh giới ứng dụng mong muốn.
