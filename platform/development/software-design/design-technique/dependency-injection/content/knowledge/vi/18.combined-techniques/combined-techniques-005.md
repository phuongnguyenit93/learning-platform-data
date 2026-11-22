# DI với Composite để xây dựng cấu trúc đối tượng kết hợp

**Dependency Injection (DI)** giúp một đối tượng nhận các cộng tác viên (*collaborator*) từ bên ngoài thay vì tự chọn hoặc tự tạo chúng. **Composite** là mẫu thiết kế cấu trúc (*structural design pattern*) cho phép một đối tượng đại diện cho **một nhóm đối tượng cùng tuân thủ một hợp đồng**, để bên sử dụng thao tác với phần tử đơn lẻ và phần tử tổ hợp theo cùng một cách.

Khi kết hợp hai kỹ thuật, ta có thể tạo một **đồ thị đối tượng nhiều tầng** bằng Java thuần: các đối tượng lá (*leaf*) triển khai interface, các composite cũng triển khai interface đó và nhận danh sách phần tử con bằng **constructor injection**. **Composition root** sẽ chọn các lá, tổ chức chúng thành những nhóm có ý nghĩa, và truyền composite gốc cho service nghiệp vụ. Khi mở rộng sang DI container, container có thể hỗ trợ lắp ghép đồ thị này, nhưng các quy tắc nghiệp vụ và trách nhiệm của Composite vẫn phải được thiết kế rõ ràng.

Bài thuộc chương **Kỹ thuật kết hợp** của module Dependency Injection / Inversion of Control (IoC). Mục tiêu không chỉ là biết dùng `new AllOfRule(...)`, mà còn hiểu **hợp đồng chung, thứ tự thực hiện, chính sách lỗi, scope, vòng đời và khả năng kiểm thử** khi một dependency được tạo từ nhiều dependency khác.

Sau bài này, bạn có thể:

- Phân biệt vai trò của **DI** và **Composite**; thấy vì sao chúng bổ trợ nhau mà không thay thế nhau.
- Nhận diện **component interface**, **leaf**, **composite** và **client** trên một object graph.
- Lắp một cây xử lý lồng nhau bằng constructor injection, không để service nghiệp vụ tự tạo các phần tử con.
- Thiết kế ngữ nghĩa **AND / OR**, thứ tự thực thi và cách tổng hợp kết quả thất bại.
- Viết chương trình Java 17 thuần và bài kiểm thử fake cho cả phần tử lá lẫn composite.
- Kiểm soát tham chiếu dùng chung, cấu trúc bất biến, chu trình, scope và quyền sở hữu tài nguyên.
- Chọn lúc nào phù hợp dùng Composite thay vì decorator, pipeline hoặc một service đơn giản.

## 1. Vấn đề: một dependency thực tế được hình thành từ nhiều chính sách

Giả sử ứng dụng muốn xét điều kiện sử dụng một ưu đãi. Một yêu cầu phải thỏa:

1. Khách hàng đã được xác minh.
2. Đồng thời, khách hàng **hoặc** thuộc nhánh thông thường (đơn không vượt giới hạn **và** ở quốc gia được hỗ trợ), **hoặc** có quyền VIP.

Có thể viết tất cả trong một phương thức dài:

~~~java
// Minh họa lối viết dồn mọi chính sách vào một lớp.
boolean eligible(OfferRequest request) {
    return request.verified()
            && ((request.amountCents() <= 1_000_000
                    && "VN".equals(request.countryCode()))
                || request.vip());
}
~~~

Biểu thức ngắn ở ví dụ này vẫn dễ hiểu. Nhưng khi từng điều kiện có cấu hình, cách giải thích lý do từ chối, nhiều phương án hợp lệ và cần kiểm thử riêng, một lớp chứa toàn bộ quy tắc có thể khó mở rộng:

- Thêm một chính sách riêng có thể buộc sửa lớp điều phối chính.
- Khó tái sử dụng một điều kiện trong nhiều tổ hợp khác nhau.
- Nếu chỉ trả `boolean`, người dùng không biết bị từ chối vì sao.
- Test từng nhánh logic phải đi qua mọi điều kiện, nhất là khi chúng có phụ thuộc hạ tầng.
- Mã nghiệp vụ có xu hướng biết tên và cách tạo các rule cụ thể.

**Composite** giúp biểu diễn **biểu thức logic bằng cấu trúc đối tượng**. **DI** giúp cung cấp các đối tượng thành phần từ bên ngoài một cách tường minh.

## 2. Bốn vai trò trong Composite

Đối với bài toán xét điều kiện ưu đãi:

| Vai trò | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Component** | Hợp đồng chung cho phần tử đơn lẻ và tổ hợp | `OfferRule.check(OfferRequest)` |
| **Leaf** | Thực hiện một quy tắc cụ thể, không giữ danh sách rule con | `VerifiedCustomerRule`, `AmountAtMostRule`, `CountryRule`, `VipCustomerRule` |
| **Composite** | Giữ nhiều `OfferRule` con và tổng hợp kết quả theo một phép toán | `AllOfRule`, `AnyOfRule` |
| **Client** | Chỉ biết hợp đồng chung và sử dụng composite gốc | `OfferService` |

Một cây có thể trông như sau:

~~~mermaid
flowchart TD
    Client["OfferService"] --> Root["AllOfRule: tất cả đúng"]
    Root --> Verified["VerifiedCustomerRule (leaf)"]
    Root --> Or["AnyOfRule: ít nhất một nhánh đúng"]
    Or --> Standard["AllOfRule: nhánh thông thường"]
    Standard --> Amount["AmountAtMostRule (leaf)"]
    Standard --> Country["CountryRule (leaf)"]
    Or --> Vip["VipCustomerRule (leaf)"]
