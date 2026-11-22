# Optional.empty(), Optional.of() và Optional.ofNullable() trong Java

## Mục tiêu

Sau bài học, bạn sẽ:

1. Nắm rõ Optional<T> biểu diễn sự **có hoặc không có giá trị non-null**.
2. Phân biệt chính xác ba cách tạo Optional: empty(), of(value) và ofNullable(value).
3. Dự đoán hành vi với null, chuỗi rỗng, chuỗi trắng, số 0 và false.
4. Chọn factory phù hợp tại ranh giới phương thức hoặc API có thể không trả dữ liệu.
5. Xử lý kết quả bằng isEmpty, isPresent, map, filter, orElse, orElseGet và orElseThrow mà không lạm dụng get().
6. Tránh lỗi trả null từ một hàm đã khai báo Optional<T>, lỗi suy luận kiểu generic và lỗi so sánh tham chiếu.
7. Biên dịch, chạy và kiểm chứng ví dụ Java 17+ bằng đầu ra cụ thể.

**Phiên bản và Special Note:** Optional và ba factory method này có từ Java 8, **vẫn còn áp dụng** trong Java hiện đại. Bài chỉ trình bày API và cách dùng còn được hỗ trợ hiện nay; những phương thức bổ sung từ Java 9, 10, 11 và 16 đều được ghi rõ khi xuất hiện.

## 1. Optional là gì?

Optional<T> trong java.util là một container có **tối đa một** giá trị kiểu T. Nếu giá trị xuất hiện, nó phải **khác null**. Nếu không có, Optional ở trạng thái empty.

~~~text
Optional<String>
  ├── present -> giá trị "Java" (non-null)
  └── empty   -> không chứa giá trị nào
~~~

Optional thường hữu ích với phương thức **có thể không tìm thấy kết quả**. Ví dụ, thay vì trả null và buộc người gọi tự suy luận, hàm tìm kiếm có thể trả Optional<User>. Người gọi sẽ thấy rõ cần xử lý cả trường hợp present lẫn empty.

Ba tình huống dưới đây khác nhau:

| Biểu thức | Trạng thái |
|---|---|
| Optional.empty() | Object Optional hợp lệ, không chứa giá trị |
| Optional.of("Java") | Object Optional hợp lệ, chứa "Java" |
| Optional<String> variable = null | Chính **biến Optional** đang null, vi phạm kỳ vọng thiết kế |

Phương thức đã khai báo trả Optional<T> **nên luôn trả một object Optional**, kể cả khi không có dữ liệu; không trả null. Nếu chính Optional là null, gọi map, isPresent hoặc orElse vẫn gây NullPointerException.

## 2. So sánh ba factory method

| Factory | Tham số | Khi giá trị null | Ý nghĩa sử dụng |
|---|---|---|---|
| Optional.empty() | Không có | Không nhận tham số | Đã biết chắc không có giá trị |
| Optional.of(value) | Bắt buộc khác null | Ném NullPointerException | Khẳng định giá trị phải tồn tại |
| Optional.ofNullable(value) | Có thể null | Trả Optional empty | Biến đầu vào có thể null thành Optional an toàn |

Chữ ký tổng quát của ba phương thức:

~~~java
static <T> Optional<T> empty()
static <T> Optional<T> of(T value)
static <T> Optional<T> ofNullable(T value)
~~~

Đây là **chữ ký API giản lược**, không phải một chương trình đầy đủ.

### 2.1. Optional.empty() — chủ động diễn đạt không có kết quả

~~~java
Optional<String> missingName = Optional.empty();
~~~

Đây là một **mảnh mã** cần import java.util.Optional. missingName là object Optional hợp lệ; isPresent() trả false và isEmpty() trả true trên Java 11+.

Use case phù hợp: tìm kiếm không khớp, tham số tùy chọn không được cung cấp, hoặc thuật toán xác định không có kết quả hợp lệ.

