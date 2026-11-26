# Optional cho kết quả đơn và thiết kế API sử dụng Optional

## Mục tiêu bài học

`Optional<T>` làm rõ rằng một phương thức có thể tìm được một giá trị hoặc không tìm được giá trị nào. Trong Spring Data, đây là kiểu trả về hữu ích cho query method kết quả đơn. Giá trị của nó nằm ở hợp đồng API: người gọi nhìn thấy và xử lý trường hợp vắng dữ liệu thay vì vô tình sử dụng một tham chiếu null.

Sau bài học, bạn có thể:

- Đọc đúng hợp đồng của repository method trả `Optional<T>`.
- Phân biệt không có kết quả, đầu vào không hợp lệ và truy vấn thất bại.
- Chọn `map`, `flatMap`, `filter`, `ifPresent`, `orElseGet` hoặc `orElseThrow` theo nhu cầu.
- Quyết định khi nào service tiếp tục trả `Optional` và khi nào yêu cầu phải có dữ liệu.
- Thiết kế ranh giới giữa repository, domain, DTO và API bên ngoài mà không lạm dụng `Optional`.

Các ví dụ dùng `java.util.Optional` trong repository đồng bộ. Spring Data Commons cung cấp các abstraction chung; module lưu trữ quyết định khả năng hỗ trợ query method, mapping và cách thực thi. Không tự suy rộng các ví dụ này thành hợp đồng cho mọi loại store hoặc repository reactive.

## 1. `Optional` biểu đạt điều gì trong kết quả truy vấn?

Giả sử domain tài khoản có các thuộc tính:

```text
Account
├── id: Long
├── tenantId: String
├── loginName: String
├── displayName: String
├── recoveryEmail: String, có thể thiếu
└── enabled: boolean
```

Nghiệp vụ yêu cầu `loginName` duy nhất trong một tenant. Điều kiện tra cứu phải chứa đúng phạm vi này và tính duy nhất cần được bảo vệ bằng cơ chế phù hợp ở store.

Repository minh họa:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.data.repository.CrudRepository;

interface AccountRepository extends CrudRepository<Account, Long> {

    Optional<Account> findByTenantIdAndLoginName(
            String tenantId, String loginName);

    List<Account> findByTenantIdAndEnabledTrue(String tenantId);
}
```

Domain `Account` cần được mapping và repository cần được kích hoạt bởi một module lưu trữ hỗ trợ các phương thức trên.

Với query method trả kết quả đơn:

| Kết quả truy vấn | Hành vi mong đợi |
| --- | --- |
| Không có tài khoản phù hợp | `Optional.empty()` |
| Có đúng một tài khoản phù hợp | `Optional` chứa tài khoản đó |
| Có nhiều tài khoản phù hợp | Lỗi số lượng kết quả, không tự chọn một tài khoản |

`Optional` không thêm giới hạn một bản ghi vào truy vấn. Nếu có nhiều kết quả, Spring Data có thể báo `IncorrectResultSizeDataAccessException` qua cơ chế xử lý ngoại lệ của module tương ứng. Chi tiết nguyên nhân bên dưới còn phụ thuộc store và provider.

Cũng không có quy tắc rằng mọi lỗi đều được đổi thành `Optional.empty()`. Lỗi kết nối, lỗi cú pháp truy vấn hoặc lỗi ánh xạ dữ liệu vẫn là lỗi. Giá trị rỗng chỉ dành cho trường hợp không có kết quả theo hợp đồng.

## 2. Nullability có nhiều trục độc lập

Một chữ ký trả `Optional<Account>` không quyết định tất cả những gì liên quan đến null:

| Vấn đề | Câu hỏi |
| --- | --- |
| Nullability của đầu vào | `tenantId` hoặc `loginName` có được phép null không? |
| Nullability của container | Phương thức có thật sự luôn trả một `Optional` khác null không? |
| Sự hiện diện của tài khoản | `Optional` rỗng hay có giá trị? |
| Nullability của thuộc tính | Tài khoản có thể có `recoveryEmail = null` không? |

Bốn vấn đề này phải được quy định riêng.

Ví dụ, `CrudRepository.findById(...)` trả `Optional`, nhưng điều đó không cho phép gọi `findById(null)`. Tham số định danh của API này bắt buộc khác null; null là lỗi đầu vào, không phải yêu cầu tìm một định danh chưa tồn tại.

Tương tự, một `Optional<Account>` có giá trị không có nghĩa mọi thuộc tính của `Account` đều khác null. Nó chỉ xác nhận container đang chứa một đối tượng.

Annotation và quy ước nullability của dự án có thể giúp công cụ phân tích hoặc hạ tầng kiểm tra hợp đồng. Cần dùng đúng cơ chế được phiên bản Spring và module hiện tại hỗ trợ, đồng thời không nhầm chúng với việc xác thực giá trị nghiệp vụ như chuỗi rỗng hoặc tên đăng nhập không hợp lệ.

## 3. Container `Optional` phải có giá trị hợp lệ

Ba cách tạo cơ bản:

```java
Optional<Account> missing = Optional.empty();

