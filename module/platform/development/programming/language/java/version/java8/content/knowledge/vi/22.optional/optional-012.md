# Kiểm thử chuỗi chuyển đổi có dữ liệu vắng mặt với Optional (Java 8)

Trong ứng dụng thực tế, một chuỗi chuyển đổi hiếm khi luôn có đủ dữ liệu. Người dùng có thể không tồn tại, người dùng có thể chưa có hồ sơ, hồ sơ chưa có địa chỉ, địa chỉ không có tên thành phố, hoặc tên thành phố chỉ chứa khoảng trắng. Khi dữ liệu vắng mặt ở bất kỳ bước nào, chương trình cần trả **kết quả đúng theo hợp đồng** thay vì ném `NullPointerException` ngoài ý muốn.

`Optional<T>` của Java 8 giúp mô hình hóa giá trị **có thể có hoặc không có** và phối hợp `map`, `flatMap`, `filter`, `orElse`, `orElseGet`, `orElseThrow` thành pipeline dễ đọc. Tuy nhiên, dùng Optional chưa đủ: phải **kiểm thử từng điểm có thể vắng mặt, đường đi có dữ liệu, giá trị không hợp lệ, fallback và hành vi của mapper**. Đây là chủ đề chính của bài.

Các ví dụ bên dưới dùng **API Java 8 vẫn được hỗ trợ hiện nay**, biên dịch ở mức `--release 8`; những phương thức chỉ có trên phiên bản Java mới hơn không được đưa vào ví dụ chạy độc lập.

## 1. Mục tiêu kiểm thử: chứng minh cả dữ liệu có mặt và vắng mặt

Giả sử ứng dụng cần hiển thị thành phố từ quan hệ:

```text
userId
  │
  ▼
find user (có thể không tồn tại)
  │
  ▼
User.profile (có thể null)
  │
  ▼
Profile.address (có thể null)
  │
  ▼
Address.city (có thể null hoặc trống)
  │
  ▼
trim → loại chuỗi trống → uppercase
  │
  ▼
"DA NANG" hoặc "UNKNOWN"
```

Một đường chạy thành công không đủ để kiểm tra chuỗi này. Bộ test tối thiểu phải trả lời:

- Không có user: các mapper ở phía sau có bị gọi nhầm không?
- Có user nhưng không có profile: có trả fallback thay vì NPE không?
- Có profile nhưng không có address: `flatMap` có tiếp tục đúng không?
- Có address nhưng city là `null`: `map` xử lý thế nào?
- City chỉ có khoảng trắng: `filter` có loại được không?
- City hợp lệ có khoảng trắng: có chuẩn hóa đúng không?
- City hợp lệ bình thường: đường đi có dữ liệu có bị làm mất không?
- Fallback có được gọi **đúng lúc**, đặc biệt khi việc tính fallback tốn kém hoặc có side effect?
- Lỗi thực sự có bị nhầm thành "dữ liệu vắng mặt" hay không?

**Nguyên tắc:** mỗi điểm có thể sinh ra `Optional.empty()` phải có một trường hợp kiểm thử tương ứng, nhưng cũng phải có đường thành công hoàn chỉnh để biết chuỗi không luôn trả empty.

## 2. Hiểu chính xác Optional trước khi viết test

`Optional<T>` biểu diễn **có đúng một giá trị không-null hoặc không có giá trị**. Đây không phải danh sách và cũng không phải bộ chứa cho thông báo lỗi.

| API Java 8 | Khi Optional đang có giá trị | Khi Optional rỗng |
| --- | --- | --- |
| `Optional.of(x)` | Tạo Optional chứa `x` nếu `x != null` | Truyền null vào `of` ném `NullPointerException` |
| `Optional.ofNullable(x)` | Chứa `x` nếu không null | Tạo Optional rỗng khi `x == null` |
| `Optional.empty()` | Không áp dụng | Tạo Optional rỗng |
| `map(fn)` | Gọi hàm chuyển đổi, đóng gói kết quả bằng quy tắc giống `ofNullable` | Không gọi `fn`, giữ trạng thái rỗng |
| `flatMap(fn)` | Gọi hàm trả về **Optional khác**, tránh lồng `Optional<Optional<U>>` | Không gọi `fn`, giữ rỗng |
| `filter(predicate)` | Giữ giá trị nếu điều kiện đúng, ngược lại thành rỗng | Không gọi predicate, giữ rỗng |
| `orElse(value)` | Trả giá trị hiện tại | Trả đối số `value` |
| `orElseGet(supplier)` | Trả giá trị hiện tại, **không gọi supplier** | Gọi supplier để lấy fallback |
| `orElseThrow(supplier)` | Trả giá trị hiện tại | Gọi supplier tạo exception rồi ném |
| `ifPresent(consumer)` | Gọi consumer | Không gọi consumer |
| `isPresent()` | `true` | `false` |

Từ đây phát sinh các chi tiết rất quan trọng khi kiểm thử:

1. **`map` có thể trả về null:** `Optional.of("x").map(s -> null)` cho `Optional.empty()`, không tự ném NPE vì kết quả mapper null.
2. **`flatMap` không được trả về null:** mapper phải trả **một đối tượng Optional không null**. `Optional.of("x").flatMap(s -> null)` ném `NullPointerException`.
3. **`orElse` đánh giá đối số theo ngữ nghĩa gọi hàm Java:** nếu viết `orElse(expensive())` thì `expensive()` **vẫn chạy** trước lời gọi `orElse`, kể cả Optional có giá trị.
4. **`orElseGet` chỉ gọi supplier khi empty**, thích hợp cho fallback tốn kém hoặc có side effect.
5. **Không gọi `get()` vô điều kiện:** `Optional.empty().get()` ném `NoSuchElementException`. Nên dùng `orElseThrow(supplier)` khi "không tìm thấy" thực sự là lỗi cần báo.
6. **Không dùng so sánh tham chiếu `==` giữa các Optional** để kiểm tra rỗng; hãy dùng `isPresent()`, `equals` hoặc giá trị kết quả. `Optional` là value-based class, không nên dựa vào danh tính đối tượng.

