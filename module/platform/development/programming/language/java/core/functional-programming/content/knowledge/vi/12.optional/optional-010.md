# Vai trò chính của Optional ở giá trị trả về và giới hạn khi lạm dụng

## 1. Optional giải quyết vấn đề nào?

Trong Java, **java.util.Optional<T>** là một đối tượng chứa **có hoặc không có một giá trị tham chiếu kiểu T**. Nó thường dùng làm **kiểu trả về của phương thức** khi việc không tìm thấy dữ liệu là một kết quả bình thường, được dự kiến trước và người gọi cần quyết định xử lý thế nào.

Ví dụ một phương thức tìm khách hàng theo mã:

~~~java
Optional<Customer> findCustomerById(String customerId);
~~~

Đây là **chữ ký API minh họa**, không phải chương trình độc lập. Nó diễn đạt hai khả năng: trả một Customer, hoặc không có Customer tương ứng. Caller nhận được tín hiệu rõ ràng trong chữ ký rằng **không có giá trị** là một trạng thái phải xem xét. Điều này thường dễ đọc hơn việc trả **Customer** với quy ước “null nghĩa là không tìm thấy” chỉ ghi trong tài liệu.

Optional **không** đảm bảo rằng mọi lỗi biến thành trạng thái rỗng, cũng không thay thế validation, exception, domain model hay collection. Nó là một công cụ nhỏ để diễn đạt **kết quả tùy chọn**; lạm dụng ở mọi nơi sẽ khiến API phức tạp và đôi khi che mất ý nghĩa nghiệp vụ.

Tư duy cốt lõi:

~~~text
findById(id)
   |
   +-- Tìm thấy một đối tượng hợp lệ ---> Optional.of(value)
   |
   +-- Không có đối tượng tương ứng ---> Optional.empty()
   |
   +-- Hệ thống bị lỗi (I/O, DB, quyền truy cập...) ---> xử lý/báo lỗi
                                                 theo hợp đồng,
                                                 không tự coi là "không có"
~~~

**Optional<T> không đồng nghĩa với nullable T:** với nullable T, người gọi có thể quên kiểm tra null; với Optional<T>, API nêu rõ sự vắng mặt. Dù vậy, kiểu dữ liệu không ép người gọi xử lý đúng về mặt nghiệp vụ: vẫn có thể gọi **get()** không kiểm tra rồi gây lỗi.

## 2. Khi nào Optional là lựa chọn tốt cho giá trị trả về?

Một số tình huống phù hợp:

| Phương thức | Khi có giá trị | Khi không có giá trị |
| --- | --- | --- |
| **findUserById(id)** | User đã tìm thấy | Không có user với ID đó |
| **findHeader(name)** | Giá trị header tồn tại | Header vắng mặt |
| **lookupCache(key)** | Cache chứa giá trị | Cache miss bình thường |
| **firstMatching(items)** | Phần tử thỏa điều kiện | Không phần tử nào thỏa |
| **parseKnownCode(text)** | Mã được nhận diện | Chuỗi không thuộc danh mục đã biết |

Những ví dụ trên chỉ là **ý tưởng hợp đồng**, không phải bảo đảm mọi implement đều dùng Optional. Khi phương thức có thể không tìm thấy dữ liệu và **không có dữ liệu không phải lỗi**, trả **Optional<T>** giúp người gọi thấy kết quả này ngay trong API.

Ngược lại, nếu **giá trị bắt buộc phải tồn tại** theo bất biến nghiệp vụ, một phương thức như **loadRequiredUser(id)** có thể trả User trực tiếp và ném exception thích hợp khi dữ liệu thiếu. Trả Optional chỉ để người gọi luôn viết **orElseThrow** đôi khi làm hợp đồng kém rõ.

Một câu hỏi thiết kế hữu ích: **“Đối tượng vắng mặt có phải một kết quả hợp lệ mà caller được quyền xử lý khác nhau?”** Nếu có, Optional là ứng viên tốt. Nếu không, hãy chọn hợp đồng phù hợp hơn.

### 2.1. Phân biệt ba trạng thái

Trong hệ thống thật cần phân biệt:

1. **Tìm thấy:** trả giá trị.
2. **Không tìm thấy hợp lệ:** trả Optional.empty().
3. **Không thể tìm kiếm vì lỗi:** ném exception, trả kiểu Result có lỗi, hoặc áp dụng chính sách thất bại được công bố.

Ví dụ một kho dữ liệu mất kết nối **không** nên mặc nhiên trả Optional.empty() như thể chắc chắn không có khách hàng. Làm vậy che khuất lỗi vận hành và có thể khiến caller ra quyết định sai.

Optional chỉ biểu diễn **hai trạng thái về giá trị**: có hoặc không. Nếu nghiệp vụ cần phân biệt “đã xóa”, “không có quyền truy cập”, “chưa đồng bộ”, “cần duyệt”, thì Optional đơn lẻ có thể **không đủ thông tin**.

## 3. Ba cách tạo Optional: of, ofNullable, empty

### 3.1. Optional.of(value)

**Optional.of(value)** dành cho giá trị **chắc chắn không null**.

~~~java
Optional<String> city = Optional.of("Hà Nội");
~~~

Đoạn minh họa cần import **java.util.Optional**. Giá trị bên trong là **"Hà Nội"**. Nếu truyền **null**, phương thức **of(null)** lập tức ném **NullPointerException**. Đây có thể là điều hữu ích khi bạn muốn phá vỡ chương trình sớm để phát hiện một bất biến đã bị vi phạm.

### 3.2. Optional.ofNullable(value)

**Optional.ofNullable(value)** tạo Optional có giá trị nếu đối số khác null, hoặc Optional.empty() nếu đối số null.