Optional<Account> present = Optional.of(account);

Optional<Account> fromNullable = Optional.ofNullable(possiblyNullAccount);
```

| Cách tạo | Ý nghĩa |
| --- | --- |
| `Optional.empty()` | Không có giá trị |
| `Optional.of(value)` | Phải có giá trị khác null; null gây `NullPointerException` |
| `Optional.ofNullable(value)` | Null thành rỗng, khác null thành có giá trị |

Một phương thức khai báo trả `Optional<Account>` cần trả `Optional.empty()` khi không có dữ liệu, thay vì trả null:

```java
// Vi phạm hợp đồng mong muốn của API trả Optional.
return null;
```

Nếu container có thể null, người gọi lại phải kiểm tra cả null lẫn trạng thái rỗng. Hợp đồng trở nên khó dùng và mất mục đích ban đầu.

Điều này cũng áp dụng với fake repository hoặc mock trong kiểm thử: trường hợp không tìm thấy cần được mô tả bằng `Optional.empty()`, không phải một giá trị null tùy ý.

### Không bọc lại một Optional đã có

Khi repository đã trả `Optional<Account>`, hãy dùng trực tiếp kết quả đó:

```java
Optional<Account> account =
        repository.findByTenantIdAndLoginName(tenantId, loginName);
```

Bọc nó bằng `Optional.ofNullable(...)` tạo ra `Optional<Optional<Account>>`. Container ngoài không bổ sung thông tin có ích nếu hợp đồng repository vốn đã bảo đảm trả một `Optional` khác null.

Nếu đang tích hợp một API cũ trả null, `ofNullable` có thể phù hợp tại ranh giới đó. Nó không phải cách che việc một API mới vi phạm chính hợp đồng trả `Optional` của mình.

## 4. Chọn phép toán theo điều bạn muốn làm

### 4.1. `map`: chuyển đổi giá trị khi có dữ liệu

Giả sử `Account` có các getter tương ứng:

```java
Optional<Long> accountId = repository
        .findByTenantIdAndLoginName(tenantId, loginName)
        .map(Account::getId);
```

Nếu tài khoản vắng mặt, mapper không chạy. Nếu có tài khoản, mapper tạo ra giá trị kế tiếp.

Một đặc điểm quan trọng của `map` là nếu mapper trả null, kết quả trở thành `Optional.empty()`. Điều này có thể hữu ích, nhưng cũng có thể làm mất sự phân biệt giữa không có tài khoản và tài khoản có một thuộc tính đang null.

```java
Optional<String> recoveryEmail = repository
        .findByTenantIdAndLoginName(tenantId, loginName)
        .map(Account::getRecoveryEmail);