Các quy tắc trên vẫn đúng khi Optional nằm giữa một chuỗi chuyển đổi dài. Kiểm thử phải dựa trên **đặc tả của từng bước**, không dựa vào việc một ví dụ may mắn không ném exception.

## 3. Thiết kế pipeline sao cho mọi điểm vắng mặt được xử lý tường minh

Một cách triển khai phù hợp ở ranh giới đọc dữ liệu là bắt đầu từ `Optional.ofNullable(...)` và để các getter có thể vắng mặt trả về `Optional<...>`:

```java
// Minh họa phụ thuộc các lớp User, Profile, Address ở mục 4.
String label = Optional.ofNullable(USERS.get(id))
    .flatMap(User::getProfile)
    .flatMap(Profile::getAddress)
    .map(Address::getCity)
    .map(String::trim)
    .filter(city -> !city.isEmpty())
    .map(city -> city.toUpperCase(Locale.ROOT))
    .orElse("UNKNOWN");
```

Diễn giải đúng thứ tự:

- `USERS.get(id)` có thể trả null, nên dùng `ofNullable` ở biên.
- `User::getProfile` trả `Optional<Profile>`, nên dùng **`flatMap`** để không tạo `Optional<Optional<Profile>>`.
- `Profile::getAddress` trả `Optional<Address>`, tiếp tục dùng **`flatMap`**.
- `Address::getCity` trả `String` (có thể null), nên dùng **`map`**. Nếu city null, kết quả chuyển thành Optional rỗng.
- `String::trim` chỉ chạy khi có city; nếu vắng mặt, không có NPE khi thực hiện trim.
- `filter(city -> !city.isEmpty())` từ chối chuỗi rỗng sau trim. Ký tự whitespace Unicode có quy tắc riêng; với yêu cầu nhận diện mọi loại khoảng trắng, phải xác định chính sách chuẩn hóa phù hợp, không coi `trim` là bộ phân tích Unicode toàn diện.
- `toUpperCase(Locale.ROOT)` tạo định dạng nhất quán không phụ thuộc locale mặc định của hệ điều hành.
- `orElse("UNKNOWN")` là fallback cuối; với hằng chuỗi rẻ tiền, dùng `orElse` là hợp lý.

**Không nhầm một pipeline không ném NPE với pipeline đúng nghiệp vụ:** nếu address mất nhưng người dùng yêu cầu thông báo "chưa có địa chỉ" khác với "không có user", một fallback chung `"UNKNOWN"` sẽ làm mất lý do vắng mặt. Khi đó cần mô hình kết quả chi tiết hơn, chứ không ép mọi nhánh thành cùng một Optional.empty.

## 4. Ví dụ chạy được: kiểm thử vắng mặt tại từng bước

Chương trình dưới đây tạo một domain nhỏ `User → Profile → Address → city` và thực thi **bảng test bảy trường hợp**. Mỗi ô dữ liệu giả lập một kiểu thiếu thông tin, không cần database hay thư viện ngoài JDK.

Tệp **`OptionalChainTest.java`**:

```java
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;

public class OptionalChainTest {
    static final class Address {
        private final String city;

        Address(String city) { this.city = city; }

        String getCity() { return city; }
    }

    static final class Profile {
        private final Address address;

        Profile(Address address) { this.address = address; }

        Optional<Address> getAddress() {
            return Optional.ofNullable(address);
        }
    }

    static final class User {
        private final Profile profile;

        User(Profile profile) { this.profile = profile; }

        Optional<Profile> getProfile() {
            return Optional.ofNullable(profile);
        }
    }

    static final Map<String, User> USERS = new HashMap<>();

    static {
        USERS.put("no-profile", new User(null));
        USERS.put("no-address", new User(new Profile(null)));
        USERS.put("null-city",
            new User(new Profile(new Address(null))));
        USERS.put("blank-city",
            new User(new Profile(new Address("   "))));
        USERS.put("ok",
            new User(new Profile(new Address("  da nang  "))));
        USERS.put("exact",
            new User(new Profile(new Address("hanoi"))));
    }

    static String cityLabel(String id) {
        return Optional.ofNullable(USERS.get(id))
            .flatMap(User::getProfile)
            .flatMap(Profile::getAddress)
            .map(Address::getCity)
            .map(String::trim)
            .filter(city -> !city.isEmpty())
            .map(city -> city.toUpperCase(Locale.ROOT))
            .orElse("UNKNOWN");
    }

    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        String[] cases = {
            "absent", "no-profile", "no-address",
            "null-city", "blank-city", "ok", "exact"
        };

        String[] expected = {
            "UNKNOWN", "UNKNOWN", "UNKNOWN",
            "UNKNOWN", "UNKNOWN", "DA NANG", "HANOI"
        };

        for (int i = 0; i < cases.length; i++) {
            String actual = cityLabel(cases[i]);
            check(expected[i].equals(actual), "case=" + cases[i]);
            System.out.println(cases[i] + " -> " + actual);
        }

        AtomicInteger calls = new AtomicInteger();
        String result = Optional.<User>empty()
            .flatMap(user -> {
                calls.incrementAndGet();
                return user.getProfile();
            })
            .map(profile -> "unreachable")
            .orElse("UNKNOWN");

        check("UNKNOWN".equals(result) && calls.get() == 0,
              "empty chain should skip mapper");

        System.out.println("emptyMapperCalls=" + calls.get());
        System.out.println("PASS");
    }
}
```

Biên dịch/chạy trên Java 8 trở lên:

```bash
javac -encoding UTF-8 OptionalChainTest.java
java OptionalChainTest
```

Kết quả đã kiểm chứng:

```text
absent -> UNKNOWN
no-profile -> UNKNOWN
no-address -> UNKNOWN
null-city -> UNKNOWN
blank-city -> UNKNOWN
ok -> DA NANG
exact -> HANOI
emptyMapperCalls=0
PASS
```

### Đọc kết quả theo ma trận