~~~

Đọc cấu trúc từ dưới lên:

- `AmountAtMostRule` và `CountryRule` cùng thuộc nhánh thông thường.
- `AnyOfRule` chấp nhận **một trong hai**: nhánh thông thường hoặc nhánh VIP.
- Composite gốc yêu cầu **đã xác minh** và **đạt một nhánh đủ điều kiện**.
- `OfferService` không biết cây có bao nhiêu tầng; nó chỉ gọi `check(request)` trên `OfferRule` đã được inject.

### DI và Composite làm hai việc khác nhau

**Composite** trả lời: “Làm sao biểu diễn phần tử đơn lẻ và nhóm phần tử bằng một interface, với quy tắc tổng hợp có ý nghĩa?”

**DI** trả lời: “Ai chọn, tạo và truyền những phần tử đó vào đối tượng sử dụng?”

**IoC** ở đây thể hiện ở việc `OfferService` không quyết định dựng cây thế nào. **Dependency Inversion Principle (DIP)** thể hiện ở việc `OfferService` phụ thuộc vào abstraction `OfferRule`; những leaf và composite cụ thể cũng thực hiện cùng hợp đồng.

Bạn có thể triển khai Composite mà không áp dụng DI, ví dụ một composite tự `new` các leaf cố định bên trong. Nhưng cách đó khiến cấu trúc khó thay đổi và kiểm thử riêng. Constructor injection giúp cây lắp ghép được tại composition root, tách quyết định **dùng thành phần nào** khỏi **cách một thành phần thực thi hợp đồng**.

## 3. Thiết kế hợp đồng chung trước khi lắp ghép

Một Composite dùng chung interface không chỉ vì “cùng có phương thức”. **Hành vi** cũng phải có ý nghĩa nhất quán để client sử dụng lá và nhóm mà không cần kiểm tra loại runtime.

Với chính sách xét ưu đãi, `OfferRule.check`:

- Nhận một `OfferRequest` hợp lệ.
- Trả một `Decision` cho biết **được phép** hay **bị từ chối**.
- Nếu từ chối, chứa ít nhất một **lý do** để kiểm tra và giải thích.
- Không thay đổi yêu cầu đầu vào hoặc gọi hạ tầng gây side effect trong ví dụ.
- Không tự chọn các rule khác hoặc tự truy cập container.

Ta chọn kết quả có cấu trúc thay vì `boolean`:

~~~java
record Decision(boolean allowed, List<String> reasons) {
    Decision {
        reasons = List.copyOf(reasons);
        if (allowed && !reasons.isEmpty()) {
            throw new IllegalArgumentException(
                    "Allowed decision must not carry failures");
        }
        if (!allowed && reasons.isEmpty()) {
            throw new IllegalArgumentException(
                    "Denied decision must explain why");
        }
    }

    static Decision allow() {
        return new Decision(true, List.of());
    }

    static Decision deny(String reason) {
        return new Decision(false, List.of(reason));
    }
}
~~~

Lợi ích:

1. Bên sử dụng chỉ cần gọi `Decision decision = rule.check(request)`, bất kể rule là leaf hay composite.
2. Composite có thể tổng hợp các lý do từ nhiều rule con.
3. Test có thể kiểm tra cả kết quả và lý do, thay vì suy đoán một nhánh được chọn.
4. Bất biến của `Decision` được kiểm tra ở constructor; danh sách lý do được sao chép bằng `List.copyOf`.

Tất nhiên, **Composite không bắt buộc dùng kết quả này**. Với xử lý tệp, component có thể là `Exporter.export`; với giao diện, là `Widget.render`. Điều quan trọng là **hợp đồng của lá và composite phù hợp với mục đích của client**, không phải mọi leaf/composite đều phải trả `boolean`.

## 4. Constructor injection cho composite

Một composite cần những phần tử con để hoạt động. Thay vì tự tạo chúng, ta đưa chúng vào constructor:

~~~java
final class AllOfRule implements OfferRule {
    private final List<OfferRule> children;

    AllOfRule(List<? extends OfferRule> children) {
        if (children == null || children.isEmpty()) {
            throw new IllegalArgumentException(
                    "AllOfRule needs at least one child");
        }
        this.children = List.copyOf(children);
    }

    // check(...) tổng hợp kết quả từ các child.
}
~~~

Các quyết định đáng chú ý:

- **Constructor nhận interface `OfferRule`**, không nhận một loại leaf cụ thể. Một phần tử con có thể lại là một composite.
- **Danh sách không rỗng** là lựa chọn hợp đồng của bài. Về logic, AND của tập rỗng đôi khi được định nghĩa là `true`, nhưng việc từ chối giúp phát hiện thiếu cấu hình sớm.
- **`List.copyOf` tạo bản sao cấu trúc danh sách** và từ chối phần tử `null`. Tuy nhiên, nó không sao chép sâu các object con; nếu child mutable thì child vẫn có thể thay đổi.
- **Thứ tự do composition root cung cấp** được giữ lại. Với các chính sách báo lỗi và short-circuit, thứ tự có thể quan sát được.
- Không expose setter thêm/xóa child khi các rule bắt buộc cần một cây ổn định sau khởi tạo.

Constructor injection khiến object graph rõ ràng: một `AllOfRule` không thể hoàn thành việc tạo nếu danh sách con bị thiếu theo hợp đồng. Ngược lại, cách truyền danh sách bằng setter sau khi tạo có thể tạo trạng thái trung gian mà rule tồn tại nhưng chưa hoạt động.