```

Kết quả rỗng có thể đến từ hai tình huống:

1. Không tìm thấy tài khoản.
2. Tìm thấy tài khoản nhưng tài khoản không có email khôi phục.

Chỉ dùng hợp đồng này khi người gọi không cần phân biệt hai tình huống. Nếu cần phân biệt, hãy giữ đối tượng tài khoản hoặc trả một view/trạng thái có cấu trúc rõ ràng hơn.

### 4.2. `flatMap`: nối một phép tra cứu cũng trả Optional

Nếu hàm chuyển đổi đã trả `Optional`, dùng `flatMap` để tránh lồng container:

```java
Optional<String> recoveryEmail = repository
        .findByTenantIdAndLoginName(tenantId, loginName)
        .flatMap(account ->
                Optional.ofNullable(account.getRecoveryEmail()));
```

Ví dụ này vẫn gộp hai lý do vắng dữ liệu vừa nêu; `flatMap` chỉ xử lý hình dạng container, không tự bổ sung một mã lý do.

Quy tắc dễ nhớ:

```text
T -> U              dùng map
T -> Optional<U>    dùng flatMap
```

Hàm cung cấp cho `flatMap` phải trả một `Optional` hợp lệ, không trả null.

### 4.3. `filter`: chỉ giữ giá trị thỏa điều kiện

```java
Optional<Account> enabledAccount = repository
        .findByTenantIdAndLoginName(tenantId, loginName)
        .filter(Account::isEnabled);
```

Nếu tài khoản tồn tại nhưng bị vô hiệu hóa, kết quả cũng trở thành rỗng. Đây là một quyết định về thông tin mà API trả ra.

Nếu nghiệp vụ cần phân biệt “không tồn tại” với “bị vô hiệu hóa”, hãy lấy tài khoản trước rồi kiểm tra trạng thái ở bước riêng. Không dùng `filter` rồi kỳ vọng `Optional` giữ lại nguyên nhân bị loại.

Phép lọc trên `Optional` chạy ở Java sau lời gọi repository. Nó không tự thêm điều kiện `enabled = true` vào truy vấn datastore.

### 4.4. `ifPresent`: thực hiện xử lý khi có dữ liệu

```java
repository.findByTenantIdAndLoginName(tenantId, loginName)
        .ifPresent(this::recordAccountVisit);
```

Ví dụ phù hợp khi không có tài khoản thì không cần thực hiện hành vi đó. Nếu cả nhánh có và không có đều cần xử lý đáng kể, một cấu trúc điều khiển rõ ràng ở service có thể dễ đọc hơn chuỗi lambda dài.

`ifPresent` không tự mở transaction hoặc tự lưu thay đổi. Tác động của `recordAccountVisit` phải tuân theo hợp đồng riêng của ứng dụng.

## 5. Chọn hành vi khi vắng dữ liệu

### 5.1. `orElse`: dùng một giá trị dự phòng đã có hoặc rẻ

```java
String label = displayName.orElse("Tài khoản chưa đặt tên");
```

Ở đây `displayName` là `Optional<String>`. Một hằng chuỗi là fallback đơn giản và không có công việc đáng kể cần trì hoãn.

### 5.2. `orElseGet`: chỉ tạo fallback khi Optional rỗng

So sánh hai lời gọi độc lập:

```java
AccountView first = result.orElse(buildFallbackView());

AccountView second = result.orElseGet(this::buildFallbackView);
```

`result` là `Optional<AccountView>`; `buildFallbackView()` là hàm tạo một view dự phòng của ứng dụng.

- Với `orElse`, biểu thức đối số `buildFallbackView()` được đánh giá trước khi gọi phương thức, kể cả khi `result` đang có giá trị.
- Với `orElseGet`, supplier chỉ được gọi khi `result` rỗng.

Nếu fallback tốn công hoặc có tác dụng phụ, khác biệt này ảnh hưởng hành vi thực tế. Việc tạo một entity mới và ghi vào database cần một luồng nghiệp vụ rõ ràng, không nên bị ẩn trong một biểu thức fallback khó nhận ra.

Cả lựa chọn fallback lẫn supplier vẫn cần tuân theo hợp đồng đầu ra. Trả null ở cuối chuỗi xử lý sẽ đưa sự không rõ ràng trở lại API nếu người gọi đang kỳ vọng một view có giá trị.

### 5.3. `orElseThrow`: thao tác này bắt buộc có dữ liệu

```java
Account account = repository
        .findByTenantIdAndLoginName(tenantId, loginName)
        .orElseThrow(AccountNotFoundException::new);