| Trường hợp | Bước khiến dữ liệu vắng mặt | Kết quả mong đợi |
| --- | --- | --- |
| `absent` | `USERS.get(id) == null`, `ofNullable` tạo empty | `UNKNOWN` |
| `no-profile` | `User::getProfile` trả empty | `UNKNOWN` |
| `no-address` | `Profile::getAddress` trả empty | `UNKNOWN` |
| `null-city` | `Address::getCity` trả null, `map` biến thành empty | `UNKNOWN` |
| `blank-city` | `trim` thành `""`, `filter` loại | `UNKNOWN` |
| `ok` | Mọi bước có dữ liệu, trim và uppercase | `DA NANG` |
| `exact` | Giá trị hợp lệ không có khoảng trắng phụ | `HANOI` |

Dòng `emptyMapperCalls=0` còn chứng minh một tính chất khác: khi Optional đang empty, mapper **không được gọi**. Đây là phép kiểm soát side effect có chủ đích trong test. Trong code sản xuất, hãy giữ mapper thuần và không dựa vào side effect để tạo logic nghiệp vụ.

### Vì sao dùng so sánh expected thay vì chỉ in kết quả?

Một chương trình chỉ có `System.out.println` không tự báo sai khi kết quả đổi. Hàm `check(...)` ném `AssertionError` ngay khi khác expected. In `PASS` chỉ xảy ra sau khi **tất cả các trường hợp** vượt qua điều kiện.

Trong dự án thật, dùng framework kiểm thử như JUnit để chia các case thành bài kiểm tra độc lập, báo case thất bại và chạy tự động trong CI. Chương trình này dùng Java thuần để **chạy được mà không phụ thuộc build/test library**.

## 5. Một dữ liệu vắng mặt có thể lan qua cả chuỗi mà không gọi hàm phía sau

Giả sử một chuỗi gồm:

```text
Optional<User>
   .flatMap(getProfile)
   .flatMap(getAddress)
   .map(getCity)
   .map(trim)
   .filter(notBlank)
   .map(upperCase)
```

Khi một bước cho `Optional.empty()`, mọi `map`, `flatMap`, `filter` phía sau **không gọi mapper/predicate tương ứng**. Toàn bộ chuỗi tiếp tục trả empty cho đến bước cuối như `orElse`/`orElseGet`/`orElseThrow`.

Cách kiểm tra tốt:

1. Tạo Optional empty ngay trước bước cần test.
2. Truyền mapper có bộ đếm (test-only) và chạy pipeline.
3. Khẳng định bộ đếm bằng 0.
4. Khẳng định kết quả cuối là fallback hoặc empty theo hợp đồng.
5. Với Optional present, khẳng định mapper được gọi đúng số lần cần thiết và kết quả đúng.

Ví dụ trong chương trình mục 4:

```java
// Trích từ OptionalChainTest.java, không phải tệp độc lập.
AtomicInteger calls = new AtomicInteger();
String result = Optional.<User>empty()
    .flatMap(user -> {
        calls.incrementAndGet();
        return user.getProfile();
    })
    .map(profile -> "unreachable")
    .orElse("UNKNOWN");
```

Ta kiểm được `calls.get() == 0`. **Không cần chèn `null` dereference cố ý vào production mapper** để xem có NPE hay không; một bộ đếm có kiểm soát trong test biểu đạt rõ hơn và không làm hệ thống thực có hành vi không cần thiết.

## 6. map hay flatMap? Bài kiểm thử phải phân biệt kết quả lồng Optional

`map` nhận một hàm `T → U` và trả `Optional<U>`. Khi mapper đã trả `Optional<U>`, dùng `map` sẽ tạo cấu trúc **`Optional<Optional<U>>`**.

`flatMap` nhận hàm `T → Optional<U>` và trả **`Optional<U>`**. Nó không tạo Optional lồng nhau.

```java
// Minh họa khi đã có phương thức parsePositive(String).
Optional<Optional<Integer>> nested =
    Optional.of("8").map(OptionalParsingMatrixDemo::parsePositive);

Optional<Integer> flat =
    Optional.of("8").flatMap(OptionalParsingMatrixDemo::parsePositive);
```

Giá trị minh họa:

```text
nested=Optional[Optional[8]]
flat=Optional[8]
```

**Ca kiểm thử cần có:** dữ liệu hợp lệ, dữ liệu không hợp lệ trả empty, dữ liệu đầu vào empty khiến mapper không chạy, và mapper của `flatMap` trả **null không hợp lệ**. Không kiểm tra chỉ đường thành công rồi bỏ qua hợp đồng của mapper.

### map có thể trả null, flatMap phải trả Optional không null

Cần nhớ hai ví dụ có hành vi khác nhau:

```java
// map: null của mapper được chuyển thành Optional.empty().
Optional<String> a =
    Optional.of("abc").map(s -> (String) null);

// flatMap: mapper trả null là vi phạm hợp đồng.
Optional<String> b =
    Optional.of("abc")
        .flatMap(s -> (Optional<String>) null);
```

Đoạn thứ hai ném `NullPointerException`; biến `b` không nhận được giá trị. Đây **không phải một cách hợp lệ để biểu diễn thiếu dữ liệu**. Mapper dùng với `flatMap` phải trả `Optional.empty()` nếu không có giá trị, thay vì trả null.

Đừng viết:

```java
// SAI: getProfile đã trả Optional<Profile>.
Optional<Optional<Profile>> nestedProfile =
    Optional.of(user).map(User::getProfile);
```

trừ khi bạn thực sự muốn một Optional lồng nhau. Trong pipeline chuyển đổi nhiều tầng, phần lớn trường hợp cần `flatMap(User::getProfile)`.

## 7. Ví dụ chạy được: kiểm thử chuyển đổi có thể thất bại

Một tình huống khác là input có thể bị thiếu, là chuỗi rỗng hoặc không có giá trị hợp lệ để chuyển đổi. Từ `String` sang số nguyên dương, ta thiết kế quy tắc minh họa:

- Input là null → Optional empty.
- Input có thể parse thành số nguyên dương → Optional chứa số.
- Input bằng 0, âm, trống hoặc không phải số → Optional empty theo **chính sách ví dụ**.