**Không nhầm empty với một Optional chứa null.** Optional không thể ở trạng thái present(null). Optional.empty().get() sẽ ném NoSuchElementException; dùng orElse, orElseGet hoặc nhánh xử lý empty khi điều đó có ý nghĩa.

### 2.2. Optional.of(value) — giá trị phải khác null

~~~java
Optional<String> language = Optional.of("Java");
~~~

of(value) trả Optional present nếu value non-null. Nếu value null, nó ném **NullPointerException ngay trong lời gọi tạo Optional**.

~~~java
// PHẢN VÍ DỤ: ném NullPointerException.
String input = null;
Optional<String> wrong = Optional.of(input);
~~~

Đó là hành vi **có chủ đích** khi null là lỗi hợp đồng: thay vì che lỗi, chương trình phát hiện nguồn truyền một giá trị trái với cam kết “bắt buộc có”.

Ngược lại, nếu nguồn có thể trả null **một cách hợp lệ** — như một Map.get(key) với key vắng mặt hoặc API cũ biểu diễn không tìm thấy bằng null — đừng dùng of; hãy dùng ofNullable.

### 2.3. Optional.ofNullable(value) — chuyển null thành empty

~~~java
String fromApi = null;
Optional<String> maybeLanguage = Optional.ofNullable(fromApi);
~~~

maybeLanguage là **Optional.empty hợp lệ**, không phải tham chiếu null. Nếu fromApi khác null, kết quả sẽ present với giá trị đó. Mô hình logic:

~~~text
ofNullable(null)    -> empty
ofNullable("Java")  -> present("Java")
ofNullable("")      -> present("")
ofNullable(0)       -> present(0)   [Integer]
ofNullable(false)   -> present(false) [Boolean]
~~~

Phương thức này là công cụ thuận tiện để **đưa dữ liệu có thể null đi vào một API trả Optional**. Nhưng nó không tự validation giá trị, không lọc chuỗi trắng, không chuyển số 0/false thành empty.

### Quy tắc lựa chọn nhanh

Nếu đã biết **không có giá trị**: dùng empty(). Nếu chắc chắn **có một giá trị non-null**: dùng of(value). Nếu đang cầm một biến **có thể null hợp lệ**: dùng ofNullable(value).

Dùng ofNullable cho dữ liệu “bắt buộc có” chỉ để che NullPointerException có thể làm lỗi hợp đồng biến mất; hãy giữ đúng chính sách của phương thức.

## 3. Những đầu vào dễ nhầm lẫn

| Giá trị truyền vào | Optional.of(value) | Optional.ofNullable(value) |
|---|---|---|
| "Java" | Present("Java") | Present("Java") |
| null | NullPointerException | Empty |
| "" | Present("") | Present("") |
| "   " | Present("   ") | Present("   ") |
| Integer.valueOf(0) | Present(0) | Present(0) |
| Boolean.FALSE | Present(false) | Present(false) |

**Chuỗi rỗng vẫn là giá trị.** Optional.of("") và Optional.ofNullable("") đều present vì chuỗi rỗng là object khác null. Nếu nghiệp vụ cần coi chuỗi trống hoặc toàn dấu cách là thiếu dữ liệu, hãy thêm một phép chuẩn hóa:

~~~java
// Mảnh mã: raw là String có thể null.
Optional<String> normalized = Optional.ofNullable(raw)
        .map(String::strip)
        .filter(s -> !s.isEmpty());
~~~

String.strip() có từ Java 11. Trên Java 8 thuần, cân nhắc chính sách chuẩn hóa bằng các API sẵn có trong dự án; cần hiểu sự khác biệt giữa trim và strip về Unicode, không đổi bừa nếu nghiệp vụ yêu cầu xử lý Unicode.

Nếu raw là null, map/filter không chạy và kết quả empty. Nếu raw là "   ", strip trả "", filter loại nó. Nếu raw là "  Java  ", kết quả present("Java").

## 4. Ví dụ hoàn chỉnh 1 — kiểm chứng ba cách tạo Optional