```

Đây là cách chuyển một kết quả có thể vắng mặt ở repository thành yêu cầu bắt buộc ở tầng nghiệp vụ. Chọn loại ngoại lệ mô tả được tình huống thay vì chỉ dựa vào một lỗi mở container chung chung.

`orElseThrow` chỉ chạy khi nhận được `Optional.empty()`. Nếu repository đã ném lỗi nhiều kết quả hoặc lỗi hạ tầng, lời gọi không đi tới bước xử lý Optional này.

### 5.4. `get()` cần một bảo đảm đã được thiết lập

```java
Account account = result.get();
```

Khi rỗng, `get()` ném `NoSuchElementException`. Chỉ nhìn dòng mã trên, người đọc chưa biết điều kiện nào bảo đảm có giá trị.

Một kiểm tra `isPresent()` trước đó có thể thiết lập điều kiện cần thiết. Tuy vậy, với nhiều API ứng dụng, `map`, `ifPresent` hoặc `orElseThrow` thể hiện mục đích ngay tại chỗ dùng và giảm việc mở container thủ công.

## 6. Thiết kế API service: tìm kiếm và yêu cầu bắt buộc

Một repository method có thể được tái sử dụng cho hai thao tác service:

```text
findAccount(...)     → có thể không tồn tại, trả Optional<AccountView>
requireAccount(...)  → phải tồn tại cho thao tác này, trả AccountView hoặc lỗi
```

Ví dụ view dùng Java record trong dự án có mức ngôn ngữ phù hợp:

```java
record AccountView(Long id, String loginName, String displayName) {

    static AccountView from(Account account) {
        return new AccountView(
                account.getId(),
                account.getLoginName(),
                account.getDisplayName()
        );
    }
}
```

Service:

```java
import java.util.Optional;

public class AccountService {

    private final AccountRepository repository;

    public AccountService(AccountRepository repository) {
        this.repository = repository;
    }

    public Optional<AccountView> findAccount(
            String tenantId, String loginName) {

        requireText(tenantId, "tenantId");
        requireText(loginName, "loginName");

        return repository
                .findByTenantIdAndLoginName(tenantId, loginName)
                .map(AccountView::from);
    }

    public AccountView requireAccount(
            String tenantId, String loginName) {

        return findAccount(tenantId, loginName)
                .orElseThrow(AccountNotFoundException::new);
    }

    private static void requireText(String value, String parameter) {
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalArgumentException(
                    parameter + " phải có giá trị");
        }
    }
}

class AccountNotFoundException extends RuntimeException {