**Cảnh báo ngữ nghĩa:** với bài toán thực tế, giá trị "không gửi" và "gửi sai định dạng" có thể cần hai loại lỗi khác nhau. Ở đây ta **chủ động chọn** chính sách coi cả hai là không nhận được số hợp lệ để minh họa `flatMap`. Không tự áp dụng chính sách gộp lỗi này cho API yêu cầu báo lỗi validation cụ thể.

Tệp **`OptionalParsingMatrixDemo.java`**:

```java
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;

public class OptionalParsingMatrixDemo {
    static Optional<Integer> parsePositive(String raw) {
        try {
            int value = Integer.parseInt(raw.trim());
            return value > 0
                ? Optional.of(value) : Optional.empty();
        } catch (NumberFormatException ex) {
            return Optional.empty();
        }
    }

    static Optional<Integer> convert(String raw) {
        return Optional.ofNullable(raw)
            .flatMap(OptionalParsingMatrixDemo::parsePositive);
    }

    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        String[] cases = {null, " 8 ", "0", "-4", "xyz", "  "};

        String[] expected = {
            "Optional.empty", "Optional[8]", "Optional.empty",
            "Optional.empty", "Optional.empty", "Optional.empty"
        };

        for (int i = 0; i < cases.length; i++) {
            Optional<Integer> actual = convert(cases[i]);
            check(expected[i].equals(actual.toString()),
                  "case=" + cases[i]);
            System.out.println("raw=" + cases[i] + " -> " + actual);
        }

        Optional<Optional<Integer>> nested =
            Optional.of("8")
                .map(OptionalParsingMatrixDemo::parsePositive);
        Optional<Integer> flat =
            Optional.of("8")
                .flatMap(OptionalParsingMatrixDemo::parsePositive);

        check("Optional[Optional[8]]".equals(nested.toString()),
              "nested");
        check(Optional.of(8).equals(flat), "flat");

        AtomicInteger parseCalls = new AtomicInteger();
        Optional<Integer> empty = Optional.<String>empty()
            .flatMap(s -> {
                parseCalls.incrementAndGet();
                return parsePositive(s);
            });

        check(!empty.isPresent() && parseCalls.get() == 0,
              "skip parser on absent source");

        System.out.println("nested=" + nested);
        System.out.println("flat=" + flat);
        System.out.println("emptyParseCalls=" + parseCalls.get());
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 OptionalParsingMatrixDemo.java
java OptionalParsingMatrixDemo
```

Kết quả đã kiểm chứng:

```text
raw=null -> Optional.empty
raw= 8  -> Optional[8]
raw=0 -> Optional.empty
raw=-4 -> Optional.empty
raw=xyz -> Optional.empty
raw=   -> Optional.empty
nested=Optional[Optional[8]]
flat=Optional[8]
emptyParseCalls=0
PASS
```

Trong ví dụ, `Optional.toString()` được dùng để **hiển thị và minh họa**. Với test thông thường, nên ưu tiên `Optional.equals` hoặc so sánh giá trị đã được mở bằng fallback thay vì phụ thuộc vào biểu diễn chuỗi. Ví dụ:

```java
// Trích trong bối cảnh convert(String) đã được định nghĩa.
if (!Optional.of(8).equals(convert(" 8 "))) {
    throw new AssertionError("positive parse failed");
}
if (convert("xyz").isPresent()) {
    throw new AssertionError("invalid number should be rejected");
}
```

Điều này mô tả hợp đồng rõ hơn "chuỗi in phải đúng từng dấu ngoặc".

### Kiểm tra lỗi tràn số và trường hợp đặc biệt

`Integer.parseInt` có thể ném `NumberFormatException` khi chuỗi trông giống số nhưng vượt miền `int`. Trong chính sách ví dụ, exception được chuyển thành empty; nếu nghiệp vụ cần báo **"vượt giới hạn"**, phải trả kiểu kết quả chi tiết hơn.

Đừng giả định `trim()` xử lý mọi kiểu khoảng trắng Unicode. Với yêu cầu quốc tế hóa, cần test khoảng trắng Unicode và lựa chọn API/chiến lược chuẩn hóa phù hợp phiên bản Java mục tiêu. Đối với số tiền, mã định danh và dữ liệu có tính pháp lý, cách phân biệt **thiếu, sai và hợp lệ** thường quan trọng hơn tiện ích của Optional.

## 8. Kiểm thử fallback: orElse và orElseGet không có cùng chi phí

Đây là lỗi khó thấy vì **kết quả trả về có thể giống nhau**, nhưng side effect hoặc chi phí tính toán khác nhau.

So sánh:

```java
// Trong ngữ cảnh present và generate(...) đã được định nghĩa.
String a = present.orElse(generate(counter));
String b = present.orElseGet(() -> generate(counter));
```

- Ở `orElse(generate(counter))`, Java tính đối số `generate(counter)` **trước khi gọi** `orElse`. Counter tăng kể cả Optional đang present.
- Ở `orElseGet(() -> generate(counter))`, ta truyền **Supplier**, và Supplier chỉ chạy nếu Optional empty.
- Với fallback hằng như `orElse("UNKNOWN")`, không có tính toán đáng kể nên `orElse` vẫn đúng và dễ đọc.

Một test chỉ khẳng định `a.equals("READY")` và `b.equals("READY")` sẽ **bỏ sót khác biệt trên**. Vì vậy cần test số lần gọi fallback khi present và empty.

## 9. Ví dụ chạy được: fallback, exception và null mapper

Tệp **`OptionalFallbackTest.java`**:

```java
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;

public class OptionalFallbackTest {
    static String generate(AtomicInteger counter) {
        counter.incrementAndGet();
        return "GENERATED";
    }

    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        Optional<String> present = Optional.of("READY");
        AtomicInteger eagerCalls = new AtomicInteger();
        AtomicInteger lazyCalls = new AtomicInteger();

        String eager = present.orElse(generate(eagerCalls));
        String lazy = present.orElseGet(
            () -> generate(lazyCalls));

        check("READY".equals(eager) && eagerCalls.get() == 1,
              "orElse evaluates argument eagerly");
        check("READY".equals(lazy) && lazyCalls.get() == 0,
              "orElseGet supplier must be lazy");

        AtomicInteger emptyCalls = new AtomicInteger();
        String missing = Optional.<String>empty()
            .orElseGet(() -> generate(emptyCalls));

        check("GENERATED".equals(missing)
            && emptyCalls.get() == 1, "missing fallback");

        boolean exceptionCaught = false;
        try {
            Optional.<String>empty().orElseThrow(
                () -> new IllegalStateException("missing value"));
        } catch (IllegalStateException e) {
            exceptionCaught = "missing value".equals(e.getMessage());
        }
        check(exceptionCaught, "expected exception");

        boolean ofNullThrows = false;
        try {
            Optional.of((String) null);
        } catch (NullPointerException e) {
            ofNullThrows = true;
        }
        check(ofNullThrows, "of(null) must throw");

        check(!Optional.ofNullable((String) null).isPresent(),
              "ofNullable null should be empty");

        Optional<String> nullMapped =
            Optional.of("abc").map(s -> (String) null);
        check(!nullMapped.isPresent(),
              "map returning null produces empty");

        boolean flatMapNullThrows = false;
        try {
            Optional.of("abc")
                .flatMap(s -> (Optional<String>) null);
        } catch (NullPointerException e) {
            flatMapNullThrows = true;
        }
        check(flatMapNullThrows,
              "flatMap mapper must return non-null Optional");

        System.out.println("eager=" + eager +
                           ", calls=" + eagerCalls.get());
        System.out.println("lazy=" + lazy +
                           ", calls=" + lazyCalls.get());
        System.out.println("missing=" + missing +
                           ", calls=" + emptyCalls.get());
        System.out.println("orElseThrowCaught=" + exceptionCaught);
        System.out.println("ofNullThrows=" + ofNullThrows);
        System.out.println("nullMappedPresent=" + nullMapped.isPresent());
        System.out.println("flatMapNullThrows=" + flatMapNullThrows);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 OptionalFallbackTest.java
java OptionalFallbackTest
```

Kết quả chính xác:

```text
eager=READY, calls=1
lazy=READY, calls=0
missing=GENERATED, calls=1
orElseThrowCaught=true
ofNullThrows=true
nullMappedPresent=false
flatMapNullThrows=true
PASS
```

Các khẳng định thể hiện năm nhóm hành vi:

1. **Fallback eager:** `orElse(generate(...))` gọi hàm ngay cả khi đang có `"READY"`.
2. **Fallback lazy:** `orElseGet(...)` không gọi Supplier khi present và gọi đúng một lần khi empty.
3. **Báo thiếu dữ liệu bằng exception:** `orElseThrow(() -> new IllegalStateException(...))` ném exception có chủ đích khi empty.
4. **Tạo Optional từ null:** `Optional.of(null)` ném NPE, `Optional.ofNullable(null)` trả empty.
5. **Mapper trả null:** `map` tạo empty, còn `flatMap` ném NPE theo hợp đồng.

**Không đánh đồng các exception này với "dữ liệu vắng mặt":** `flatMap` ném NPE do mapper trả null là lỗi triển khai, không phải cách dùng Optional để báo không tìm thấy.

## 10. Thiết kế test matrix cho pipeline nhiều tầng

Không nhất thiết viết hàng trăm test độc lập bằng tay. Hãy dựng **bảng trạng thái** dựa trên điểm vắng mặt và mục tiêu đầu ra, sau đó chuyển mỗi dòng thành một test case.

Ví dụ với pipeline ở mục 4:

| Nhóm kiểm thử | Input/Fake cần dựng | Expected | Khẳng định bổ sung |
| --- | --- | --- | --- |
| Nguồn rỗng | Không có user cho ID | `UNKNOWN` | Getter sau đó không được chạy |
| Thiếu tầng 1 | User không có profile | `UNKNOWN` | Không truy cập address |
| Thiếu tầng 2 | Profile không có address | `UNKNOWN` | Không truy cập city |
| Thiếu giá trị cuối | Address có city = null | `UNKNOWN` | Không gọi `trim` |
| Giá trị sau chuẩn hóa thành empty | City = chuỗi toàn khoảng trắng | `UNKNOWN` | `filter` loại dữ liệu |
| Dữ liệu hợp lệ cần chuẩn hóa | City có khoảng trắng, chữ thường | `DA NANG` | Đúng kết quả cuối |
| Dữ liệu hợp lệ sẵn | City = `hanoi` | `HANOI` | Không bị biến thành empty |
| Lỗi mapper `flatMap` | Mapper trả null thay vì Optional | NPE | Thử ngoại lệ đúng loại |
| Mapper `map` trả null | Mapper trả null | Empty | Không ném NPE ở bước map |
| Fallback khi present | Optional có giá trị | Giá trị gốc | `orElseGet` không chạy |
| Fallback khi empty | Optional rỗng | Giá trị fallback | Supplier được gọi |
| orElseThrow khi empty | Optional rỗng | Exception nghiệp vụ | Đúng loại và thông báo |
| Chuỗi có giá trị nhưng filter không đạt | Present, predicate false | Empty/fallback | Không thực hiện map sau filter |
| Chuỗi có giá trị, filter đạt | Present, predicate true | Kết quả đã biến đổi | Bảo toàn đúng giá trị |

**Lưu ý khi xây fixture:** các trường hợp độc lập nên có dữ liệu riêng, không dùng chung đối tượng mutable rồi cho test này thay đổi đối tượng làm test khác vô tình sai. Với dữ liệu giả lập bằng `Map` như ví dụ, chọn giá trị bất biến ở từng case, hoặc reset fixture trước mỗi test trong framework test.

### Không dùng chỉ một đầu vào null để "chứng minh" toàn chuỗi

`Optional.ofNullable(null)` chuyển thành empty ngay tại đầu nguồn. Case đó **không kiểm tra** liệu `User::getProfile` hoặc `Profile::getAddress` xử lý thiếu dữ liệu đúng hay không, vì các getter này không được gọi. Do đó phải chủ động tạo **user present nhưng profile null**, và **profile present nhưng address null**.

Ngược lại, một case chỉ có mọi trường đều present không chứng minh bất kỳ nhánh vắng mặt nào. Hai cực "tất cả present" và "nguồn empty" chưa đủ cho chuỗi sâu.