### Tại sao không để composite tự `new` leaf?

~~~java
// Tránh ghép chặt cấu trúc với implementation trong Composite.
final class HardCodedOfferRule implements OfferRule {
    private final OfferRule nested = new AllOfRule(List.of(
            new VerifiedCustomerRule(),
            new VipCustomerRule()));
}
~~~

`HardCodedOfferRule` vừa giữ trách nhiệm tổng hợp **vừa quyết định chính sách cố định và cách tạo leaf**. Nếu bộ quy tắc thay đổi theo môi trường, tenant hoặc sản phẩm, phải sửa lớp này. Đưa việc `new` đến composition root giúp tái sử dụng `AllOfRule` cho nhiều cấu trúc khác nhau và cấp fake trong unit test.

## 5. Ngữ nghĩa tổng hợp phải được tuyên bố rõ

Hai composite phổ biến thể hiện **AND** và **OR**, nhưng còn nhiều chi tiết cần định nghĩa.

| Composite | Khi nào cho phép? | Khi nào từ chối? | Chính sách đánh giá của bài |
| --- | --- | --- | --- |
| **`AllOfRule` (AND)** | Tất cả child cho phép | Ít nhất một child từ chối | Đánh giá tất cả để thu thập đủ lý do |
| **`AnyOfRule` (OR)** | Có ít nhất một child cho phép | Tất cả child đều từ chối | Dừng ngay ở child đầu tiên cho phép; nếu không có, gộp lý do |
| **`NotRule` (NOT), nếu cần** | Child từ chối | Child cho phép | Phải thiết kế lại lời giải thích, không đảo `allowed` rồi giữ nguyên reasons |
| **`FirstMatchingRule`, nếu cần** | Theo nhánh đầu tiên phù hợp | Tùy hợp đồng | Phải quy định ưu tiên và phân biệt không khớp với lỗi |

Với `AllOfRule`, ta **cố ý không short-circuit khi gặp lỗi đầu tiên** để báo đủ điều kiện chưa đạt. Với `AnyOfRule`, ta **cố ý short-circuit khi đã có một nhánh hợp lệ** để tránh đánh giá những nhánh không cần thiết.

Hai lựa chọn này có thể thay đổi theo yêu cầu sản phẩm. Ví dụ, nếu một rule gọi dịch vụ có chi phí, đánh giá tất cả có thể quá tốn kém; nếu lý do thất bại là thông tin nhạy cảm, không nên trả hết cho người dùng. Chính sách đánh giá phải là một phần của contract, không để container tự quyết định.

**Không dùng Composite để che vấn đề giao dịch.** Nếu child gây tác dụng phụ như thanh toán hoặc gửi email, “đánh giá tất cả” hay “dừng ở child đầu tiên” có thể làm một số tác dụng xảy ra trước khi child khác thất bại. Khi đó cần một hợp đồng xử lý khác hoặc cơ chế điều phối/transaction phù hợp; DI không tự cung cấp atomicity.

## 6. Ví dụ Java 17 hoàn chỉnh: một cây chính sách được inject

Ví dụ sau sử dụng **Java 17 trở lên**, không cần DI container hay thư viện ngoài. Mọi leaf và composite triển khai `OfferRule`; `Main` là composition root xây cây bằng constructor injection. Các rule chỉ kiểm tra dữ liệu trong memory, không có network hoặc database.