    AccountNotFoundException() {
        super("Không tìm thấy tài khoản phù hợp.");
    }
}
```

Những hợp đồng được thể hiện rõ trong ví dụ:

- Đầu vào null hoặc trắng là lỗi yêu cầu, không phải không tìm thấy.
- `findAccount` giữ sự vắng mặt như một kết quả hợp lệ.
- `requireAccount` yêu cầu có dữ liệu cho thao tác hiện tại.
- Repository trả entity; service ánh xạ sang view.
- `AccountView.from` luôn tạo view khác null khi được cung cấp một tài khoản hợp lệ.

Kiểm tra có văn bản không đồng nghĩa chuẩn hóa tên đăng nhập, kiểm tra quyền hoặc xác định tenant đáng tin cậy. Các quy tắc đó cần được ứng dụng thực hiện ở nơi thích hợp.

### Vì sao không để repository quyết định mọi lỗi nghiệp vụ?

Cùng một tài khoản chưa tồn tại có thể mang ý nghĩa khác nhau:

| Thao tác | Cách hiểu vắng dữ liệu |
| --- | --- |
| Kiểm tra tên đăng nhập đã được dùng chưa | Có thể là trạng thái bình thường |
| Xem trang hồ sơ của một tài khoản cụ thể | Có thể là không tìm thấy tài nguyên |
| Thực hiện một thao tác bắt buộc có tài khoản | Là lỗi nghiệp vụ cần báo rõ |

Repository biểu đạt việc đọc dữ liệu. Service hoặc tầng sử dụng quyết định ý nghĩa của việc vắng dữ liệu đối với một thao tác cụ thể.

## 7. Hợp đồng nội bộ và API bên ngoài cần được nối rõ ràng

Một phương thức Java trả `Optional<AccountView>` không tự quyết định mã HTTP hoặc hình dạng JSON.

Ví dụ các lựa chọn thiết kế API:

| Tình huống | Hình thức phản hồi có thể chọn |
| --- | --- |
| Có tài nguyên được yêu cầu | Trả biểu diễn tài nguyên thành công |
| Không có tài nguyên tại một endpoint chi tiết | Phản hồi không tìm thấy theo quy ước API |
| Truy vấn danh sách không có phần tử | Danh sách rỗng theo hợp đồng endpoint |
| Tính năng tùy chọn chưa được cấu hình | Một trạng thái thành công có biểu diễn vắng cấu hình rõ ràng |
| Đầu vào không hợp lệ | Phản hồi lỗi yêu cầu theo quy tắc validation |

Những lựa chọn này cần được quyết định ở hợp đồng API. Không nên dựa vào việc serializer tình cờ biến `Optional.empty()` thành một dạng JSON nào đó.

Nếu đưa `Optional` thẳng ra payload, hình dạng kết quả còn phụ thuộc công cụ serialization và cấu hình của dự án. Một DTO có schema được định nghĩa rõ giúp người sử dụng API không phải hiểu các lớp Java nội bộ.

Tương tự, không chuyển mọi ngoại lệ repository thành phản hồi không tìm thấy. Một lỗi nhiều kết quả cho khóa phải duy nhất hoặc lỗi kết nối cần một luồng xử lý khác với tài nguyên không tồn tại.

## 8. Có nên dùng Optional ở tham số và field?

`Optional` hữu ích ở kiểu trả về không có nghĩa cần thay mọi tham chiếu nullable bằng `Optional`.

| Vị trí | Cách cân nhắc |
| --- | --- |
| Kết quả tra cứu tối đa một phần tử | Thường là vị trí rõ ràng để dùng `Optional<T>` |
| Service có thể không tìm được một view | Có thể tiếp tục trả `Optional<View>` |
| Tham số repository | Cần hợp đồng được store hỗ trợ; không tự coi empty là bỏ bộ lọc |
| Field entity được lưu trữ | Cần xem mapping của store; không mặc định `Optional` là kiểu persistent phù hợp |
| Field DTO gửi ra ngoài | Định nghĩa schema và serialization rõ ràng trước khi chọn kiểu Java |
| Tập kết quả nhiều phần tử | Thường dùng collection rỗng để biểu đạt không có phần tử |

### 8.1. Optional làm tham số không tự tạo truy vấn động

Giả sử giao diện cho phép lọc theo email khôi phục. Ba ý định có thể là:

1. Không lọc theo email.
2. Chỉ lấy tài khoản chưa có email.
3. Lấy tài khoản có email bằng một giá trị cụ thể.

Một `Optional<String>` chỉ có hai trạng thái empty/present. Nếu dùng empty mà không xác định rõ ngữ nghĩa, bạn chưa biểu đạt đủ ba ý định này.

Thêm một tham số `Optional<String>` vào query method cũng không tự buộc Spring Data bỏ predicate khi empty. Module có thể có khả năng unwrap tham số riêng; hành vi vẫn cần đối chiếu với store và kiểu truy vấn.

Cách thiết kế rõ hơn là dùng một tiêu chí truy vấn có trạng thái tường minh, chọn phương thức phù hợp hoặc dùng API truy vấn động được store hỗ trợ. Những cập nhật kiểu PATCH cũng cần phân biệt không cung cấp field với yêu cầu xóa giá trị; `Optional.empty()` đơn lẻ không tự giải quyết sự phân biệt đó.

### 8.2. Field Optional không tự được lưu đúng

Một field `Optional<String> recoveryEmail` trong entity không mặc nhiên tương đương với một cột nullable hoặc một trường document tùy chọn được mapping đúng. Cần xác nhận kiểu được mapper của store hỗ trợ và có thể cần cơ chế chuyển đổi phù hợp.

Trong nhiều mô hình, entity giữ một giá trị nullable theo hợp đồng mapping và service cung cấp API tra cứu rõ ràng ra bên ngoài. Có thể thêm một accessor tính toán trả Optional nếu hữu ích, đồng thời bảo đảm accessor đó không bị hiểu nhầm thành thuộc tính persistent ngoài ý muốn theo cách mapping của store.

### 8.3. Collection rỗng đã biểu đạt không có phần tử

```java
List<Account> accounts =
        repository.findByTenantIdAndEnabledTrue(tenantId);