~~~java
String nickname = null;
Optional<String> nicknameResult = Optional.ofNullable(nickname);
~~~

Đây là đoạn minh họa. **nicknameResult.isEmpty()** trả true. Cách này thường dùng ở **ranh giới chuyển đổi API cũ trả nullable** sang API mới trả Optional, ví dụ từ **Map.get(key)** khi null được định nghĩa là “không tìm thấy”.

**Không nên dùng ofNullable một cách máy móc** để che một giá trị bắt buộc không được null. Nếu một trường bắt buộc mà lại null do lỗi, trả empty() sẽ làm mất tín hiệu bug.

### 3.3. Optional.empty()

**Optional.empty()** thể hiện rõ không có giá trị:

~~~java
Optional<String> noNickname = Optional.empty();
~~~

Nếu phương thức trả **Optional<User>**, nên trả **Optional.empty()** khi không có User; **không** trả **null** thay cho Optional rỗng.

**Quy ước cần duy trì:** phương thức đã công bố trả Optional phải trả **một Optional không null** trong trường hợp trả về bình thường. Trả **null** từ phương thức Optional làm mất mục đích thiết kế và gây NullPointerException khi caller dùng **map**, **orElse**, **isPresent**...

### 3.4. So sánh nhanh

| Factory | Đối số khác null | Đối số null |
| --- | --- | --- |
| **Optional.of(value)** | Optional chứa value | Ném NullPointerException |
| **Optional.ofNullable(value)** | Optional chứa value | Optional.empty() |
| **Optional.empty()** | Không nhận đối số | Luôn rỗng |

**Đừng lồng Optional một cách vô ý:** nếu một phương thức đã trả Optional<T>, bọc nó bằng **Optional.ofNullable(...)** sẽ tạo ra **Optional<Optional<T>>**, thường làm caller xử lý phức tạp hơn. Muốn kết hợp hai phép tra cứu Optional, dùng **flatMap** khi thích hợp.

## 4. Ví dụ Java 17 hoàn chỉnh: tìm dữ liệu và trả Optional

Bài toán: tìm người dùng theo ID trong một repository đơn giản. Không có ID là chuyện bình thường, còn ID null bị xem là đầu vào không hợp lệ. Người dùng có thể chưa khai báo email.

Tạo tệp **OptionalReturnDemo.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

record User(String id, String name, String email) {}

public class OptionalReturnDemo {
    static final Map<String, User> USERS = Map.of(
            "u1", new User("u1", "Lan", "lan@example.test"),
            "u2", new User("u2", "Minh", null)
    );

    static Optional<User> findUser(String id) {
        Objects.requireNonNull(id, "id");
        return Optional.ofNullable(USERS.get(id));
    }

    static String displayName(String id) {
        return findUser(id)
                .map(User::name)
                .orElse("Khách");
    }

    static String emailOrDefault(String id) {
        return findUser(id)
                .map(User::email)
                .filter(email -> !email.isBlank())
                .orElse("(chưa có)");
    }