Lưu toàn bộ đoạn sau vào `Main.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record OfferRequest(
        String orderId,
        long amountCents,
        String countryCode,
        boolean verified,
        boolean vip) {
    OfferRequest {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("Invalid order id");
        }
        if (amountCents <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        if (countryCode == null || countryCode.isBlank()) {
            throw new IllegalArgumentException("Invalid country");
        }
    }
}

record Decision(boolean allowed, List<String> reasons) {
    Decision {
        reasons = List.copyOf(Objects.requireNonNull(reasons, "reasons"));
        if (allowed && !reasons.isEmpty()) {
            throw new IllegalArgumentException(
                    "Allowed decision cannot contain failures");
        }
        if (!allowed && reasons.isEmpty()) {
            throw new IllegalArgumentException(
                    "Denied decision needs a reason");
        }
    }

    static Decision allow() {
        return new Decision(true, List.of());
    }

    static Decision deny(String reason) {
        if (reason == null || reason.isBlank()) {
            throw new IllegalArgumentException("Invalid reason");
        }
        return new Decision(false, List.of(reason));
    }
}

// Component: cùng một interface cho lá và composite.
@FunctionalInterface
interface OfferRule {
    Decision check(OfferRequest request);
}

// Các leaf tập trung đúng một điều kiện.
final class VerifiedCustomerRule implements OfferRule {
    @Override
    public Decision check(OfferRequest request) {
        Objects.requireNonNull(request, "request");
        return request.verified()
                ? Decision.allow()
                : Decision.deny("Khach hang chua xac minh");
    }
}

final class AmountAtMostRule implements OfferRule {
    private final long maximum;

    AmountAtMostRule(long maximum) {
        if (maximum <= 0) {
            throw new IllegalArgumentException("Invalid maximum");
        }
        this.maximum = maximum;
    }

    @Override
    public Decision check(OfferRequest request) {
        Objects.requireNonNull(request, "request");
        return request.amountCents() <= maximum
                ? Decision.allow()
                : Decision.deny("Don vuot gioi han");
    }
}

final class CountryRule implements OfferRule {
    private final String supported;

    CountryRule(String supported) {
        if (supported == null || supported.isBlank()) {
            throw new IllegalArgumentException("Invalid country");
        }
        this.supported = supported;
    }

    @Override
    public Decision check(OfferRequest request) {
        Objects.requireNonNull(request, "request");
        return supported.equals(request.countryCode())
                ? Decision.allow()
                : Decision.deny("Quoc gia khong ho tro");
    }
}

final class VipCustomerRule implements OfferRule {
    @Override
    public Decision check(OfferRequest request) {
        Objects.requireNonNull(request, "request");
        return request.vip()
                ? Decision.allow()
                : Decision.deny("Khong co quyen VIP");
    }
}

// Composite AND: chạy tất cả child để gom đủ lý do từ chối.
final class AllOfRule implements OfferRule {
    private final List<OfferRule> children;

    AllOfRule(List<? extends OfferRule> children) {
        if (children == null || children.isEmpty()) {
            throw new IllegalArgumentException("AllOf needs children");
        }
        this.children = List.copyOf(children);
    }

    @Override
    public Decision check(OfferRequest request) {
        Objects.requireNonNull(request, "request");
        List<String> failures = new ArrayList<>();

        for (OfferRule child : children) {
            Decision result = Objects.requireNonNull(
                    child.check(request), "Child returned null");
            if (!result.allowed()) {
                failures.addAll(result.reasons());
            }
        }

        return failures.isEmpty()
                ? Decision.allow()
                : new Decision(false, failures);
    }
}

// Composite OR: dừng khi một nhánh đạt; nếu không, gom lỗi.
final class AnyOfRule implements OfferRule {
    private final List<OfferRule> children;

    AnyOfRule(List<? extends OfferRule> children) {
        if (children == null || children.isEmpty()) {
            throw new IllegalArgumentException("AnyOf needs children");
        }
        this.children = List.copyOf(children);
    }

    @Override
    public Decision check(OfferRequest request) {
        Objects.requireNonNull(request, "request");
        List<String> failures = new ArrayList<>();

        for (OfferRule child : children) {
            Decision result = Objects.requireNonNull(
                    child.check(request), "Child returned null");
            if (result.allowed()) {
                return Decision.allow(); // short-circuit
            }
            failures.addAll(result.reasons());
        }

        return new Decision(false, failures);
    }
}

// Client: không biết cây có mấy tầng hoặc có những leaf nào.
final class OfferService {
    private final OfferRule policy;

    OfferService(OfferRule policy) {
        this.policy = Objects.requireNonNull(policy, "policy");
    }

    Decision assess(OfferRequest request) {
        return policy.check(Objects.requireNonNull(request, "request"));
    }
}

// Composition root: lựa chọn rule và cấu trúc của toàn object graph.
public class Main {
    static OfferRule buildPolicy() {
        OfferRule verified = new VerifiedCustomerRule();

        OfferRule regularPath = new AllOfRule(List.of(
                new AmountAtMostRule(1_000_000),
                new CountryRule("VN")));

        OfferRule vipPath = new VipCustomerRule();
        OfferRule atLeastOnePath =
                new AnyOfRule(List.of(regularPath, vipPath));

        return new AllOfRule(List.of(verified, atLeastOnePath));
    }

    public static void main(String[] args) {
        OfferService service = new OfferService(buildPolicy());

        OfferRequest regular = new OfferRequest(
                "O-01", 500_000, "VN", true, false);
        OfferRequest vip = new OfferRequest(
                "O-02", 1_500_000, "SG", true, true);
        OfferRequest rejected = new OfferRequest(
                "O-03", 1_500_000, "SG", true, false);

        System.out.println(
                "Regular: " + service.assess(regular).allowed());
        System.out.println(
                "VIP: " + service.assess(vip).allowed());

        Decision denied = service.assess(rejected);
        System.out.println("Rejected: " + denied.allowed());
        System.out.println("Reasons: " + denied.reasons());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac Main.java
java Main
~~~

Kết quả dự kiến:

~~~text
Regular: true
VIP: true
Rejected: false
Reasons: [Don vuot gioi han, Quoc gia khong ho tro, Khong co quyen VIP]
~~~

### Lần theo object graph

**Trường hợp đơn thông thường:** `VerifiedCustomerRule` trả hợp lệ; nhánh `regularPath` gồm `AmountAtMostRule` và `CountryRule` đều hợp lệ; `AnyOfRule` trả `allow()` và **không cần gọi nhánh VIP**.

**Trường hợp VIP:** khách hàng đã xác minh; nhánh thông thường bị từ chối do số tiền và quốc gia, nhưng `VipCustomerRule` trả hợp lệ. `AnyOfRule` thành công; kết quả cho phép không mang các lý do thất bại của nhánh thông thường, vì điều kiện OR đã được đáp ứng.

**Trường hợp từ chối:** khách hàng được xác minh; cả nhánh thông thường và nhánh VIP đều thất bại. `AnyOfRule` trả danh sách lý do từ cả hai; `AllOfRule` gốc nhận kết quả đó và trả lại cho client.

Nhìn vào `OfferService`, không có phép `new` nào tạo leaf hoặc composite. **Chỉ composition root biết cấu trúc cụ thể của cây**. Điều này cho phép thay cây theo chính sách triển khai mà không sửa logic `assess`, miễn là các implementation giữ đúng hợp đồng `OfferRule`.

### Vì sao `Decision` sao chép danh sách?

`List.copyOf` làm danh sách lý do trong một kết quả không thể bị người gọi thêm/xóa phần tử. Tương tự, constructor của composite sao chép **danh sách child**, để code bên ngoài không thay đổi thứ tự hoặc số lượng child sau khi tạo composite.

Tuy nhiên, **bất biến cấu trúc không đồng nghĩa bất biến sâu**. Nếu một child giữ state mutable, composite vẫn giữ tham chiếu tới cùng child đó. Bài thực hành dùng các leaf gần như không trạng thái (chỉ giữ cấu hình bất biến) nên có thể tái sử dụng an toàn trong luồng tuần tự. Khi rule phụ thuộc database hoặc cache, cần kiểm tra thread-safety và scope riêng.

## 7. Kiểm thử Composite: tập trung vào hợp đồng và thứ tự đánh giá

Có hai nhóm kiểm thử khác nhau:

- **Kiểm thử leaf:** một rule cụ thể xử lý đúng dữ liệu của chính nó.
- **Kiểm thử composite:** tổng hợp đúng kết quả; bảo toàn thứ tự; `AllOfRule` đánh giá toàn bộ child còn `AnyOfRule` dừng khi gặp child cho phép; cấu trúc child không bị thay đổi từ ngoài.

Có thể dùng fake `OfferRule` bằng lambda, không cần container hay adapter thật.

Lưu đoạn sau vào `CompositeRuleTest.java` bên cạnh `Main.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CompositeRuleTest {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void expectInvalid(Runnable operation) {
        boolean rejected = false;
        try {
            operation.run();
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        check(rejected, "Invalid composition must be rejected");
    }

    public static void main(String[] args) {
        OfferRequest request = new OfferRequest(
                "TEST-01", 200_000, "VN", true, false);

        List<String> calls = new ArrayList<>();

        OfferRule firstFail = r -> {
            calls.add("first");
            return Decision.deny("FIRST");
        };
        OfferRule secondFail = r -> {
            calls.add("second");
            return Decision.deny("SECOND");
        };

        // AND chạy tất cả child và giữ thứ tự lý do.
        Decision andResult =
                new AllOfRule(List.of(firstFail, secondFail))
                        .check(request);
        check(!andResult.allowed(), "AND must deny");
        check(andResult.reasons().equals(List.of("FIRST", "SECOND")),
                "AND must aggregate failures in child order");
        check(calls.equals(List.of("first", "second")),
                "AND must evaluate every child");

        calls.clear();
        OfferRule success = r -> {
            calls.add("success");
            return Decision.allow();
        };
        OfferRule shouldNotRun = r -> {
            throw new AssertionError("OR must short-circuit");
        };

        // OR dừng ngay khi tìm được một nhánh hợp lệ.
        Decision orResult = new AnyOfRule(List.of(
                firstFail, success, shouldNotRun)).check(request);
        check(orResult.allowed(), "OR must allow");
        check(calls.equals(List.of("first", "success")),
                "OR must not evaluate later children");

        // Object graph được lắp tại composition root hoạt động đúng.
        OfferService service = new OfferService(Main.buildPolicy());
        check(service.assess(new OfferRequest(
                        "A", 500_000, "VN", true, false)).allowed(),
                "Regular path must pass");
        check(service.assess(new OfferRequest(
                        "B", 1_500_000, "SG", true, true)).allowed(),
                "VIP path must pass");
        check(!service.assess(new OfferRequest(
                        "C", 1_500_000, "SG", false, true)).allowed(),
                "Verification is always required");

        // Thay đổi list gốc không được thay đổi composite.
        List<OfferRule> supplied = new ArrayList<>();
        supplied.add(r -> Decision.allow());
        AllOfRule stable = new AllOfRule(supplied);
        supplied.add(r -> Decision.deny("ADDED LATER"));
        check(stable.check(request).allowed(),
                "Composite must snapshot its child list");

        // Tránh cấu trúc vô tình thiếu child.
        expectInvalid(() -> new AllOfRule(List.of()));
        expectInvalid(() -> new AnyOfRule(List.of()));

        System.out.println("PASS");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac Main.java CompositeRuleTest.java
java CompositeRuleTest
~~~

Kết quả dự kiến: `PASS`.

**Cần tách phạm vi xác minh:** bài test trên chứng minh hợp đồng đánh giá của những class viết bằng Java thuần; nó không kiểm tra transaction, network, resource scope hay cấu hình container. Nếu từng leaf sau này sử dụng HTTP/DB, cần contract test hoặc integration test riêng cho adapter tương ứng.

## 8. Từ cây sang đồ thị: chia sẻ child có chủ đích

Trong ví dụ, các rule được lắp thành **cây**: mỗi nhánh sở hữu tham chiếu đến một nhóm con. Nhưng khi dùng DI, nhiều composite có thể cùng nhận **một instance leaf**, tạo một **đồ thị có hướng không vòng (DAG)** thay vì một cây thuần túy:

~~~java
OfferRule verification = new VerifiedCustomerRule();

OfferRule policyA = new AllOfRule(List.of(
        verification, new CountryRule("VN")));

OfferRule policyB = new AllOfRule(List.of(
        verification, new VipCustomerRule()));
~~~

Hai composite chứa **cùng tham chiếu** `verification`. Điều đó hợp lý nếu leaf không giữ trạng thái theo request hoặc được thiết kế thread-safe. Với leaf mutable hoặc chứa state của một giao dịch, việc tái sử dụng có thể khiến hai nhánh ảnh hưởng nhau.

**Không nhầm identity với số lần gọi:** cùng một instance xuất hiện ở hai nhánh **không** có nghĩa nó chỉ được đánh giá một lần. Nếu một composite gốc đi qua cả hai nhánh, cùng leaf có thể được gọi hai lần trong một lượt đánh giá. Nếu cần tính toán một lần và cache theo yêu cầu, phải đưa quy tắc cache vào hợp đồng hoặc chọn cấu trúc khác; không tự suy từ việc chia sẻ object.

| Cấu trúc | Đặc tính | Lưu ý |
| --- | --- | --- |
| **Cây (tree)** | Mỗi child nằm trong một nhánh của cấu trúc | Dễ quan sát trách nhiệm và thứ tự |
| **DAG** | Một leaf/composite có thể được tái sử dụng tại nhiều nhánh, không có chu trình | Cần xét state, identity, số lần thực thi |
| **Đồ thị có vòng** | Một composite gián tiếp chứa lại chính nó | Có thể gây đệ quy vô hạn và `StackOverflowError` |
| **Đồ thị thay đổi sau khởi tạo** | Child có thể bị thêm/xóa khi xử lý | Cần chính sách đồng thời, consistency và versioning |

Các composite trong ví dụ nhận bản sao danh sách `final` qua constructor; không có setter để tự tạo một vòng tham chiếu. Đây là một cách đơn giản để tránh cấu trúc bị thay đổi sau khi khởi tạo. Nếu ứng dụng sử dụng factory/provider hoặc cấu trúc mutable phức tạp, vòng vẫn có thể xuất hiện và phải được phát hiện/kiểm soát riêng.

## 9. Scope và vòng đời: composite có thể sống lâu hơn các child?

Một composite thường được xem như “chỉ là danh sách rule”, nhưng nhiều leaf có thể giữ **session, connection, request context** hoặc tài nguyên cần đóng. Khi đó, câu hỏi scope rất quan trọng.

Giả sử:

- `AllOfRule` được đăng ký **singleton**, sống toàn ứng dụng.
- Một child giữ `RequestContext` của **một request**.
- Composite giữ child đó trong field và được dùng cho nhiều request sau.

Đây là một **scope mismatch**: object sống dài giữ state gắn với request đầu tiên. Dù framework đã inject thành công, ngữ nghĩa nghiệp vụ và an toàn dữ liệu có thể sai.

Các hướng thiết kế thường hợp lý:

1. **Rule bất biến, stateless:** xây composite một lần và truyền dữ liệu request vào `check(request)`. Đây là lựa chọn ưu tiên của ví dụ.
2. **Leaf theo mỗi request:** tạo composite theo request/work scope; tất cả child liên quan được quản lý trong cùng scope.
3. **Dữ liệu theo request chỉ là đầu vào:** truyền nó qua tham số phương thức, không giữ `RequestContext` trong singleton.
4. **Factory/provider khi thật sự cần tạo collaborator ngắn hạn:** xác định rõ ai tạo, ai dùng, ai đóng và liệu mỗi lần gọi có trả instance mới không.

**DI container không tự làm một leaf mutable trở thành thread-safe** khi composite được đăng ký singleton. Tương tự, inject `Supplier<Leaf>` không đồng nghĩa mỗi lần `get()` trả instance mới; điều đó phụ thuộc binding và scope.

### Ai đóng tài nguyên nếu Composite giữ nhiều child?

Nếu composite chỉ **sử dụng** những child do composition root/container sở hữu, nó thường **không tự đóng** toàn bộ child trong `check()`. Nếu composite thật sự là **owner** của các tài nguyên được tạo riêng và cần giải phóng cùng một scope, trách nhiệm đóng có thể được thể hiện qua `AutoCloseable` hoặc lifecycle manager.

Không nên tự động đóng theo thứ tự ngược khi một instance được **chia sẻ giữa hai composite**, vì có thể đóng cùng tài nguyên hai lần hoặc đóng khi composite kia vẫn dùng. Quyền sở hữu phải được khai báo riêng với quan hệ “có tham chiếu đến”.

Một ví dụ khác là composite gửi thông báo đến nhiều kênh. Nếu gửi kênh thứ nhất thành công và kênh thứ hai thất bại, `close()` hay DI scope không đảo ngược được thông báo đã gửi; cần chính sách lỗi/đền bù và tính idempotent ở mức nghiệp vụ.

## 10. Composite không phải Decorator, Chain of Responsibility hay container

Các kỹ thuật kết hợp khác cũng có thể giữ tham chiếu tới object cùng interface. Phân biệt đúng sẽ giúp tránh dùng Composite cho mọi vấn đề.

| Kỹ thuật | Ý tưởng chính | Ví dụ |
| --- | --- | --- |
| **Composite** | Gom **nhiều component** thành một component và tổng hợp hành vi | AND/OR của nhiều `OfferRule` |
| **Decorator** | Bọc một component để thêm hành vi trước/sau mà vẫn giữ interface | `LoggingRule` bọc một rule, đo thời gian |
| **Chain of Responsibility** | Chuyển yêu cầu theo chuỗi handler, handler quyết định xử lý/chuyển tiếp | Chuỗi kiểm tra với cơ chế dừng theo kết quả |
| **Strategy** | Thay một thuật toán bằng implementation khác cùng hợp đồng | `PricingStrategy` lựa chọn theo thị trường |
| **DI / Composition root** | Cung cấp những collaborator và lắp object graph | Tạo `new AllOfRule(List.of(...))` |
| **DI container** | Tự động hóa đăng ký, resolve, scope và lifecycle của object graph | Cấu hình framework tạo cây `OfferRule` |

Một `AllOfRule` có thể đồng thời là **Composite** và được tạo qua **DI**. Nhưng nó không vì vậy trở thành DI container: nó **không tra cứu binding toàn cục** hay chịu trách nhiệm tạo toàn bộ object graph. Nó chỉ thực hiện **một phép tổng hợp nghiệp vụ** trên các child đã được cấp.

Tương tự, một danh sách handler gọi tuần tự chưa chắc là Composite. Nếu handler không có hợp đồng chung để bản thân danh sách có thể được dùng thay một handler đơn lẻ, cấu trúc đó có thể chỉ là pipeline. Nếu sự khác biệt này không đem lại giá trị, đôi khi một vòng lặp đơn giản rõ hơn việc tạo cả hệ phân cấp class.

## 11. Biến cấu trúc thành cấu hình mà không đẩy logic vào service

Khi hệ thống có nhiều thị trường hoặc gói sản phẩm, composition root có thể tạo các cây khác nhau từ **cấu hình đã được parse/validate**:

~~~java
// Minh họa cách chọn cấu trúc ở composition root.
OfferRule buildPolicy(OfferConfig config) {
    OfferRule verified = new VerifiedCustomerRule();

    OfferRule regular = new AllOfRule(List.of(
            new AmountAtMostRule(config.standardLimit()),
            new CountryRule(config.supportedCountry())));

    if (config.vipEnabled()) {
        return new AllOfRule(List.of(
                verified,
                new AnyOfRule(List.of(
                        regular, new VipCustomerRule()))));
    }
    return new AllOfRule(List.of(verified, regular));
}
~~~

Đây là đoạn mô tả thiết kế, **không phải chương trình biên dịch độc lập** vì `OfferConfig` được giả định tồn tại. Ý nghĩa của nó là việc **chọn cấu trúc thuộc composition root**; `OfferService` không tự biết môi trường hay lắp các leaf cụ thể.

Khi nhập cấu hình từ tệp/JSON, cần thêm cơ chế:

- **Allowlist loại rule** được phép tạo: không tự động instantiate class chỉ từ chuỗi tùy ý nhận được.
- **Xác thực tham số:** giới hạn tiền dương, mã quốc gia hợp lệ, không có node thiếu child.
- **Giới hạn độ sâu và số lượng node:** tránh cây quá lớn hoặc cấu trúc bất thường làm tốn tài nguyên.
- **Phát hiện chu trình** nếu cấu hình cho phép tham chiếu node theo ID.
- **Theo dõi phiên bản chính sách:** để kết quả kiểm tra có thể truy vết cây nào đã được dùng.
- **Phân tách bí mật:** không ghi cấu hình chứa token/endpoint nhạy cảm vào log chẩn đoán.

DI container có thể hỗ trợ đăng ký và tạo bean, nhưng **không tự chuyển một cấu trúc chính sách không hợp lệ thành hợp đồng đúng**. Đối với cấu hình động, nên xây dựng và kiểm tra **toàn bộ cây mới** trước khi thay cây đang phục vụ request; nếu nhiều luồng cùng đọc, cần cơ chế công bố và quản lý lifecycle rõ ràng.

## 12. Ví dụ ghép với DI container: giữ nguyên interface và composite

Sau khi thiết kế và kiểm thử bằng Java thuần, ta có thể để framework khởi tạo các leaf và composite. Ví dụ **Spring Java Configuration** dưới đây minh họa ý tưởng; cần Spring dependency và import tương ứng, không chạy riêng bằng lệnh `javac` ở phần thực hành:

~~~java
@Configuration
class OfferWiring {
    @Bean
    OfferService offerService() {
        OfferRule verified = new VerifiedCustomerRule();

        OfferRule regular = new AllOfRule(List.of(
                new AmountAtMostRule(1_000_000),
                new CountryRule("VN")));

        OfferRule policy = new AllOfRule(List.of(
                verified,
                new AnyOfRule(List.of(
                        regular, new VipCustomerRule()))));

        return new OfferService(policy);
    }
}
~~~

Cách trên để container quản lý bean `OfferService` trả về từ factory method; các rule trong phương thức được xây dựng thủ công để minh họa cấu trúc. Nếu cần **mỗi leaf là bean do container quản lý**, có thể khai báo nhiều `@Bean` hoặc component và truyền chúng vào method cấu hình một cách tường minh.

Khi có nhiều bean đều triển khai `OfferRule`, không nên mặc định container sẽ tự chọn “đúng rule gốc” nếu injection chỉ yêu cầu `OfferRule` mà không phân biệt. Một số framework hỗ trợ qualifier, tên bean, collection injection hoặc factory method có tham số rõ ràng. Cần định nghĩa **binding không mơ hồ**, thứ tự child và scope; đừng để một `List<OfferRule>` được container tổng hợp theo thứ tự bất định rồi dùng cho logic nhạy cảm với thứ tự.

Khi chuyển từ DI thủ công sang container, **không cần sửa `OfferService.assess()`**. Thay đổi chính là cách chọn và cung cấp object graph ở ranh giới khởi động.

## 13. Dấu hiệu cần kiểm tra khi Composite được inject

| Dấu hiệu | Điều có thể sai | Cách khắc phục |
| --- | --- | --- |
| Composite constructor tự tạo mọi leaf bằng `new` | Cấu trúc và chính sách bị đóng cứng trong class | Inject danh sách child, xây cây tại composition root |
| Service nghiệp vụ gọi `instanceof AllOfRule` để chọn xử lý | Client phải biết cấu trúc cụ thể | Giữ hợp đồng `OfferRule` nhất quán để thay thế |
| Một leaf trả `null` thay vì `Decision` | Phá hợp đồng component | Kiểm tra ở ranh giới; sửa implementation và contract test |
| `AnyOfRule` chạy mọi child dù đã có một nhánh đạt | Chính sách short-circuit không được tôn trọng | Test số lần gọi và thứ tự bằng fake |
| `AllOfRule` bỏ qua các lỗi sau lỗi đầu tiên | Không đáp ứng yêu cầu tổng hợp đầy đủ lý do | Test nhiều child thất bại và danh sách reasons |
| Danh sách child bị sửa sau khi composite tạo | Cấu trúc biến đổi ngoài dự kiến | Sao chép list; dùng constructor và graph bất biến |
| Một leaf mutable dùng chung giữa nhiều request | Scope sai hoặc thiếu thread-safety | Tách input theo request, đổi scope hoặc dùng factory phù hợp |
| Đồ thị lồng nhau có vòng A → B → A | Đệ quy có thể không kết thúc | Phát hiện chu trình trước khi xuất bản graph |
| Child gây side effect nhưng composite giả định atomicity | Một số child đã chạy dù toàn bộ tổng hợp thất bại | Thiết kế policy lỗi/transaction/đền bù riêng |
| Một child dùng chung bị nhiều composite đóng | Ownership của tài nguyên không rõ | Đóng ở đúng scope/owner, không tự đóng vì đang giữ tham chiếu |
| Bean `OfferRule` có nhiều implementation và container không biết chọn | Binding mơ hồ | Khai báo qualifier/factory method rõ ràng |

## 14. Quy trình thiết kế Composite kết hợp DI

1. **Xác định một khả năng có ý nghĩa với client.** Ví dụ “đánh giá điều kiện ưu đãi”, thay vì một interface quá chung như `Executable`.
2. **Định nghĩa hợp đồng thống nhất.** Nêu rõ tham số, kết quả, lỗi và side effect. Leaf và composite phải giữ cùng lời hứa.
3. **Tìm phần tử lá độc lập.** Mỗi leaf nên có một trách nhiệm rõ và có thể kiểm thử riêng.
4. **Chọn phép tổng hợp.** AND, OR, ưu tiên hoặc tổng hợp toàn bộ phải được đặc tả rõ, đặc biệt về short-circuit.
5. **Đưa child vào constructor.** Nhận `List<? extends Component>`, kiểm tra không rỗng/không null khi phù hợp và sao chép list nếu cấu trúc cần ổn định.
6. **Lắp cây ở composition root.** Service nghiệp vụ chỉ nhận component gốc; không dùng service locator để tự tìm leaf.
7. **Đánh dấu scope và ownership.** Rule stateless có thể dùng chung; rule giữ tài nguyên cần chính sách cấp/đóng riêng.
8. **Kiểm tra đồ thị không vòng.** Với cây sinh từ cấu hình, giới hạn độ sâu và phát hiện node tham chiếu ngược.
9. **Viết test cho leaf và composite.** Kiểm tra truth table, thứ tự, short-circuit, lý do lỗi và thay thế fake.
10. **Mở rộng sang container khi cần.** Cấu hình bean, qualifier và scope dựa trên graph đã hiểu; không để framework quyết định ngữ nghĩa nghiệp vụ.

### Câu hỏi tự kiểm tra

**Tình huống A:** `AllOfRule` nhận một `List<OfferRule>` qua constructor; trong danh sách có cả leaf lẫn `AnyOfRule`. Đây có phải Composite không?

**Có.** Leaf và composite cùng thực hiện `OfferRule`, còn composite tổng hợp các child. Việc child lại là composite cho phép cấu trúc đệ quy.

**Tình huống B:** `OfferService` tự viết `new CountryRule("VN")` trong `assess()`. Composite vẫn hoạt động, vậy DI đã được áp dụng đúng ranh giới chưa?

**Chưa.** Service đang quyết định cách tạo và cấu hình một phần dependency. Có thể chuyển việc chọn rule và lắp đồ thị ra composition root, rồi inject composite gốc.

**Tình huống C:** `AnyOfRule` đã nhận một child cho phép nhưng vẫn gọi child tiếp theo; child đó gửi email. Có vấn đề không?

**Có.** Nếu hợp đồng OR của bài quy định short-circuit, lời gọi thêm vừa sai quy tắc vừa có thể gây side effect không mong muốn. Cần test số lần gọi và giữ child kiểm tra thuần túy khi phù hợp.

**Tình huống D:** Hai composite cùng giữ một `CountryRule` immutable. Có phải tạo hai instance để “đúng DI” không?

**Không.** DI không bắt buộc mọi tham chiếu là instance mới. Chia sẻ một rule stateless, immutable có thể phù hợp; cần xét scope và thread-safety nếu rule có trạng thái mutable.

**Tình huống E:** Một `AllOfRule` singleton giữ `RequestContextRule` chứa thông tin request đầu tiên. Container có tự bảo đảm request thứ hai không thấy dữ liệu cũ không?

**Không.** Đây là lỗi lifetime. Nên truyền request data qua `check(request)`, hoặc tạo rule/composite theo request scope với cơ chế cấp đúng.

**Tình huống F:** Biến `List<OfferRule> original` được sửa sau khi tạo composite có `List.copyOf(original)`. Cấu trúc composite có thay đổi theo không?

**Không**, vì constructor đã sao chép cấu trúc list. Nhưng những **object child** trong list vẫn là cùng tham chiếu; trạng thái nội bộ của chúng, nếu mutable, không được sao chép sâu.

## Ghi nhớ

**Composite** cho phép xây một dependency phức hợp từ nhiều component cùng interface, còn **Dependency Injection** giúp cung cấp và lắp các component ấy bên ngoài logic nghiệp vụ. Khi composite nhận các child bằng **constructor injection**, composition root có thể xây cây AND/OR hoặc các cấu trúc khác một cách tường minh và kiểm thử được. Hợp đồng tổng hợp, thứ tự thực hiện, trạng thái, scope, lifecycle và quyền sở hữu tài nguyên vẫn phải được xác định rõ; DI container chỉ hỗ trợ tự động hóa việc lắp ghép chứ không tự quyết định quy tắc xử lý.