## 11. Chuỗi chuyển đổi cần tách biệt "không tìm thấy", "không hợp lệ" và "lỗi hệ thống"

`Optional.empty()` thường phù hợp cho trường hợp **giá trị hợp lệ nhưng không tồn tại**. Nó không tự mang thông tin về lý do hoặc exception.

Ba tình huống sau có thể cần ba cách ứng xử khác nhau:

| Tình huống | Ý nghĩa | Hướng biểu diễn phù hợp |
| --- | --- | --- |
| Không tìm thấy user theo ID | Có thể là kết quả hợp lệ "không có" | `Optional<User>` |
| Người dùng nhập mã không đúng định dạng | Lỗi validation có thông báo cụ thể | Trả một result type có lỗi hoặc ném exception được định nghĩa ở tầng phù hợp |
| Database mất kết nối | Lỗi hạ tầng, không phải "user vắng mặt" | Truyền/bọc exception có ngữ cảnh, xử lý ở tầng phù hợp |

Nếu viết:

```java
// Mã phản ví dụ, không nên dùng khi exception biểu thị lỗi hệ thống.
try {
    return Optional.ofNullable(repository.findById(id));
} catch (Exception ex) {
    return Optional.empty(); // Đánh đồng lỗi DB với không tìm thấy!
}
```

thì test thành công ở trường hợp "not found" không phát hiện việc ứng dụng đang **giấu lỗi thật**. Hãy viết test cho exception của dependency và xác minh tầng xử lý có phản ứng đúng: log/propagate/translate theo hợp đồng, thay vì trả fallback giả thành công.

Trong ví dụ `parsePositive` ở mục 7, việc chuyển `NumberFormatException` thành empty là **quyết định minh họa rõ ràng**; nếu ứng dụng cần thông báo cho người dùng "sai định dạng", nên giữ kết quả validation có thông tin thay vì dùng Optional cho mọi trạng thái.

### Một fallback chung có thể che mất dữ liệu sai

`orElse("UNKNOWN")` có thể được dùng cho giao diện cần một nhãn chung, nhưng không nên sử dụng nó làm câu trả lời của mọi API nghiệp vụ nếu khách hàng của API cần biết **không có user**, **thiếu địa chỉ** hay **địa chỉ lỗi**. Kiểm thử fallback phải xuất phát từ **hợp đồng nghiệp vụ** trước, rồi mới đến việc chain Optional có chạy được hay không.

## 12. Các chiến lược kiểm thử giúp bắt lỗi khó thấy

### 12.1. Table-driven tests

Bảng `cases[]` và `expected[]` trong `OptionalChainTest` là cách viết test theo dữ liệu:

```java
// Minh họa dựa trên OptionalChainTest.java ở mục 4.
for (int i = 0; i < cases.length; i++) {
    String actual = cityLabel(cases[i]);
    check(expected[i].equals(actual), "case=" + cases[i]);
}
```

Trong JUnit, cách này có thể trở thành parameterized test với tên case rõ ràng. Luôn hiển thị case hỏng trong thông báo assertion để việc chẩn đoán không phụ thuộc vào thứ tự chạy.

### 12.2. Kiểm tra số lần gọi của callback

Để xác minh tính "không chạy bước sau nếu thiếu", dùng bộ đếm hoặc test double:

```java
// Ví dụ ngắn; chỉ dùng bộ đếm để kiểm tra hành vi.
AtomicInteger calls = new AtomicInteger();
Optional<String> result = Optional.<String>empty()
    .map(s -> {
        calls.incrementAndGet();
        return s.trim();
    });
if (calls.get() != 0 || result.isPresent()) {
    throw new AssertionError("mapper should be skipped");
}
```

Với `orElseGet`, test callback gọi 0 lần khi present và 1 lần khi empty. Với `orElseThrow`, nếu Optional present, Supplier tạo exception không được gọi; nếu empty, nó mới được đánh giá.

### 12.3. Kiểm tra loại exception và thông tin lỗi

Nếu hợp đồng yêu cầu ném exception khi thiếu dữ liệu, đừng chỉ khẳng định "có exception bất kỳ". Phải kiểm tra loại và thông điệp/cause cần thiết. Ví dụ chương trình `OptionalFallbackTest` chủ động kiểm `IllegalStateException` chứa `"missing value"`; nếu vô tình ném `NullPointerException`, test không được pass.

### 12.4. Thử giá trị ở biên

Tùy loại chuyển đổi, thêm:

- `null`, chuỗi rỗng, chỉ khoảng trắng, chuỗi có khoảng trắng đầu/cuối.
- Giá trị hợp lệ ở biên min/max, giá trị ngoài miền và dấu âm.
- Chữ hoa/chữ thường và locale nếu pipeline chuẩn hóa ký tự.
- Chuỗi vượt miền `Integer.parseInt`.
- Input có phần tử trùng hoặc nhiều record cùng khóa, nếu pipeline còn liên quan tới tìm kiếm.

Cần định nghĩa expected cho từng case. Không thêm một loạt dữ liệu random không có oracle rồi xem "không crash" là pass.

### 12.5. Kiểm tra kết quả lẫn hành vi

Với Optional, hai implementation có thể cho cùng String cuối nhưng chi phí rất khác nhau. Ví dụ `orElse(expensive())` và `orElseGet(() -> expensive())` thường trả cùng kết quả khi present, nhưng khác số lần tính expensive. Test tốt kiểm tra **cả nội dung kết quả lẫn việc callback có được gọi hay không**.

Ngược lại, không nên kiểm tra quá nhiều chi tiết nội bộ không thuộc contract. Nếu implementation đổi cách gọi phương thức nội bộ nhưng kết quả và những cam kết side-effect vẫn đúng, test không nên thất bại vô cớ.

## 13. Khi nào dùng Optional bên ngoài chuỗi chuyển đổi?

### Optional ở ranh giới trả giá trị

`Optional<T>` thích hợp với các phương thức trả về một giá trị **có thể không tồn tại một cách bình thường**:

```java
// Ví dụ kiểu chữ ký; phương thức thực tế do ứng dụng cung cấp.
Optional<User> findUserById(String id);
Optional<Address> findShippingAddress(User user);
```

Người gọi bắt buộc phải cân nhắc present/empty qua các phép chuyển đổi hoặc fallback. Tránh thiết kế **return null thay vì Optional.empty()** từ một phương thức có return type `Optional<T>`, vì `flatMap` yêu cầu mapper trả Optional không null.

### Optional không phải thay thế mọi kiểu nullable

Không tự động biến toàn bộ field của entity, tham số phương thức, record truyền mạng, JSON field hoặc tập hợp thành `Optional` mà không xem xét hợp đồng serialize, ORM và framework sử dụng. Java `Optional` chủ yếu hữu ích ở **kiểu trả về của phương thức có thể không có kết quả**; không có nghĩa mọi nơi trong mô hình dữ liệu đều cần lưu Optional.

Nếu có nhiều lý do thất bại, cần cấu trúc kết quả biểu diễn lý do rõ ràng. Với collection không có phần tử, **collection rỗng** thường dễ hiểu hơn `Optional<List<T>>` nếu "không có danh sách" và "danh sách rỗng" không cần phân biệt.

### Primitive Optional

Java 8 có `OptionalInt`, `OptionalLong`, `OptionalDouble` để biểu diễn giá trị số nguyên thủy có/không có mà không boxing giống `Optional<Integer>`. Tuy nhiên các kiểu đó không có đúng toàn bộ hệ phương thức như `Optional<T>` tổng quát, ví dụ không có `flatMap` kiểu generic trong Java 8. Khi viết test, đừng tự giả định mọi Optional có cùng API.

## 14. Anti-patterns trong code và test

| Anti-pattern | Vì sao nguy hiểm | Cách thay thế |
| --- | --- | --- |
| `Optional.of(nullable)` | NPE nếu nullable null | `Optional.ofNullable(nullable)` hoặc đảm bảo không-null thật |
| `optional.get()` trong pipeline không kiểm tra | `NoSuchElementException` khi empty | `map/flatMap/orElseThrow(supplier)` theo contract |
| `optional.isPresent() ? optional.get() : ...` ở mọi bước | Quay lại cây `if` sâu, dễ lặp logic | Dùng `map/flatMap/filter` khi biểu đạt được |
| Dùng `map` với hàm trả Optional | Tạo `Optional<Optional<U>>` | `flatMap` |
| Trả null từ mapper của `flatMap` | Ném NPE | Trả `Optional.empty()` |
| Nghĩ `map(fn)` với `fn` trả null sẽ giữ present | Thực tế thành empty | Viết test và xác định chính sách null |
| Dùng `orElse(expensive())` khi present nhiều | Hàm vẫn chạy, tốn tài nguyên/side effect | `orElseGet(() -> expensive())` |
| Chỉ test mọi trường đều có dữ liệu | Bỏ sót các nhánh empty ở giữa | Dựng case thiếu từng tầng |
| Chỉ test nguồn null | Getter sâu chưa từng được gọi | Test present ở tầng trước, missing ở tầng sau |
| Assert chỉ "không có exception" | Logic trả empty sai vẫn pass | Assert giá trị expected hoặc exception cụ thể |
| Bắt mọi exception rồi trả Optional.empty() | Giấu lỗi hệ thống thành thiếu dữ liệu | Tách not-found và exceptional outcome |
| So `Optional.empty() == other` | Value-based class không cam kết identity | `equals`, `isPresent`, kết quả cuối |
| Reuse mutable fixture giữa test | Case này ảnh hưởng case khác | Tạo fixture độc lập/reset rõ ràng |
| Dùng API Optional chỉ có từ Java mới hơn trong bài Java 8 | Không biên dịch với Java 8 | Dùng `isPresent` và `orElseThrow(Supplier)` của Java 8 |

Đặc biệt, các phương thức như `Optional.isEmpty()` hoặc `Optional.stream()` không phải API Java 8. Chúng tồn tại trong những phiên bản Java mới hơn nhưng **không dùng được khi biên dịch với `--release 8`**. Để bài này nhất quán với phạm vi Java 8, tất cả chương trình chạy độc lập chỉ sử dụng phương thức có từ Java 8, không phải vì API mới hơn đã lỗi thời.

## 15. Checklist đưa vào code review hoặc CI

Trước khi coi một pipeline Optional là đã kiểm thử đủ, đối chiếu:

- [ ] Có ít nhất **một ca thành công** với mọi tầng có giá trị.
- [ ] Có ca nguồn vắng mặt.
- [ ] Có ca **mỗi tầng có thể vắng mặt**, với tầng trước vẫn có dữ liệu.
- [ ] Có ca giá trị cuối là null và ca giá trị sau chuẩn hóa không hợp lệ nếu nghiệp vụ yêu cầu.
- [ ] Có expected rõ cho mỗi case; test ném AssertionError/failed assertion khi sai.
- [ ] Mapper của `flatMap` luôn trả Optional không null; có test bảo vệ contract nếu implementation phức tạp.
- [ ] Có test cho sự khác nhau giữa `map` null và `flatMap` null.
- [ ] Có test callback không chạy khi Optional empty.
- [ ] Có test fallback present/empty, bao gồm số lần gọi Supplier khi cần.
- [ ] Với `orElseThrow`, kiểm tra loại exception hoặc thông tin lỗi theo API contract.
- [ ] Phân biệt "không tìm thấy" và "đầu vào lỗi/hạ tầng lỗi"; không âm thầm nuốt mọi exception.
- [ ] Dữ liệu test không phụ thuộc trạng thái mutable của test khác.
- [ ] Không sử dụng API có phiên bản cao hơn Java 8 trong mục tiêu build Java 8.
- [ ] Test được chạy trong build/CI với cấu hình thực tế của dự án.

Danh sách này không phải yêu cầu phải tạo một test file riêng cho mỗi ô. Có thể dùng parameterized tests, bảng case hoặc helper tạo fixture; điều quan trọng là **mỗi nhánh có expected và dấu hiệu thất bại rõ ràng**.

## 16. Bài tập thực hành