Tạo tệp **OptionalFactoriesDemo.java**:

~~~java
import java.util.Optional;

public class OptionalFactoriesDemo {
    public static void main(String[] args) {
        Optional<String> absent = Optional.empty();
        Optional<String> present = Optional.of("Java");

        String fromExternalApi = null;
        Optional<String> nullable = Optional.ofNullable(fromExternalApi);

        Optional<String> emptyText = Optional.of("");
        Optional<String> blankText = Optional.ofNullable("   ");
        Optional<String> normalized = blankText
                .map(String::strip)
                .filter(s -> !s.isEmpty());

        System.out.println("empty.isEmpty=" + absent.isEmpty());
        System.out.println("of.value=" + present.orElseThrow());
        System.out.println("nullable.isPresent=" + nullable.isPresent());
        System.out.println("emptyText.isPresent=" + emptyText.isPresent());
        System.out.println("blankText.isPresent=" + blankText.isPresent());
        System.out.println("normalized.isEmpty=" + normalized.isEmpty());
        System.out.println("empty.equals(empty)="
                + absent.equals(Optional.empty()));

        try {
            Optional.of((String) null);
        } catch (NullPointerException expected) {
            System.out.println("of(null)=NullPointerException");
        }
    }
}
~~~

Lệnh biên dịch và chạy trên JDK 17+:

~~~text
javac --release 17 OptionalFactoriesDemo.java
java OptionalFactoriesDemo
~~~

Stdout:

~~~text
empty.isEmpty=true
of.value=Java
nullable.isPresent=false
emptyText.isPresent=true
blankText.isPresent=true
normalized.isEmpty=true
empty.equals(empty)=true
of(null)=NullPointerException
~~~

Từng kết quả có ý nghĩa rõ ràng: absent luôn empty; present lấy được "Java"; ofNullable(null) trả empty; chuỗi rỗng và chuỗi trắng đều present **trước khi** áp dụng filter. Try/catch chỉ nhằm minh họa of(null) ném lỗi; trong ứng dụng, không bắt NPE như một phương án thay cho ofNullable khi null là điều có thể xảy ra hợp lệ.

## 5. Không so sánh empty bằng identity

Optional là một **value-based class**. Các Optional rỗng bằng nhau theo equals; các Optional present với giá trị bên trong bằng nhau cũng được coi là bằng nhau.

~~~java
// Mảnh mã.
Optional<String> a = Optional.empty();
Optional<String> b = Optional.empty();

boolean equalInValue = a.equals(b); // true
~~~

**Không dùng a == b** để suy luận cùng trạng thái empty: API **không bảo đảm** Optional.empty() luôn trả một singleton instance. Khi chỉ cần biết vắng mặt, dùng isEmpty() (Java 11+) hoặc !isPresent(). Khi cần so hai Optional về giá trị, dùng equals().

Cũng không dùng synchronized trên Optional hoặc dựa vào identityHashCode của Optional: đây là value-based class, và hành vi identity có thể không thích hợp với các bản Java tương lai.

## 6. Thiết kế phương thức trả về Optional

Mục tiêu thực tế thường là xử lý API bên ngoài có thể trả null và đưa ra một hợp đồng trả về không null.

### 6.1. Không tìm thấy trong Map

~~~java
// Mảnh mã: users là Map<Long, User>, id là Long.
Optional<User> found = Optional.ofNullable(users.get(id));
~~~

Với Map thông thường, get trả null nếu không tìm thấy key (hoặc nếu có key nhưng value null ở Map cho phép null). Vì vậy phải xác định nghiệp vụ có cần **phân biệt hai tình huống này** hay không; nếu có, dùng containsKey hoặc kiểu kết quả khác. Optional.ofNullable tự nó chỉ gộp cả hai thành empty.

### 6.2. Null đầu vào và null đầu ra

Có thể dùng ofNullable từ ranh giới đầu vào, rồi flatMap để tiếp tục gọi API:

~~~java
// Mảnh mã: users là Map<Long, User>.
Optional<User> result = Optional.ofNullable(id)
        .flatMap(key -> Optional.ofNullable(users.get(key)));
~~~

Nếu id null, flatMap không gọi lambda. Điều này hữu ích với Map.of(...) vì Map.of không cho phép key null. Nếu id hợp lệ nhưng không có trong Map, get trả null và ofNullable tạo empty.

### 6.3. Phương thức có thể chủ động return empty

~~~java
// Mảnh mã: User và findUserOrNull do ứng dụng định nghĩa.
Optional<User> lookup(long id) {
    if (id <= 0) {
        return Optional.empty();
    }
    return Optional.ofNullable(findUserOrNull(id));
}
~~~

Nếu một nhánh đã biết chắc không có kết quả, empty() diễn đạt ý định tốt hơn ofNullable(null). Nếu kết quả từ nguồn chưa biết là null hay không, ofNullable là lựa chọn hợp lý.

**Phân biệt “không tìm thấy” và “hệ thống lỗi”.** Database timeout, lỗi mạng hoặc vi phạm quy tắc nghiệp vụ không tự nhiên tương đương với Optional.empty. Nếu dùng empty để che mọi exception, tầng gọi sẽ không còn biết hệ thống bị lỗi.

## 7. Ví dụ hoàn chỉnh 2 — phương thức tra cứu an toàn

Tạo tệp **OptionalLookupDemo.java**:

~~~java
import java.util.Map;
import java.util.Optional;

public class OptionalLookupDemo {
    record User(long id, String name) {}

    static Optional<User> findUser(Map<Long, User> users, Long id) {
        return Optional.ofNullable(id)
                .flatMap(key -> Optional.ofNullable(users.get(key)));
    }

    static Optional<String> normalizeDisplayName(String raw) {
        return Optional.ofNullable(raw)
                .map(String::strip)
                .filter(s -> !s.isBlank());
    }

    public static void main(String[] args) {
        Map<Long, User> users = Map.of(
                1L, new User(1L, "An"),
                2L, new User(2L, "Binh")
        );

        String found = findUser(users, 1L)
                .map(User::name)
                .orElse("not found");

        String missing = findUser(users, 99L)
                .map(User::name)
                .orElse("not found");

        boolean nullIdIsEmpty = findUser(users, null).isEmpty();

        String cleanName = normalizeDisplayName("  Mai  ")
                .orElse("anonymous");

        boolean blankIsEmpty =
                normalizeDisplayName("  \t  ").isEmpty();

        boolean nullNameIsEmpty =
                normalizeDisplayName(null).isEmpty();

        System.out.println("found=" + found);
        System.out.println("missing=" + missing);
        System.out.println("nullIdIsEmpty=" + nullIdIsEmpty);
        System.out.println("cleanName=" + cleanName);
        System.out.println("blankIsEmpty=" + blankIsEmpty);
        System.out.println("nullNameIsEmpty=" + nullNameIsEmpty);
    }
}
~~~

Chạy:

~~~text
javac --release 17 OptionalLookupDemo.java
java OptionalLookupDemo
~~~

Stdout:

~~~text
found=An
missing=not found
nullIdIsEmpty=true
cleanName=Mai
blankIsEmpty=true
nullNameIsEmpty=true
~~~

Ở đây Map.of không cho phép null key/value, còn Map.get trả null khi key vắng mặt. Phương thức findUser không bao giờ trả tham chiếu Optional null. normalizeDisplayName chuyển nguồn null thành empty; với chuỗi trắng, map(String::strip) và filter xử lý theo **quy tắc nghiệp vụ**. isBlank() có từ Java 11.

**Không dùng Optional.of(users.get(id))** nếu id có thể không tồn tại: thay vì biểu diễn một tìm kiếm không thấy kết quả, of sẽ ném NullPointerException.

## 8. Xử lý Optional sau khi tạo: đừng gọi get() mù quáng