```

Theo hợp đồng collection thông dụng của Spring Data, không có kết quả được biểu diễn bằng collection rỗng. `Optional<List<Account>>` chỉ nên xuất hiện khi ứng dụng thật sự có thêm một trạng thái khác với danh sách rỗng và đã định nghĩa rõ trạng thái đó.

Không dùng container lồng nhau chỉ để tránh lựa chọn ý nghĩa của “không có dữ liệu”. Hợp đồng tốt cần ít trạng thái mơ hồ hơn, không chỉ nhiều lớp bao hơn.

## 9. Không để Optional làm mất thông tin cần thiết

Các thao tác sau đều có thể làm kết quả trở thành rỗng:

```text
Repository không tìm thấy tài khoản
map trả về null
flatMap trả về Optional.empty()
filter loại tài khoản theo điều kiện
```

Nếu người gọi cần phân biệt từng nguyên nhân, `Optional` không phải một mô hình đầy đủ cho kết quả nghiệp vụ đó. Có thể cần một trạng thái có tên, một kiểu kết quả chuyên biệt hoặc các bước kiểm tra tách rời.

Ví dụ, với thao tác cần phân biệt tài khoản thiếu và tài khoản bị vô hiệu hóa, có thể:

1. Tra cứu và yêu cầu tài khoản tồn tại.
2. Kiểm tra trạng thái enabled.
3. Tiếp tục xử lý hoặc báo lỗi trạng thái theo hợp đồng.

Việc dùng `filter(Account::isEnabled)` rồi xử lý mọi empty thành “không tìm thấy” chỉ phù hợp khi bạn chủ động muốn gộp các tình huống đó.

Ngược lại, không cần tạo một kiểu kết quả phức tạp nếu người gọi chỉ cần biết có giá trị hay không. `Optional` phù hợp với đúng hai trạng thái ấy.

## 10. Sự hiện diện không đồng nghĩa tính duy nhất hoặc tính mới nhất

### 10.1. Dữ liệu trùng là lỗi hợp đồng khác

`Optional<Account>` không tạo unique constraint. Nếu tên đăng nhập phải duy nhất trong tenant, cần ràng buộc ở store phù hợp với điều kiện và quy tắc chuẩn hóa.

Một bước tra cứu rỗng rồi `save` không tự ngăn hai yêu cầu đồng thời cùng tạo dữ liệu trùng. Cần cơ chế bảo vệ ghi và xử lý xung đột tương ứng.

Đừng bắt lỗi nhiều kết quả rồi đổi thành `Optional.empty()`: người gọi có thể hiểu nhầm rằng tên đăng nhập chưa được dùng và tạo thêm dữ liệu không hợp lệ.

### 10.2. Chọn một từ nhiều ứng viên cần quy tắc riêng

Nếu nghiệp vụ muốn “tài khoản mới nhất”, cần giới hạn cùng thứ tự thích hợp mà store hỗ trợ. Trả `Optional` đơn thuần không tự chọn bản ghi đầu tiên hoặc mới nhất.

Ngược lại, thêm `First`/`Top` chỉ để làm biến mất lỗi nhiều kết quả có thể che dữ liệu trùng theo một khóa vốn phải duy nhất. Cần phân biệt rõ chọn một ứng viên hợp lệ với yêu cầu mọi dữ liệu phải duy nhất.

### 10.3. Optional không giữ tài nguyên truy vấn cho bạn

Một `Optional<Account>` có giá trị không tự bảo đảm mọi quan hệ lazy trên entity có thể được đọc ở bất kỳ thời điểm nào. Vòng đời transaction và persistence context vẫn do công nghệ truy cập dữ liệu quyết định.

Nếu service cần ánh xạ sang view, hãy thực hiện việc đọc các dữ liệu cần thiết trong phạm vi tài nguyên phù hợp. `Optional.map` là một thao tác Java; nó không mở thêm transaction tự động.

## 11. Các lỗi thiết kế thường gặp

| Cách dùng | Hệ quả | Hướng điều chỉnh |
| --- | --- | --- |
| Trả null từ phương thức khai báo Optional | Người gọi phải kiểm tra thêm container null | Trả `Optional.empty()` hoặc một Optional có giá trị |
| Gọi `get()` không có bảo đảm | Lỗi mở Optional rỗng khó gắn với nghiệp vụ | Dùng phép xử lý vắng dữ liệu có ý nghĩa |
| Dùng `orElse` với hàm fallback có tác dụng phụ | Hàm có thể chạy ngay cả khi có giá trị | Xem xét `orElseGet` và giữ luồng ghi rõ ràng |
| Dùng `map` trên thuộc tính nullable rồi coi empty luôn là thiếu entity | Mất phân biệt hai tình huống | Giữ entity/view hoặc mô hình trạng thái phù hợp |
| Dùng `filter` nhưng vẫn muốn biết lý do bị loại | Thông tin nguyên nhân không còn trong Optional | Kiểm tra riêng hoặc trả kết quả nghiệp vụ có cấu trúc |
| Dùng Optional tham số để mặc định bỏ bộ lọc | Ngữ nghĩa query không rõ hoặc không đúng | Định nghĩa tiêu chí và hỗ trợ theo store |
| Bắt mọi lỗi rồi trả empty | Lỗi hạ tầng và dữ liệu bị che | Phân biệt vắng dữ liệu với truy vấn thất bại |
| Trả Optional thẳng ra payload mà chưa định nghĩa schema | API phụ thuộc cấu hình serialization | Ánh xạ phản hồi theo hợp đồng bên ngoài |
| Dùng Optional để kỳ vọng dữ liệu tự duy nhất | Vẫn có thể trùng hoặc lỗi nhiều kết quả | Bảo vệ khóa ở kho dữ liệu |

## 12. Các tình huống nên xác minh

Một hợp đồng Optional có thể được xác minh bằng các ca có khả năng phân biệt hành vi:

- Không có tài khoản: repository trả empty, service tùy thao tác giữ empty hoặc ném lỗi nghiệp vụ.
- Có một tài khoản: mapper được gọi và tạo view đúng.
- Tài khoản có thuộc tính nullable: kiểm tra API có chủ động gộp hay phân biệt trạng thái này với thiếu tài khoản.
- Tài khoản bị vô hiệu hóa: kiểm tra ý nghĩa của filter hoặc bước kiểm tra riêng.
- Đầu vào null và trắng: bị xử lý theo hợp đồng validation, không bị coi là không tìm thấy.
- Có nhiều kết quả: không bị chuyển âm thầm thành empty.
- Fallback: chỉ được thực hiện tại thời điểm mà API hứa sẽ thực hiện.
- Tập kết quả không có phần tử: trả collection rỗng khi dùng query method nhiều kết quả.

Khi dùng mock hoặc implementation tùy biến, cần giữ đúng hợp đồng non-null của container. Khi kiểm tra với store thực, còn cần mapping, ràng buộc duy nhất, điều kiện tenant và quy tắc chuẩn hóa phù hợp.

## 13. Bài tập tự kiểm tra

### Bài 1: Container null

Một phương thức khai báo `Optional<Account>` nhưng trả null khi không có tài khoản. Có thể coi đó là một cách biểu diễn empty tương đương không?

**Gợi ý đáp án:** Không. Người gọi kỳ vọng một Optional hợp lệ để tiếp tục dùng `map` hoặc `orElseThrow`. Phải trả `Optional.empty()` cho trạng thái không có kết quả.

### Bài 2: Fallback có chạy không?

```java
AccountView view = result.orElse(buildFallbackView());
```

Nếu `result` có giá trị, `buildFallbackView()` có được gọi không?

**Gợi ý đáp án:** Có. Biểu thức đối số được đánh giá trước lời gọi `orElse`. Dùng `orElseGet` khi muốn trì hoãn việc tạo fallback đến lúc Optional rỗng.

### Bài 3: Hai nguyên nhân empty

Sau `repository.findBy...().map(Account::getRecoveryEmail)`, kết quả rỗng có luôn chứng minh rằng tài khoản không tồn tại không?

**Gợi ý đáp án:** Không. Tài khoản có thể tồn tại nhưng getter trả null. Nếu người gọi cần phân biệt, phải giữ thông tin ở một hình dạng kết quả phù hợp hơn.

### Bài 4: Optional ở đầu vào

Một bộ lọc cần phân biệt không lọc email, tìm email null và tìm email bằng một giá trị. Chỉ một `Optional<String>` với empty/present có tự biểu đạt đủ ba trạng thái không?

**Gợi ý đáp án:** Không. Cần tiêu chí có trạng thái rõ hoặc cách chọn truy vấn tương ứng. Optional không tự quy định việc bỏ predicate trong repository.

### Bài 5: Service và API

Repository trả empty cho tên đăng nhập chưa tồn tại. Có bắt buộc mọi nơi gọi đều ném cùng một lỗi không?

**Gợi ý đáp án:** Không. Một thao tác kiểm tra có thể coi đó là bình thường; thao tác yêu cầu tài khoản có thể chuyển thành lỗi nghiệp vụ. API bên ngoài ánh xạ kết quả theo hợp đồng của endpoint.

### Bài 6: Truy vấn thất bại

Một lỗi kết nối xảy ra trong repository method trả Optional. Có nên chuyển thành empty để người gọi đơn giản hơn không?

**Gợi ý đáp án:** Không. Empty có nghĩa không có kết quả sau một truy vấn hợp lệ, còn lỗi kết nối là thất bại của việc truy vấn. Gộp chúng làm người gọi đưa ra quyết định nghiệp vụ sai.

## Những điểm cần nhớ

- `Optional<T>` là hợp đồng về sự hiện diện của kết quả đơn; container được trả về phải khác null.
- Xử lý vắng dữ liệu bằng phép toán thể hiện rõ ý định, đồng thời hiểu khả năng gộp trạng thái của `map`, `flatMap` và `filter`.
- `orElse` nhận giá trị đã được tính; `orElseGet` trì hoãn supplier; `orElseThrow` chuyển empty thành một yêu cầu bắt buộc.
- Repository, service và API bên ngoài có trách nhiệm riêng đối với việc không có dữ liệu.
- Optional không tự validation đầu vào, không tạo query động, không bảo vệ tính duy nhất và không thay thế hợp đồng mapping của store.