**Bài tập 1 — thiếu mã bưu chính.** Có `Customer → ShippingAddress → zipCode`; mỗi tầng có thể vắng. Viết pipeline trả `"N/A"` nếu thiếu bất cứ tầng nào. Chuẩn hóa zipCode bằng `trim` trước khi nhận. Viết case: thiếu Customer, thiếu ShippingAddress, zipCode null, zipCode rỗng sau trim và zipCode hợp lệ.

**Gợi ý:** `Optional.ofNullable(customer).flatMap(Customer::getShippingAddress).map(ShippingAddress::getZipCode).map(String::trim).filter(s -> !s.isEmpty()).orElse("N/A")`, trong đó `getShippingAddress` được định nghĩa trả `Optional<ShippingAddress>`.

**Bài tập 2 — fallback tốn chi phí.** Có `Optional<String> cachedName` và phương thức `loadNameFromDatabase()`. Viết code chỉ gọi database khi cache rỗng. Tạo fake database đếm số lần gọi; test present = 0 lần, empty = 1 lần.

**Đáp án định hướng:** `cachedName.orElseGet(() -> loadNameFromDatabase())`. Không dùng `orElse(loadNameFromDatabase())` nếu muốn tránh gọi eager.

**Bài tập 3 — phân biệt "không tìm thấy" và "mã lỗi".** Hàm tìm mã sản phẩm nhận một chuỗi. Nếu chuỗi null là "không nhập"; nếu chuỗi sai định dạng là lỗi validation; nếu hợp lệ nhưng không có sản phẩm là "not found". Bạn có nên trả `Optional<Product>` cho **cả ba tình huống**?

**Đáp án:** không mặc định. Optional phù hợp với "not found", nhưng validation error cần được biểu diễn hoặc ném theo hợp đồng riêng. Test phải khẳng định thông báo lỗi đúng.

**Bài tập 4 — mapper trả null.** Cho:

```java
// Đoạn minh họa.
Optional<String> a =
    Optional.of("x").map(s -> (String) null);
```

Câu hỏi: a có present không? Nếu đổi map thành `flatMap(s -> (Optional<String>) null)` thì sao?

**Đáp án:** a là empty; đổi sang flatMap trả null sẽ ném `NullPointerException` vì vi phạm hợp đồng mapper.

**Bài tập 5 — bộ test hiện tại thiếu gì?** Một ứng dụng chỉ kiểm:

```text
findUser("valid-id") → có User, Profile, Address, city hợp lệ
findUser("absent")   → không có User
```

**Đáp án:** chưa kiểm tra trường hợp **User tồn tại nhưng Profile vắng**, **Profile có nhưng Address vắng**, **city null hoặc blank**, và hành vi fallback/callback. Các ca đó không thể suy ra chỉ từ hai đầu vào trên.

## 17. Câu hỏi tự kiểm tra

**1. Vì sao khi Optional empty, `.map(String::trim)` không gây NPE dù không có String?**  
Vì mapper không được gọi khi Optional rỗng; kết quả vẫn là Optional.empty.

**2. Có thể trả null từ hàm dùng trong `flatMap` để mô tả không tìm thấy không?**  
Không. Hàm phải trả `Optional.empty()` khi không có giá trị; trả null ném NPE.

**3. Trong `Optional.of("x").map(s -> null)`, kết quả là gì?**  
Optional.empty, vì `map` xử lý kết quả mapper null như giá trị không hiện diện.

**4. Vì sao `orElse(expensive())` có thể gây truy cập database thừa?**  
Vì đối số `expensive()` được tính trước lời gọi `orElse`, bất kể Optional present hay empty. `orElseGet` nhận Supplier và gọi chỉ khi empty.

**5. Tại sao chỉ test một user không tồn tại chưa chứng minh pipeline an toàn khi address vắng?**  
Vì khi user đã vắng, `flatMap(User::getProfile)` không chạy; nhánh có User và Profile nhưng thiếu Address vẫn chưa được kiểm.

**6. Có nên luôn chuyển `NumberFormatException` thành Optional.empty không?**  
Không. Chỉ làm nếu đó là hợp đồng nghiệp vụ chủ động chọn. Nếu cần báo lỗi validation, phải giữ thông tin lỗi.

**7. Nếu Optional có giá trị và gọi `orElseThrow(supplier)`, Supplier tạo exception có được chạy không?**  
Không. Nó chỉ chạy khi Optional rỗng.

**8. Dùng `Optional.equals` có tốt hơn so sánh tham chiếu `==` không?**  
Có. Optional là value-based; equality của giá trị/ngữ nghĩa hiện diện mới là thứ cần kiểm.

## Tài liệu chính thức

- [Java SE 8 — Optional](https://docs.oracle.com/javase/8/docs/api/java/util/Optional.html): `of`, `ofNullable`, `empty`, `map`, `flatMap`, `filter`, `orElse`, `orElseGet`, `orElseThrow(Supplier)`, `ifPresent` và `isPresent`.
- [Java SE 8 — java.util.function](https://docs.oracle.com/javase/8/docs/api/java/util/function/package-summary.html): `Function`, `Predicate`, `Supplier`, `Consumer` dùng trong chuỗi chuyển đổi.
- [Java SE 8 — Objects](https://docs.oracle.com/javase/8/docs/api/java/util/Objects.html): nguyên tắc kiểm tra non-null và phương thức hỗ trợ.
- [Java SE 8 — Integer.parseInt](https://docs.oracle.com/javase/8/docs/api/java/lang/Integer.html#parseInt-java.lang.String-): chuyển chuỗi sang số nguyên và `NumberFormatException`.

**Ghi nhớ:** kiểm thử Optional tốt là kiểm thử **dòng dữ liệu và ranh giới vắng mặt**. Hãy tạo dữ liệu thiếu ở từng tầng, khẳng định callback phía sau bị bỏ qua đúng lúc, phân biệt `map` với `flatMap`, kiểm tra fallback eager/lazy, và không dùng `Optional.empty()` để che mọi loại lỗi. Một chuỗi chuyển đổi chỉ đáng tin khi cả đường thành công lẫn từng nhánh dữ liệu vắng mặt đều có expected rõ ràng.