Bên cạnh factory, các phương thức dùng thường xuyên là:

| Phương thức | Khi present | Khi empty | Phiên bản tối thiểu |
|---|---|---|---|
| isPresent() | true | false | Java 8 |
| isEmpty() | false | true | Java 11 |
| ifPresent(action) | Chạy action | Bỏ qua | Java 8 |
| ifPresentOrElse(action, emptyAction) | Chạy action | Chạy emptyAction | Java 9 |
| map(mapper) | Áp dụng mapper, cho Optional mới | Giữ empty | Java 8 |
| filter(predicate) | Giữ hoặc bỏ giá trị | Giữ empty | Java 8 |
| orElse(defaultValue) | Trả giá trị bên trong | Trả defaultValue | Java 8 |
| orElseGet(supplier) | Trả giá trị bên trong | Gọi supplier | Java 8 |
| orElseThrow(exceptionSupplier) | Trả giá trị bên trong | Ném exception chỉ định | Java 8 |
| orElseThrow() | Trả giá trị bên trong | Ném NoSuchElementException | Java 10 |

Dùng get() khi Optional empty sẽ ném NoSuchElementException. Java API hiện hành xem orElseThrow() là lựa chọn ưu tiên hơn get() khi logic bắt buộc phải có kết quả. Khi vắng mặt là bình thường, hãy chọn fallback hoặc nhánh xử lý empty có nghĩa.

### orElse và orElseGet khác nhau vì thời điểm tính fallback

Trong Java, đối số phương thức được **đánh giá trước khi** lời gọi chạy. Vì thế:

~~~java
// Mảnh mã: expensiveFallback là hàm giả định.
String a = Optional.of("admin").orElse(expensiveFallback());
String b = Optional.of("admin")
        .orElseGet(() -> expensiveFallback());
~~~

Ở câu a, expensiveFallback() đã được gọi, dù Optional present và kết quả vẫn là "admin". Ở câu b, supplier chỉ được gọi khi Optional empty; với present, nó không chạy.

Không cần thay tất cả orElse bằng orElseGet: một literal như orElse("guest") là hợp lý. Ưu tiên orElseGet nếu fallback tốn CPU, tạo object không cần thiết, gọi I/O hoặc có side effect.

## 9. Ví dụ hoàn chỉnh 3 — kiểm chứng fallback eager và lazy

Tạo tệp **OptionalFallbackDemo.java**:

~~~java
import java.util.Optional;

public class OptionalFallbackDemo {
    private static String expensiveFallback() {
        System.out.println("fallback evaluated");
        return "guest";
    }