    public static void main(String[] args) {
        System.out.println("find u1: "
                + (findUser("u1").isPresent() ? "Có" : "Không"));
        System.out.println("find ux: "
                + (findUser("ux").isPresent() ? "Có" : "Không"));
        System.out.println("name u1: " + displayName("u1"));
        System.out.println("name ux: " + displayName("ux"));
        System.out.println("mail u1: " + emailOrDefault("u1"));
        System.out.println("mail u2: " + emailOrDefault("u2"));

        List<String> names = List.of("u1", "ux", "u2").stream()
                .map(OptionalReturnDemo::findUser)
                .flatMap(Optional::stream)
                .map(User::name)
                .toList();
        System.out.println("names: " + names);
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 OptionalReturnDemo.java
java OptionalReturnDemo
~~~

Stdout:

~~~text
find u1: Có
find ux: Không
name u1: Lan
name ux: Khách
mail u1: lan@example.test
mail u2: (chưa có)
names: [Lan, Minh]
~~~

**Giải thích:**

1. **findUser(id)** là ranh giới API trả Optional. **Map.get** trả null nếu không có key; **ofNullable** chuyển quy ước này thành Optional.empty().
2. **Objects.requireNonNull(id)** phân biệt rõ **đầu vào null là sai hợp đồng** với **ID không có trong kho dữ liệu là kết quả bình thường**.
3. **displayName** không cần gọi **get()**. **map(User::name)** tạo Optional<String> nếu tìm thấy User, rồi **orElse("Khách")** đặt fallback.
4. **emailOrDefault** minh họa một User có thể có **email == null**. **map(User::email)** chuyển kết quả null thành Optional.empty(); **filter** chỉ kiểm tra isBlank khi đã có String.
5. **Optional::stream** tạo Stream có **0 hoặc 1 phần tử**. **flatMap(Optional::stream)** bỏ những lần tra cứu rỗng và làm phẳng những lần có User.
6. Danh sách đầu vào có **u1**, **ux** (không tồn tại) và **u2**, nên kết quả cuối là **[Lan, Minh]** theo thứ tự gặp của Stream tuần tự.

**Quan trọng:** lớp **User** ở đây là mô hình minh họa. Trong ứng dụng thực, email optional có thể được mô hình hóa bằng quy tắc domain, validation hoặc đối tượng riêng. Ví dụ này cố ý dùng một trường nullable ở dữ liệu mẫu để cho thấy Optional tại **ranh giới trả về** hoạt động ra sao; nó **không khuyến nghị** biến mọi field thành Optional.

## 5. Dùng Optional theo hướng tiêu thụ giá trị

Khi nhận **Optional<T>**, caller thường có những lựa chọn:

- **map(...)**: biến đổi giá trị nếu có.
- **flatMap(...)**: tiếp tục một thao tác khác cũng trả Optional, tránh lồng Optional.
- **filter(...)**: giữ giá trị nếu thỏa điều kiện.
- **orElse(...)**: lấy giá trị hoặc fallback có sẵn.
- **orElseGet(...)**: tạo fallback lười bằng Supplier.
- **orElseThrow(...)**: biến trạng thái thiếu thành exception được xác định.
- **ifPresent(...) / ifPresentOrElse(...)**: thực hiện hành động có side effect.
- **stream()**: biểu diễn Optional thành Stream 0/1 phần tử.

### 5.1. map(): biến đổi khi có dữ liệu

~~~java
Optional<User> maybeUser = findUser("u1");
Optional<String> name = maybeUser.map(User::name);
~~~

Đây là đoạn minh họa giả định dùng **User** và **findUser** trong ví dụ trên. Nếu maybeUser rỗng, **User::name** không được gọi. Nếu mapper trả **null**, **Optional.map** trả Optional.empty(), thay vì một Optional chứa null.

Khi cần chuyển **User → String** trong cùng một Optional, đây thường dễ đọc hơn:

~~~java
String label = maybeUser.isPresent()
        ? maybeUser.get().name()
        : "Khách";
~~~

Đoạn minh họa này hợp lệ khi có maybeUser, nhưng cách viết dùng **map(...).orElse(...)** thể hiện chuỗi xử lý tốt hơn và tránh dựa vào **get()**.

### 5.2. filter(): kiểm tra điều kiện khi có giá trị

~~~java
Optional<String> approvedCode = Optional.of("AB-12")
        .filter(code -> code.startsWith("AB-"));
~~~

Đây là đoạn minh họa. Kết quả chứa **"AB-12"**. Nếu điều kiện false thì kết quả rỗng. Nếu Optional đầu vào đã rỗng, Predicate không được gọi.

Dùng filter để quyết định **giữ hay bỏ một giá trị tùy chọn**, không phải thay thế toàn bộ quy trình validation có nhiều thông báo lỗi. Nếu một mã không hợp lệ cần trả về **lý do**, chỉ dùng Optional.empty() sẽ mất lý do đó.

### 5.3. flatMap(): tránh Optional<Optional<T>>

Giả sử phương thức **UserSettingsRepository.findSettings(user)** trả Optional<Settings>. Khi người dùng có thể không tồn tại:

~~~java
Optional<Settings> settings = findUser(id)
        .flatMap(settingsRepository::findSettings);
~~~

Đây là **đoạn API minh họa**, giả định đã định nghĩa Settings, repository và id. **flatMap** nhận mapper trả **Optional<Settings>** rồi tạo một Optional<Settings> duy nhất. Nếu dùng **map**, kiểu kết quả thường là **Optional<Optional<Settings>>**.

**Chú ý:** Mapper truyền cho **Optional.flatMap** phải trả **Optional không null**; nếu trả null, Java ném NullPointerException. Khác với **Optional.map**, việc trả null từ một mapper Optional là vi phạm hợp đồng.

### 5.4. ifPresent và ifPresentOrElse

~~~java
findUser("u1")
        .ifPresent(user -> System.out.println(user.name()));
~~~

Đây là đoạn minh họa: nếu có User, thực hiện Consumer; nếu không, bỏ qua. **ifPresent** trả **void**, không trả Optional mới để nối tiếp phép biến đổi. Dùng khi mục tiêu thật sự là hành động, ví dụ in log, thông báo, cập nhật UI.

Từ Java 9 có **ifPresentOrElse(action, emptyAction)**:

~~~java
findUser("ux").ifPresentOrElse(
        user -> System.out.println(user.name()),
        () -> System.out.println("Không có người dùng")
);
~~~

Đây là đoạn minh họa. Chương trình in **Không có người dùng** ở trường hợp ID ux không tồn tại. Nếu cần trả String cho caller thay vì thực hiện side effect, **map(...).orElse(...)** hoặc **orElseGet(...)** thường phù hợp hơn.

## 6. Phân biệt orElse và orElseGet: eager vs lazy

Đây là điểm dễ gây lỗi hiệu năng và side effect.

**orElse(fallbackExpression)** nhận **một giá trị T**. Trước khi phương thức orElse được gọi, Java phải **đánh giá biểu thức fallback** để tính đối số, dù Optional đang có giá trị. Nếu fallback chỉ là literal rẻ, điều này không đáng ngại.

**orElseGet(supplier)** nhận **Supplier<? extends T>**. Java chỉ gọi **supplier.get()** khi Optional rỗng. Với fallback tốn công như truy vấn khác, tạo object lớn hay ghi log, đây thường là lựa chọn phù hợp hơn.

Tạo tệp **OptionalFallbackDemo.java**:

~~~java
import java.util.Optional;

public class OptionalFallbackDemo {
    static String makeFallback() {
        System.out.println("build fallback");
        return "fallback";
    }

    public static void main(String[] args) {
        Optional<String> present = Optional.of("ready");
        Optional<String> absent = Optional.empty();

        System.out.println("orElse: "
                + present.orElse(makeFallback()));

        System.out.println("orElseGet: "
                + present.orElseGet(OptionalFallbackDemo::makeFallback));

        System.out.println("absent: "
                + absent.orElseGet(OptionalFallbackDemo::makeFallback));

        System.out.println("literal: "
                + present.orElse("constant"));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 OptionalFallbackDemo.java
java OptionalFallbackDemo
~~~

Stdout:

~~~text
build fallback
orElse: ready
orElseGet: ready
build fallback
absent: fallback
literal: ready
~~~

**Diễn giải chính xác:**

- Ở **present.orElse(makeFallback())**, phương thức makeFallback được gọi **trước khi** orElse nhận đối số, vì thế in **build fallback** dù kết quả trả về cuối cùng vẫn là **ready**.
- Ở **present.orElseGet(...::makeFallback)**, supplier không được gọi vì Optional có giá trị; không xuất hiện dòng log thứ hai trước **orElseGet: ready**.
- Ở **absent.orElseGet(...)**, Optional rỗng nên gọi makeFallback và dùng kết quả **fallback**.
- Với **orElse("constant")**, việc đánh giá literal là rẻ và đơn giản; không cần biến mọi orElse thành orElseGet.

**Sai lầm thường gặp:** dùng **orElse(database.loadDefault())** và ngỡ rằng database chỉ được gọi khi Optional rỗng. Nếu fallback có side effect, thao tác đó vẫn diễn ra ngay cả khi đã tìm thấy giá trị.

### 6.1. or(Supplier<Optional<T>>): phương án dự phòng vẫn có thể rỗng

Java 9 bổ sung **Optional.or(...)** để lựa chọn một Optional khác **khi Optional đầu rỗng**:

~~~java
Optional<String> result = Optional.<String>empty()
        .or(() -> Optional.of("backup"));
~~~

Đây là đoạn minh họa. Kết quả chứa **backup**. Khác với **orElseGet**, supplier của **or** phải trả **Optional**, không trả trực tiếp T. Nó thích hợp khi muốn thử **nguồn tra cứu thứ hai** cũng có thể không tìm thấy:

~~~java
Optional<User> found = findPrimary(id)
        .or(() -> findSecondary(id));
~~~

Đây là đoạn API minh họa, giả định hai hàm trả Optional<User>. **findSecondary** chỉ được gọi khi **findPrimary** rỗng. Nếu supplier của **or** trả null thì Java ném NullPointerException; không dùng null như một Optional rỗng.

## 7. orElseThrow(): chuyển sự vắng mặt thành lỗi khi đúng hợp đồng

Nếu caller **bắt buộc** phải có giá trị, có thể chuyển Optional.empty() thành exception rõ nghĩa:

~~~java
User required = findUser(id)
        .orElseThrow(() ->
                new IllegalArgumentException("Unknown user: " + id));
~~~

Đây là đoạn API minh họa. Exception được tạo bởi Supplier chỉ khi Optional rỗng. Dùng **orElseThrow(Supplier<? extends X>)** nếu muốn exception có thông điệp/kiểu phù hợp với caller.

Ngoài ra còn có **orElseThrow()** không tham số (Java 10+), ném **NoSuchElementException** nếu Optional rỗng. Phương thức **get()** cũng ném **NoSuchElementException** trong trường hợp rỗng; tuy nhiên **get()** thường là dấu hiệu caller chưa thiết kế cách xử lý rõ ràng.

Chẳng hạn:

~~~java
Optional<String> maybe = Optional.empty();
// maybe.get()             -> NoSuchElementException khi chạy.
// maybe.orElseThrow()     -> NoSuchElementException khi chạy.
~~~

Đoạn minh họa trên không có lỗi biên dịch; hai dòng chú thích mô tả lỗi lúc **thực thi** nếu được bỏ comment.

**Không coi orElseThrow là bắt buộc trong mọi use case:** một API trả Optional để caller quyết định, có caller muốn fallback, có caller muốn bỏ qua, có caller muốn báo lỗi. Đừng biến việc “không tìm thấy” thành exception không cần thiết nếu đó chỉ là kết quả bình thường.

### 7.1. Khác với câu hỏi “Optional có an toàn hơn null tuyệt đối không?”

Không. Optional giúp làm rõ hợp đồng, nhưng người gọi có thể dùng sai **get()**, **orElse(null)**, hoặc bỏ qua việc kiểm tra. An toàn thực sự cần đồng thời có **thiết kế API**, **mô hình dữ liệu**, **kiểm thử**, **quy ước xử lý lỗi** và đôi khi phân tích nullability.

## 8. Chương trình Java 17: map, flatMap và mô hình quan hệ tùy chọn

Một đơn hàng có thể tồn tại nhưng chưa có địa chỉ giao hàng. Đó là hai tầng kết quả: có/không có đơn hàng; nếu có đơn hàng thì có/không có địa chỉ. **flatMap** giúp tránh Optional lồng nhau.

Tạo tệp **OptionalCompositionDemo.java**:

~~~java
import java.util.Map;
import java.util.Optional;

record Address(String city, String postalCode) {}
record Order(String id, Address shippingAddress) {}

public class OptionalCompositionDemo {
    static final Map<String, Order> ORDERS = Map.of(
            "a", new Order("a", new Address("Hà Nội", "10000")),
            "b", new Order("b", null)
    );

    static Optional<Order> findOrder(String id) {
        return Optional.ofNullable(ORDERS.get(id));
    }

    static Optional<Address> shippingAddress(Order order) {
        return Optional.ofNullable(order.shippingAddress());
    }

    static Optional<String> shippingCity(String id) {
        return findOrder(id)
                .flatMap(OptionalCompositionDemo::shippingAddress)
                .map(Address::city);
    }

    public static void main(String[] args) {
        System.out.println("a: "
                + shippingCity("a").orElse("unknown"));
        System.out.println("b: "
                + shippingCity("b").orElse("unknown"));
        System.out.println("x: "
                + shippingCity("x").orElse("unknown"));

        Optional<Optional<Address>> nested = findOrder("a")
                .map(OptionalCompositionDemo::shippingAddress);

        System.out.println("nested present: " + nested.isPresent());

        Optional<Address> flattened = findOrder("a")
                .flatMap(OptionalCompositionDemo::shippingAddress);

        System.out.println("flattened present: "
                + flattened.isPresent());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 OptionalCompositionDemo.java
java OptionalCompositionDemo
~~~

Stdout:

~~~text
a: Hà Nội
b: unknown
x: unknown
nested present: true
flattened present: true
~~~

**Ý nghĩa:**

1. **findOrder("a")** có Order, **shippingAddress** trả Optional có Address và **map(Address::city)** lấy thành phố.
2. **findOrder("b")** có Order nhưng không có địa chỉ; **flatMap** cho Optional.empty().
3. **findOrder("x")** không có Order; **flatMap** không gọi hàm shippingAddress trên một Order không tồn tại.
4. **map** một phương thức đã trả Optional tạo ra **Optional<Optional<Address>>**, khiến caller cần xử lý hai lớp Optional.
5. **flatMap** tạo thẳng **Optional<Address>**, phù hợp với mục đích “thực hiện bước tra cứu tiếp theo nếu giá trị đầu có mặt”.

**Một giới hạn của mô hình minh họa:** code dùng trường **Address** nullable trong record Order để tạo dữ liệu đầu vào và chuyển đổi ở ranh giới phương thức. Trong ứng dụng thật, hãy xác định rõ trường nào được phép vắng mặt và kiểm tra bất biến; không tự cho rằng mọi record có thể chứa null đều là mô hình domain tốt.

## 9. Optional.stream(): nối với Stream mà không kiểm tra thủ công

Từ Java 9, **Optional.stream()** trả:

- Stream có đúng **một phần tử** nếu Optional có giá trị;
- Stream **rỗng** nếu Optional.empty().

Vì vậy, với một Stream gồm nhiều Optional<T>, viết:

~~~java
List<T> values = optionals
        .flatMap(Optional::stream)
        .toList();
~~~

Đây là **đoạn minh họa**, giả định **optionals** là **Stream<Optional<T>>** có kiểu T phù hợp, và đã import List, Optional. Nó tránh dạng xử lý dài như **filter(Optional::isPresent).map(Optional::get)**.

Khi bản thân một phương thức trả **Stream<T>**, danh sách rỗng là cách biểu diễn tự nhiên khi không có phần tử; **không cần** đổi mọi kết quả collection sang Optional<List<T>>. Nếu phương thức trả **List<T>**, thường nên trả **danh sách rỗng** (không null) khi không có phần tử.

### 9.1. Optional và Stream không phải một

Optional biểu diễn **0 hoặc 1 giá trị**, còn Stream có thể có **0, 1 hoặc nhiều giá trị** và thường được xử lý theo pipeline. Đừng dùng Optional<List<T>> chỉ để nói “có thể danh sách rỗng” nếu **empty list** đã đủ diễn đạt trạng thái. Chỉ dùng Optional<List<T>> khi **“không có danh sách/không được cung cấp danh sách”** khác về nghĩa với **“có danh sách và danh sách này rỗng”**; khi đó cần tài liệu hóa rõ hai trạng thái.

## 10. Giới hạn khi lạm dụng Optional

### 10.1. Không mặc định dùng Optional cho field của entity/DTO/record

Một kiểu dữ liệu như sau thường khiến việc khởi tạo, serialization, persistence và mapping trở nên rắc rối nếu không có lý do rõ ràng:

~~~java
class PersonDto {
    Optional<String> nickname;
}
~~~

Đây là **ví dụ thiết kế để thảo luận**, không khuyến nghị đem nguyên vào chương trình. Với một DTO lưu trữ hay đối tượng dữ liệu thuần, thường tiện hơn khi dùng **String nickname** có quy tắc nullability/validation rõ ràng, hoặc một kiểu miền nghiệp vụ phù hợp, rồi trả Optional từ phương thức đọc:

~~~java
class Person {
    private final String nickname; // Theo hợp đồng có thể null.

    Person(String nickname) {
        this.nickname = nickname;
    }

    Optional<String> nickname() {
        return Optional.ofNullable(nickname);
    }
}
~~~

Đoạn này là **lớp minh họa** cần import Optional. Cách thiết kế này giữ Optional chủ yếu ở **ranh giới trả về**. Nó cũng tránh tạo **Optional** như trạng thái mutable được lưu trong field mà có thể bị gán null.

**Không tuyên bố mọi framework đều cấm Optional field.** Một số serializer/binder có module hỗ trợ Optional; một số khác không hoặc xử lý khác nhau. Vấn đề là **contract và khả năng tương thích của các công cụ**, không phải quy tắc trình biên dịch rằng mọi field Optional đều sai.

**Về Java serialization:** java.util.Optional không triển khai **java.io.Serializable** theo JDK chuẩn. Vì thế, đặt Optional trực tiếp trong một object đòi hỏi Java serialization mặc định có thể gây **NotSerializableException**, nếu field đó được tuần tự hóa. JSON serialization là cơ chế khác, phụ thuộc library và cấu hình.

### 10.2. Đừng mặc định nhận Optional làm tham số

Ví dụ:

~~~java
void sendMessage(String message, Optional<String> label)
~~~

Đây là **chữ ký minh họa**. Nếu caller luôn phải tạo **Optional.of(label)** hoặc **Optional.empty()** chỉ để gọi, API có thể trở nên dài và bất tiện. Với một tham số tùy chọn, cân nhắc **overload**, **builder**, **options object**, hoặc một hợp đồng cho phép null ở ranh giới nội bộ khi phù hợp và được quản lý.

Chẳng hạn:

~~~java
void sendMessage(String message);
void sendMessage(String message, String label);
~~~

Đây là hai chữ ký minh họa. Không phải lúc nào overload cũng tốt: nếu có nhiều tham số tùy chọn, builder/options object thường dễ mở rộng hơn. Nếu mục đích của API thật sự là **nhận một kết quả tùy chọn làm dữ liệu đầu vào**, tham số Optional có thể hợp lý; chỉ không nên dùng nó theo thói quen.

### 10.3. Không bao bọc collection một cách dư thừa

So sánh:

~~~java
List<User> searchUsers(String query);
Optional<List<User>> searchUsersWrapped(String query);
~~~

Hai dòng trên là chữ ký minh họa. Khi **không tìm được người dùng**, **List.of()** trả danh sách rỗng thường đã đủ. Optional<List<User>> đẩy thêm một nhánh xử lý tới caller mà không mang lại thông tin mới.

Trường hợp Optional<List<T>> có thể đúng là khi “**chưa thực hiện truy vấn**” khác với “**đã truy vấn và không có kết quả**”. Nếu cần biểu diễn thêm trạng thái tải dữ liệu, lỗi hoặc quyền truy cập, một kiểu kết quả chuyên biệt thường giàu nghĩa hơn.

### 10.4. Không dùng Optional để thay thế mọi exception

Không nên nuốt lỗi dữ liệu nguồn:

~~~java
// Ví dụ minh họa phản mẫu:
try {
    return Optional.of(loadFromDatabase());
} catch (Exception ignored) {
    return Optional.empty();
}
~~~

Đây là **đoạn cố ý không đầy đủ**, không có lớp/method bao quanh. Nó nguy hiểm vì coi mọi exception là “không tìm thấy”. Ngoài ra, **Optional.of(...)** sẽ ném NullPointerException nếu loadFromDatabase trả null. Caller mất khả năng phân biệt **database mất kết nối**, **dữ liệu hỏng** và **ID không tồn tại**.

Hãy chỉ trả empty khi thực sự không có giá trị. Các lỗi bất thường phải được xử lý theo chính sách hệ thống — exception thích hợp, retry, error result, log/metrics có kiểm soát.

### 10.5. Tránh get() sau một chuỗi kiểm tra rườm rà

Mã kiểu sau thường khó mở rộng:

~~~java
Optional<User> found = findUser(id);
if (found.isPresent()) {
    return found.get().name();
}
return "Khách";
~~~

Đây là **đoạn minh họa nằm trong một phương thức trả String**. Với logic đơn giản, có thể viết:

~~~java
return findUser(id)
        .map(User::name)
        .orElse("Khách");
~~~

Nó thể hiện việc biến đổi có điều kiện và fallback, tránh **get()**. Tuy nhiên, một **if/else** rõ ràng vẫn tốt khi cần nhiều hành động, ghi log, hoặc xử lý lỗi phức tạp. Không có quy tắc buộc toàn bộ chương trình phải biến thành chuỗi Optional.

### 10.6. Không dùng Optional cho mọi biểu thức cục bộ

Đoạn sau thường tạo thêm đối tượng/nhánh không cần thiết:

~~~java
Optional<Integer> sum = Optional.of(a + b);
int result = sum.orElse(0);
~~~

Đây là đoạn minh họa giả định a, b là int. Nếu **a + b** luôn tạo một int và không có khái niệm vắng mặt, nên giữ **int result = a + b;**. Optional phù hợp khi kiểu trả về cần diễn đạt absence; không phải lớp vỏ mặc định cho mọi giá trị.

## 11. Value-based class: không dựa vào identity của Optional

Theo JDK, **Optional là value-based class**. Vì thế, cần tránh dựa vào **danh tính object** của các instance Optional như một phần hợp đồng:

- Không so sánh Optional bằng **==** để kiểm tra có cùng nội dung. Dùng **equals(...)** khi cần so sánh giá trị, hoặc tốt hơn xử lý theo nội dung.
- Không khóa đồng bộ bằng **synchronized(optional)**. Java cảnh báo việc dùng đối tượng value-based làm monitor có thể mang hành vi không đáng tin cậy trong những phiên bản/JVM tương lai.
- Không dựa vào **System.identityHashCode(optional)** hoặc việc **Optional.empty()** luôn là đúng một object duy nhất. JDK không hứa về identity kiểu đó.

Ví dụ:

~~~java
Optional<String> first = Optional.of("A");
Optional<String> second = Optional.of("A");

System.out.println(first.equals(second)); // true
~~~

Đây là đoạn minh họa cần import Optional. **equals** so sánh nội dung và cho true với hai Optional chứa String bằng nhau. Việc dùng **first == second** không phải cách kiểm tra nội dung hợp lệ về mặt ngữ nghĩa.

**Một phân biệt khác:** Optional bản thân không có setter để thay đổi trạng thái có/không có sau khi tạo; nhưng **giá trị T bên trong có thể là đối tượng mutable**. Chứa một List mutable trong Optional **không** khiến List đó bất biến hoặc thread-safe.

## 12. Primitive Optional và chi phí boxing

Khi thao tác với giá trị primitive, JDK có:

- **OptionalInt** — có hoặc không có int.
- **OptionalLong** — có hoặc không có long.
- **OptionalDouble** — có hoặc không có double.

Ví dụ:

~~~java
OptionalInt maybeMax = IntStream.of(2, 5, 1).max();
System.out.println(maybeMax.orElse(-1)); // 5
~~~

Đây là đoạn minh họa với import **java.util.OptionalInt** và **java.util.stream.IntStream**. Nếu stream rỗng, **max()** trả OptionalInt rỗng. **orElse(-1)** là fallback của ví dụ, phải được chọn có chủ ý: nếu -1 cũng là một dữ liệu hợp lệ, fallback có thể gây nhầm.

Các kiểu primitive Optional giúp tránh boxing của **Integer**, **Long**, **Double** trong những API tương ứng. Nhưng **API của OptionalInt/Long/Double không hoàn toàn giống Optional<T>**, nên không nên giả định chúng có mọi phương thức **map/flatMap** như Optional<T>.

**Không tối ưu trước khi đo:** chọn cách biểu diễn vừa đúng ý nghĩa vừa tương thích dữ liệu; chỉ xem boxing/performance khi workload thực sự cần.

## 13. Ranh giới tương tác: framework, thư viện và hợp đồng public

Khi đưa Optional vào API nhiều module sử dụng, cân nhắc:

1. **Khả năng đọc hiểu của caller:** Optional thể hiện absence; tài liệu phải nói rõ thế nào là “không có”.
2. **Java và thư viện:** một số framework hỗ trợ Optional ở return type (chẳng hạn repository API), một số binder, ORM, serializer hoặc công cụ tạo schema cần cấu hình riêng. Không giả định hỗ trợ đồng nhất cho field, setter, constructor param và DTO.
3. **Khả năng tương thích:** đổi phương thức từ **T get(...)** sang **Optional<T> get(...)** là thay đổi chữ ký gây ảnh hưởng caller; cần quản lý migration/versioning.
4. **Tương tác với null:** nhiều API Java cũ và thư viện bên thứ ba vẫn trả null; **ofNullable** hữu ích ở ranh giới, nhưng phải giữ đúng nghĩa “không có”.
5. **Chi phí phân bổ object:** tránh tạo Optional ở những vòng lặp nóng mà không có ý nghĩa absence; quan trọng hơn là chọn API rõ nghĩa và đo lường trước khi tối ưu.
6. **Domain modeling:** nếu dữ liệu có hơn hai trạng thái nghiệp vụ, hãy cân nhắc **enum/record/sealed hierarchy/Result**, thay vì ép mọi thứ vào Optional.

**Không dùng Optional ở vị trí mà dữ liệu có thể chứa null** và coi Optional là nơi lưu một null có ý nghĩa riêng: Optional không thể chứa null. **Optional.ofNullable(null)** luôn rỗng. Nếu cần phân biệt “chưa cung cấp” với “đã cung cấp rõ ràng giá trị null”, hai trạng thái đó đòi hỏi một mô hình dữ liệu khác.

## 14. So sánh các lựa chọn API

| Nhu cầu | Lựa chọn thường phù hợp | Vì sao |
| --- | --- | --- |
| Tra cứu một thực thể có thể không tồn tại | **Optional<User> findById(...)** | Absence hợp lệ được nêu ở return type |
| Luôn phải có thực thể, thiếu là vi phạm | **User requireById(...)** + exception | Hợp đồng bắt buộc rõ hơn |
| Tìm nhiều phần tử | **List<User> findAll(...)** | Danh sách rỗng diễn đạt không có phần tử |
| Trả giá trị số có thể thiếu | **OptionalInt/Long/Double** nếu API phù hợp | Tránh boxing cho primitive |
| Biết thành công/thất bại kèm lý do | **Result/record/sealed type** | Optional không chứa chi tiết lỗi |
| Dữ liệu lưu trong entity/DTO | Field theo quy ước của domain/framework | Optional field có thể tăng độ phức tạp tương tác |
| Một tham số tùy chọn | Overload, options/builder hoặc contract phù hợp | Tránh buộc mọi caller bọc Optional |
| Biến đổi Optional đã có | **map/flatMap/filter** | Tránh get/check lặp lại |
| Cần fallback tốn chi phí | **orElseGet** | Chỉ tính fallback khi rỗng |
| Cần lỗi rõ khi giá trị bắt buộc | **orElseThrow(supplier)** | Thông báo điều kiện vi phạm đúng ranh giới |

Đây là các **quy tắc hướng dẫn**, không phải cấm tuyệt đối. Quyết định cụ thể phải dựa trên hợp đồng, framework và chi phí duy trì API.

## 15. Kiểm thử Optional đúng theo hợp đồng

Một bộ kiểm thử nhỏ cho phương thức trả Optional nên bao phủ **ba nhóm**:

**Có kết quả:**
- Với ID tồn tại, **isPresent()** là true.
- **map(...)** trả nội dung đúng.
- **orElseGet(...)** không gọi fallback đắt đỏ.

**Không có kết quả:**
- Với ID không tồn tại, **isEmpty()** là true.
- **orElse(...)** hoặc **orElseGet(...)** trả fallback đúng.
- **orElseThrow(...)** ném loại exception và thông điệp mong đợi nếu caller yêu cầu dữ liệu bắt buộc.

**Dữ liệu và hệ thống bất thường:**
- Input null được xử lý theo tiền điều kiện đã công bố (trong ví dụ findUser, ném NullPointerException do requireNonNull).
- Lỗi cơ sở dữ liệu không bị chuyển sai thành Optional.empty().
- Mapper hoặc predicate ném lỗi thì lỗi không bị Optional “nuốt” tự động.
- Phương thức đã công bố trả Optional không bao giờ trả null khi hoàn tất bình thường.

Ví dụ kiểm tra hành vi fallback:

~~~java
AtomicInteger calls = new AtomicInteger();
Optional<String> present = Optional.of("value");

String result = present.orElseGet(() -> {
    calls.incrementAndGet();
    return "fallback";
});

System.out.println(result);      // value
System.out.println(calls.get()); // 0
~~~

Đây là **đoạn minh họa** với import **java.util.Optional** và **java.util.concurrent.atomic.AtomicInteger**. Nó cho thấy supplier không được gọi khi Optional có giá trị. Trong unit test thực, nên dùng assertions để tự động kiểm tra các điều kiện trên.

### 15.1. Các câu hỏi phân biệt Optional với validation

Giả sử API nhận `age` hoặc chuỗi mã:

- **Không có người dùng theo ID hợp lệ:** Optional.empty() có thể đúng.
- **ID null hoặc sai định dạng:** cần quy tắc validation riêng; không mặc định biến mọi lỗi input thành empty().
- **Dữ liệu người dùng tồn tại nhưng thiếu email:** có thể biểu diễn email không có ở một API trả Optional<String> phù hợp.
- **Không thể truy cập repository:** cần báo lỗi kết nối/ủy quyền theo hợp đồng; không phải “không tìm thấy”.

Một API tốt giúp caller phân biệt những trạng thái này, tránh xem việc trả empty như giải pháp cho mọi ca thất bại.

## 16. Bài tập

### Bài 1: Thiết kế return type

Với ba phương thức: tìm user theo ID, lấy tất cả user theo nhóm và lấy user bắt buộc cho transaction, chọn giữa **Optional<User>**, **List<User>** và **User + exception**. Giải thích liệu vắng mặt có phải kết quả hợp lệ của mỗi phương thức không.

### Bài 2: Bỏ get() không cần thiết

Chuyển:

~~~java
Optional<User> user = findUser(id);
if (user.isPresent()) {
    return user.get().name();
}
return "Khách";
~~~

Đây là đoạn minh họa nằm trong một phương thức trả String. Hãy dùng **map** và **orElse** để diễn đạt cùng logic ngắn gọn hơn, rồi kiểm thử cả ID tồn tại lẫn không tồn tại.

### Bài 3: Dự đoán orElse và orElseGet

Tạo **Optional.of("ok")** rồi truyền một lời gọi có log vào **orElse**, sau đó truyền Supplier tương ứng vào **orElseGet**. Phần nào gọi fallback? Khi đổi thành Optional.empty(), hành vi khác ra sao?

### Bài 4: map hay flatMap?

Cho **Optional<Customer>** và hàm **Optional<Address> addressOf(Customer)**, hãy viết hai cách dùng map/flatMap và xác định kiểu kết quả của mỗi cách. Vì sao flatMap thường thuận tiện hơn khi muốn tiếp tục lấy **Address.city()**?

### Bài 5: Tránh lạm dụng Optional<List<T>>

Một API **searchProducts(query)** trả **Optional<List<Product>>** nhưng luôn dùng Optional.empty() khi tìm không thấy sản phẩm. Hãy thiết kế lại với **List<Product>**, trả **List.of()** khi không tìm thấy và chỉ dùng Optional nếu thực sự có ý nghĩa phân biệt hai loại absence.

### Bài 6: Mô hình hóa lỗi

Một API truy vấn giá hàng hóa có thể **không tìm thấy sản phẩm**, **không có quyền đọc**, hoặc **mất kết nối**. Hãy xác định trạng thái nào có thể trả Optional.empty(), trạng thái nào cần exception hoặc kiểu Result giàu thông tin. Đừng lẫn “không tìm thấy” với “không thể truy vấn”.

## 17. Checklist trước khi đưa Optional vào API

1. **Có một giá trị trả về có thể vắng mặt hợp lệ không?** Nếu không, có thể không cần Optional.
2. **Không tìm thấy khác lỗi hệ thống chứ?** Giữ nguyên thông tin lỗi.
3. **Có thể trả collection rỗng thay vì Optional<Collection> không?** Nếu hai trạng thái không khác nghĩa, dùng collection rỗng.
4. **Đang đặt Optional ở return type hay vô thức đưa vào field/parameter?** Cân nhắc khả năng dùng với serializer, ORM và caller.
5. **Có dùng get() không kiểm tra hoặc orElse(null) không?** Xem lại hợp đồng của caller.
6. **Fallback có side effect/tốn chi phí không?** Cân nhắc orElseGet thay vì orElse.
7. **Mapper đã trả Optional chưa?** Dùng flatMap để tránh Optional lồng nhau.
8. **Cần giải thích lý do thất bại không?** Optional chỉ có mặt/vắng mặt; có thể cần kiểu dữ liệu khác.
9. **Đang dựa vào identity hoặc monitor của Optional không?** Tránh vì đây là value-based class.
10. **Có kiểm thử cả nhánh present, empty và lỗi không?** Không dùng mỗi ca thành công để kết luận API đúng.

## 18. Ghi nhớ

**Optional<T> nên được hiểu trước hết là công cụ mô tả sự vắng mặt hợp lệ ở giá trị trả về của phương thức.** Nó giúp caller chọn cách tiếp tục: map, flatMap, filter, fallback, bỏ qua hay chủ động ném exception. Các factory **of**, **ofNullable** và **empty** giúp phân biệt giá trị có, nullable từ nguồn ngoài và không có giá trị.

**Không nên coi Optional là lớp vỏ mặc định cho field, tham số, mọi kết quả collection hoặc mọi biến local.** Những chỗ đó có thể làm tăng chi phí tương tác, gây rắc rối serialization/ORM và che mất bất biến dữ liệu. Một Optional rỗng cũng không phải cách biểu diễn mọi loại lỗi.

Một câu để tự kiểm tra thiết kế: **“Nếu phương thức không trả được T, đó là vắng mặt hợp lệ mà caller có quyền xử lý, hay là lỗi/trạng thái nghiệp vụ cần mô tả rõ hơn?”** Trả lời được câu hỏi này sẽ giúp dùng Optional đúng trọng tâm và tránh lạm dụng.