    public static void main(String[] args) {
        Optional<String> present = Optional.of("admin");

        String eager = present.orElse(expensiveFallback());
        System.out.println("present.orElse=" + eager);

        String lazy = present.orElseGet(
                OptionalFallbackDemo::expensiveFallback);
        System.out.println("present.orElseGet=" + lazy);

        String fromEmpty = Optional.<String>empty()
                .orElseGet(OptionalFallbackDemo::expensiveFallback);
        System.out.println("empty.orElseGet=" + fromEmpty);

        try {
            Optional.<String>empty()
                    .orElseThrow(() ->
                            new IllegalArgumentException("missing"));
        } catch (IllegalArgumentException ex) {
            System.out.println("empty.orElseThrow=" + ex.getMessage());
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 OptionalFallbackDemo.java
java OptionalFallbackDemo
~~~

Stdout:

~~~text
fallback evaluated
present.orElse=admin
present.orElseGet=admin
fallback evaluated
empty.orElseGet=guest
empty.orElseThrow=missing
~~~

Nhìn hai lần xuất hiện fallback evaluated: lần thứ nhất do đối số của orElse được đánh giá dù present; lần thứ hai do Optional rỗng làm orElseGet thực thi supplier. Nhánh orElseThrow(exceptionSupplier) tạo lỗi có thông điệp "missing" khi không có kết quả.

## 10. Type inference của Optional.empty() và ofNullable(null)

Ba factory là **generic methods**. Compiler thường suy ra tham số T từ kiểu đích:

~~~java
// Các mảnh mã hợp lệ:
Optional<String> a = Optional.empty();
Optional<Long> b = Optional.empty();
Optional<String> c = Optional.ofNullable(null);
~~~

Khi dùng var mà không có kiểu đích rõ ràng:

~~~java
var a = Optional.empty();
var b = Optional.ofNullable(null);
~~~

T thường được suy luận thành Object vì không có giá trị cụ thể để gợi kiểu String. Nếu cần Optional<String>, hãy dùng type witness:

~~~java
var name = Optional.<String>empty();
var anotherName = Optional.<String>ofNullable(null);
~~~

Hoặc khai báo đầy đủ Optional<String> ở bên trái. Không cast Optional<Object> sang Optional<String> một cách không an toàn; kiểu generic trong Java là invariant.

Optional.of(value) thường suy luận T từ kiểu của value. Nếu value là String, kết quả có kiểu Optional<String> trong ngữ cảnh thích hợp; nếu value literal null, of sẽ ném NullPointerException bất kể type inference.

## 11. map, flatMap và stream giúp xử lý trạng thái present/empty

### map: mapper trả null sẽ thành empty

Java Optional.map(mapper) xử lý kết quả mapper theo ý nghĩa tương tự Optional.ofNullable. Nếu có giá trị để map nhưng mapper trả null, kết quả map là Optional.empty().

~~~java
// Mảnh mã minh họa; kết quả là empty.
Optional<String> result = Optional.of("Java")
        .map(text -> (String) null);
~~~

Đừng hiểu rằng Optional.map tạo ra một Optional chứa null: Optional vẫn chỉ có hai trạng thái, present(non-null) hoặc empty.

### flatMap: mapper phải trả Optional hợp lệ

Khi hàm chuyển đổi đã trả Optional<U>, flatMap tránh tạo Optional<Optional<U>>. Nếu mapper của flatMap **trả null thay vì Optional**, thao tác có thể ném NullPointerException. Vì thế một phương thức trả Optional không được return null.

~~~java
// Mảnh mã: lookupByKey(key) là phương thức của ứng dụng
// và luôn trả Optional<String>, có thể empty.
Optional<String> result = Optional.of("key")
        .flatMap(key -> lookupByKey(key));
~~~

### Optional.stream() (Java 9+)

Optional.stream() trả Stream một phần tử nếu present, hoặc Stream rỗng nếu empty. Nó hữu ích để lấy giá trị từ Stream<Optional<T>>:

~~~java
// Mảnh mã: results là List<Optional<String>>.
List<String> values = results.stream()
        .flatMap(Optional::stream)
        .toList();
~~~

Stream.toList() có từ Java 16 và trả List không sửa được. Nếu chỉ cần lọc null trong List<String>, filter(Objects::nonNull) có thể ngắn và rõ hơn; không phải mọi thao tác dữ liệu đều cần tạo Optional.

## 12. Ví dụ hoàn chỉnh 4 — kết hợp factory với pipeline Stream

Tạo tệp **OptionalPipelineDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public class OptionalPipelineDemo {
    static Optional<String> normalize(String raw) {
        return Optional.ofNullable(raw)
                .map(String::strip)
                .filter(s -> !s.isBlank());
    }

    public static void main(String[] args) {
        List<String> raw = new ArrayList<>();
        raw.add("  Alpha ");
        raw.add(null);
        raw.add("   ");
        raw.add("Beta");

        List<String> cleaned = raw.stream()
                .map(OptionalPipelineDemo::normalize)
                .flatMap(Optional::stream)
                .toList();

        System.out.println("raw.size=" + raw.size());
        System.out.println("cleaned=" + cleaned);
    }
}
~~~

Chạy:

~~~text
javac --release 17 OptionalPipelineDemo.java
java OptionalPipelineDemo
~~~

Stdout:

~~~text
raw.size=4
cleaned=[Alpha, Beta]
~~~

List.of(...) không cho phép phần tử null, vì vậy ví dụ chủ động tạo ArrayList để minh họa nguồn có null. normalize trả empty khi gặp null và khi chuỗi bị chuẩn hóa thành trắng; flatMap(Optional::stream) giữ lại đúng các Optional present. Đây là một bài tập về cách dùng Optional làm **kết quả chuẩn hóa**, không phải yêu cầu phải wrap Optional cho mọi phần tử trong mọi Stream.

## 13. Lỗi phổ biến cần tránh

### Lỗi 1 — dùng Optional.of với API có thể trả null

~~~java
// PHẢN VÍ DỤ: repositoryFindById(id) có thể trả null.
Optional<User> user = Optional.of(repositoryFindById(id));
~~~

Nếu null là trường hợp không tìm thấy hợp lệ, dùng ofNullable. Nếu null là lỗi hợp đồng, cân nhắc để of phát hiện lỗi thay vì che bug. Phải xác định **ý nghĩa của null trong nghiệp vụ** trước khi chọn factory.

### Lỗi 2 — phương thức Optional trả chính null

~~~java
// PHẢN VÍ DỤ:
Optional<String> findName() {
    return null;
}
~~~

Trả Optional.empty() khi không có kết quả. Người dùng của hàm phải nhận một Optional hợp lệ.

### Lỗi 3 — cho rằng chuỗi rỗng hoặc 0 là empty

Optional.of("") và Optional.of(0) đều present. Nếu muốn coi chúng là “thiếu”, dùng filter/validation theo yêu cầu nghiệp vụ.

### Lỗi 4 — so sánh Optional bằng ==

Không có bảo đảm Optional.empty() là singleton. Dùng isEmpty/isPresent cho trạng thái, equals cho nội dung. Đây là value-based class; tránh dựa vào identity hoặc dùng instance Optional làm lock.

### Lỗi 5 — gọi get() mà chưa xử lý trường hợp empty

Optional.empty().get() ném NoSuchElementException. Dùng orElse, orElseGet, orElseThrow hoặc các thao tác điều kiện. Không dùng isPresent()+get() như một nghi thức ở mọi nơi khi map/flatMap có thể diễn đạt trực tiếp.

### Lỗi 6 — lạm dụng Optional ở field, tham số và DTO

Theo API Note của Java, Optional **chủ yếu dành cho return type** khi cần biểu diễn không có kết quả. Không cần thay mọi biến, field, tham số, thuộc tính entity hoặc DTO bằng Optional; serialization và framework mapping có thể cần cách biểu diễn khác. Khi giá trị luôn bắt buộc có, dùng kiểu T trực tiếp và validation phù hợp.

### Lỗi 7 — bọc Optional có sẵn

Nếu API đã trả Optional<User>, đừng gọi Optional.ofNullable(optional) theo thói quen: có thể tạo Optional<Optional<User>> dư thừa. Nếu cần biến đổi, gọi map/flatMap trên Optional có sẵn.

### Lỗi 8 — che lỗi hệ thống thành Optional.empty

Không biến exception do timeout, mất DB connection hay lỗi dữ liệu thành empty mà không có quy tắc nghiệp vụ rõ ràng. “Không tìm thấy” khác “không thể thực hiện tìm kiếm”. Optional chỉ biểu diễn có/không có giá trị, không cung cấp đầy đủ thông tin lỗi.

### Lỗi 9 — hiểu sai orElse thành lazy

orElse(expensive()) đánh giá expensive() ngay cả khi Optional present. Nếu fallback chỉ được tính khi empty, dùng orElseGet.

### Lỗi 10 — bỏ qua khác biệt phiên bản

Ba factory empty/of/ofNullable đều có từ Java 8. Nhưng Optional.stream và ifPresentOrElse có từ Java 9; orElseThrow() không tham số có từ Java 10; Optional.isEmpty, String.strip và String.isBlank có từ Java 11; Stream.toList có từ Java 16. Các ví dụ đầy đủ ở đây yêu cầu Java 17+, nên đều hợp lệ. Nếu viết riêng cho Java 8, điều chỉnh các API mới đúng phiên bản, không sao chép nguyên ví dụ rồi cho rằng mọi phương thức đã có từ Java 8.

## 14. Bảng quyết định thực tế

| Tình huống | Nên dùng | Vì sao |
|---|---|---|
| Biết chắc không có kết quả | Optional.empty() | Diễn đạt sự vắng mặt trực tiếp |
| Giá trị đã được bảo đảm non-null | Optional.of(value) | Sai hợp đồng null được phát hiện ngay |
| Nguồn có thể trả null hợp lệ | Optional.ofNullable(value) | Quy đổi null thành empty |
| Cần coi chuỗi trắng là thiếu | ofNullable(raw).map(...).filter(...) | Thêm chính sách chuẩn hóa |
| Có Optional và muốn default hằng | orElse(default) | Rõ ràng, đủ cho fallback rẻ |
| Cần tính default đắt tiền | orElseGet(supplier) | Lazy: chỉ chạy khi empty |
| Không có kết quả là lỗi | orElseThrow(...) | Diễn đạt điều kiện thất bại |
| Chỉ chuyển đổi giá trị nếu present | map/flatMap | Không tự gọi get |
| Đang nhận Optional từ API khác | Dùng trực tiếp | Tránh Optional lồng không cần thiết |

## 15. Tự kiểm tra kiến thức

**Câu 1.** Optional.of(null) khác Optional.ofNullable(null) thế nào?

*Đáp án:* of(null) ném NullPointerException; ofNullable(null) trả Optional.empty() hợp lệ.

**Câu 2.** Optional.of("") có empty không?

*Đáp án:* Không. Chuỗi rỗng là một object String khác null nên Optional present.

**Câu 3.** Khi nào return Optional.empty() thể hiện ý định rõ hơn ofNullable(null)?

*Đáp án:* Khi thuật toán đã **chắc chắn không có kết quả**. ofNullable hợp khi chuyển một biến nguồn có thể null.

**Câu 4.** Vì sao hàm Optional<User> không nên return null?

*Đáp án:* Vì người gọi kỳ vọng một container Optional có thể dùng các phương thức xử lý present/empty. Tham chiếu null làm mất hợp đồng đó.

**Câu 5.** Dùng a == Optional.empty() có đúng để kiểm tra empty không?

*Đáp án:* Không. Không có bảo đảm singleton identity; dùng isEmpty/isPresent.

**Câu 6.** var x = Optional.ofNullable(null) suy luận loại T nào nếu không có ngữ cảnh?

*Đáp án:* Thường là Object. Nếu cần String, dùng Optional.<String>ofNullable(null) hoặc kiểu đích Optional<String>.

**Câu 7.** Khi Optional đã present, orElse(expensive()) có gọi expensive() không?

*Đáp án:* Có, vì biểu thức đối số được đánh giá trước lời gọi. orElseGet(() -> expensive()) mới trì hoãn tính fallback.

**Câu 8.** Có nên trả empty cho mọi lỗi database?

*Đáp án:* Không. Empty diễn đạt vắng mặt bình thường; lỗi kết nối/timeout cần có cơ chế xử lý riêng.

## Tài liệu tham khảo đang được duy trì

- Oracle Java SE 25 (LTS), Optional: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html
- Oracle Java SE 25 (LTS), Stream: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html
- Oracle Java SE 25 (LTS), Map: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html

**Ghi nhớ:** Optional.empty() là “không có giá trị”, Optional.of(value) là “chắc chắn có non-null value”, Optional.ofNullable(value) là “value có thể null, hãy chuyển null thành empty”. Chọn đúng theo hợp đồng nguồn dữ liệu, rồi xử lý empty có chủ đích ở nơi sử dụng Optional.
