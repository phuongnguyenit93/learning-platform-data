# So sánh component tham chiếu bằng ngữ nghĩa `Objects.equals`

**Module:** `JAVA_VERSION_JAVA16`  
**Chương:** Ngữ nghĩa record  
**Áp dụng:** Java 16 trở lên, bao gồm Java hiện đại.

Record được chuẩn hóa thành tính năng chính thức ở Java 16. Với một `record` không tự khai báo `equals(Object)`, Java tự cung cấp phương thức `equals` để so sánh các record component. Riêng component **kiểu tham chiếu** như `String`, `List`, `BigDecimal`, record khác hoặc mảng, phép so sánh có **ngữ nghĩa tương đương `java.util.Objects.equals(a, b)`**. Quy tắc này tiếp tục áp dụng trong các phiên bản Java hiện đại và là trọng tâm của bài.

Việc nắm rõ quy tắc giúp chọn đúng kiểu component cho value object, dự đoán kết quả khi record chứa `null` hoặc collection, và tránh lỗi khi record tham gia `HashMap`/`HashSet`.

## 1. Hợp đồng `equals` mặc định của record

Xét khai báo:

```java
record Profile(String name, String email) {}
```

Khi so sánh hai `Profile`, phương thức `equals` **được compiler cung cấp** sẽ trả về `true` khi:

1. Đối tượng ở vế phải là instance của **cùng lớp record** `Profile` tại runtime.
2. Component `name` của hai đối tượng bằng nhau theo ngữ nghĩa `Objects.equals`.
3. Component `email` của hai đối tượng bằng nhau theo ngữ nghĩa `Objects.equals`.

Có thể hình dung điều kiện tương đương:

```java
// Mã minh họa ngữ nghĩa, KHÔNG phải mã mà compiler bắt buộc tạo ra.
boolean equivalent(Profile left, Object candidate) {
    if (!(candidate instanceof Profile right)) {
        return false;
    }
    return java.util.Objects.equals(left.name(), right.name())
        && java.util.Objects.equals(left.email(), right.email());
}
```

Ở ví dụ `Profile`, các accessor mặc định chỉ trả về giá trị của component nên mã minh họa hoạt động đúng. **Đặc tả không yêu cầu compiler phải tạo các lệnh gọi `Objects.equals` thật, không cố định thuật toán hoặc thứ tự so sánh**, và phép so sánh mặc định dựa trên **trường component**, không gọi accessor do lập trình viên ghi đè.

> Phạm vi của bài là `equals(Object)` **mặc định**. Java cho phép tự khai báo `equals` và `hashCode` trong record; một cách triển khai tùy chỉnh có thể thay đổi cách các giá trị được so sánh nhưng phải giữ các hợp đồng của `Object` và record.

## 2. `Objects.equals(a, b)` thực sự có nghĩa gì?

Hành vi được mô tả đơn giản như sau:

```java
import java.util.Objects;

// Biểu thức mô tả ngữ nghĩa của Objects.equals(a, b):
boolean equal = (a == b) || (a != null && a.equals(b));
```

Trong ngữ nghĩa trên, `a` và `b` là các biến kiểu tham chiếu đã được khai báo trước đó. `Objects.equals` xử lý `null` an toàn và, khi cả hai đều khác `null`, dựa vào `equals` do kiểu đối tượng ở vế trái cung cấp.

| Component bên trái | Component bên phải | `Objects.equals` | Giải thích |
| --- | --- | --- | --- |
| `null` | `null` | `true` | Cả hai cùng `null`. |
| `null` | `"A"` | `false` | Chỉ một bên `null`. |
| `"A"` | `null` | `false` | Chỉ một bên `null`. |
| `new String("A")` | `new String("A")` | `true` | `String.equals` so sánh nội dung. |
| `"A"` | `"a"` | `false` | `String.equals` phân biệt chữ hoa/chữ thường. |
| Cùng một đối tượng | Cùng một đối tượng | `true` | Cùng tham chiếu. |

So sánh tham chiếu bằng `==` và so sánh giá trị bằng `equals` là hai khái niệm khác nhau:

```java
record Badge(String title) {}

String s1 = new String("JAVA");
String s2 = new String("JAVA");

System.out.println(s1 == s2);                       // false
System.out.println(java.util.Objects.equals(s1, s2)); // true
System.out.println(new Badge(s1).equals(new Badge(s2))); // true
```

Hai chuỗi khác đối tượng nhưng có cùng nội dung. Vì `String` triển khai `equals` theo ký tự, record chứa chúng cũng bằng nhau.

### Có `null` trong record thì sao?

Mặc định, record **không tự cấm `null`** đối với component tham chiếu.

```java
record Contact(String phone, String email) {}

Contact a = new Contact(null, "a@example.org");
Contact b = new Contact(null, "a@example.org");
Contact c = new Contact("123", "a@example.org");

System.out.println(a.equals(b)); // true
System.out.println(a.equals(c)); // false
```

Hai component `phone` cùng `null` không làm ném `NullPointerException` khi dùng `equals` mặc định. Tuy nhiên, nếu nghiệp vụ yêu cầu không được để trống dữ liệu, hãy kiểm tra trong canonical constructor:

```java
import java.util.Objects;

record Contact(String phone, String email) {
    Contact {
        Objects.requireNonNull(email, "email");
    }
}
```

Quy tắc kiểm tra `null` là quyết định của mô hình dữ liệu, độc lập với việc `Objects.equals` xử lý `null` an toàn.

## 3. Bảng quy tắc theo kiểu component

Record **không tự quyết định hai đối tượng tham chiếu có giá trị bằng nhau hay không**. Nó sử dụng ngữ nghĩa `equals` của chính kiểu thành phần:

| Kiểu component | Cách `equals` thường hoạt động | Ảnh hưởng với record |
| --- | --- | --- |
| `String` | So sánh chuỗi ký tự, có phân biệt hoa/thường. | Hai chuỗi cùng nội dung bằng nhau dù là hai instance. |
| Record khác | So sánh cùng lớp record và các component của record lồng nhau. | Có thể so sánh giá trị theo nhiều cấp. |
| `List` | So sánh theo thứ tự các phần tử bằng `equals`. | Cùng phần tử khác thứ tự thường không bằng nhau. |
| `Set` | So sánh thành viên của tập hợp, không phụ thuộc thứ tự duyệt. | Hai tập hợp có cùng thành viên bằng nhau. |
| `Map` | So sánh các ánh xạ khóa → giá trị. | Hai map chứa cùng mapping bằng nhau. |
| `Optional` | So sánh trạng thái rỗng hoặc giá trị đang chứa. | Hai `Optional` tương đương bằng nhau. |
| `BigDecimal` | `equals` xét cả giá trị và `scale`. | `1.0` và `1.00` không bằng nhau theo `equals`. |
| Mảng `int[]`, `String[]`, ... | Mảng không ghi đè `Object.equals`: so sánh cùng đối tượng mảng. | Hai mảng khác nhau nhưng cùng phần tử không bằng nhau theo mặc định. |
| Class thường không ghi đè `equals` | Kế thừa so sánh danh tính từ `Object`. | Hai instance khác nhau không bằng nhau dù trường nội bộ giống nhau. |
| Class có `equals` tùy chỉnh | Theo hợp đồng do class đó triển khai. | Record kế thừa ngữ nghĩa so sánh của component. |

### Record lồng record

```java
record Address(String city, String street) {}
record Person(String name, Address address) {}

Person p1 = new Person("Lan", new Address("Huế", "Lê Lợi"));
Person p2 = new Person("Lan", new Address("Huế", "Lê Lợi"));

System.out.println(p1.equals(p2)); // true
```

Ở đây, `Person.address` là kiểu tham chiếu. `Objects.equals` đi vào `Address.equals`, mà `Address` cũng so sánh theo component; vì thế hai địa chỉ được tạo riêng nhưng có cùng nội dung vẫn bằng nhau.

### Collection: cùng nội dung nhưng tùy đặc tính kiểu

```java
import java.util.List;
import java.util.Set;

record Favorites(List<String> ordered, Set<String> categories) {}

Favorites one = new Favorites(
    List.of("Java", "SQL"),
    Set.of("backend", "database")
);
Favorites two = new Favorites(
    List.of("Java", "SQL"),
    Set.of("database", "backend")
);
Favorites three = new Favorites(
    List.of("SQL", "Java"),
    Set.of("backend", "database")
);

System.out.println(one.equals(two));   // true
System.out.println(one.equals(three)); // false: List khác thứ tự
```

`Objects.equals` không tự phân tích ý nghĩa nghiệp vụ của collection. `List.equals` và `Set.equals` đã có hợp đồng riêng, và record dùng lại hợp đồng đó.

## 4. Một bẫy hay gặp: `BigDecimal.equals` khác `compareTo`

Với tiền tệ hoặc giá trị thập phân, hai giá trị bằng nhau về mặt số học có thể **không** bằng nhau theo `BigDecimal.equals`:

```java
import java.math.BigDecimal;

record Amount(BigDecimal value) {}

BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.compareTo(b) == 0);          // true: cùng giá trị số
System.out.println(a.equals(b));                  // false: scale khác nhau
System.out.println(new Amount(a).equals(new Amount(b))); // false
```

Nếu yêu cầu nghiệp vụ coi hai cách biểu diễn này là bằng nhau, nên xác định chính sách chuẩn hóa ở thời điểm tạo record, chẳng hạn:

```java
import java.math.BigDecimal;
import java.util.Objects;

record Amount(BigDecimal value) {
    Amount {
        value = Objects.requireNonNull(value, "value")
                       .stripTrailingZeros();
    }
}

System.out.println(
    new Amount(new BigDecimal("1.0"))
        .equals(new Amount(new BigDecimal("1.00")))
); // true
```

`stripTrailingZeros()` có thể thay đổi cách hiển thị và `scale` của dữ liệu (ví dụ có thể dùng dạng lũy thừa của 10). Hãy áp dụng khi phù hợp với hợp đồng dữ liệu. Điều quan trọng là chuẩn hóa giá trị lưu trữ trước khi sử dụng `equals` mặc định.

## 5. Mảng: `Objects.equals` **không** phải so sánh sâu

Đây là trường hợp gây nhầm lẫn khi mới dùng record:

```java
record Payload(byte[] bytes) {}

byte[] first = {1, 2, 3};
byte[] second = {1, 2, 3};

System.out.println(java.util.Arrays.equals(first, second)); // true
System.out.println(java.util.Objects.equals(first, second)); // false
System.out.println(
    new Payload(first).equals(new Payload(second))
); // false

System.out.println(
    new Payload(first).equals(new Payload(first))
); // true: dùng cùng một mảng
```

Cần phân biệt:

- `Objects.equals(a, b)`: gọi `equals` của component và xử lý `null`. Với mảng, `equals` mặc định xét cùng tham chiếu.
- `Arrays.equals(a, b)`: so sánh phần tử tương ứng của hai mảng cùng loại; có các overload cho mảng kiểu nguyên thủy và tham chiếu.
- `Arrays.deepEquals(a, b)`: so sánh sâu khi các phần tử là mảng lồng nhau; áp dụng cho `Object[]`.
- `Objects.deepEquals(a, b)`: có quy tắc so sánh sâu đối với mảng, **nhưng không phải quy tắc mà record tự áp dụng** cho component tham chiếu.

Nếu record có nghĩa là “một chuỗi byte theo nội dung”, có thể triển khai rõ ràng phép so sánh và mã băm, đồng thời sao chép phòng vệ:

```java
import java.util.Arrays;
import java.util.Objects;

record ByteValue(byte[] bytes) {
    ByteValue {
        bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }

    @Override
    public boolean equals(Object other) {
        return this == other
            || (other instanceof ByteValue that
                && Arrays.equals(this.bytes, that.bytes));
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(bytes);
    }
}

System.out.println(
    new ByteValue(new byte[] {1, 2})
        .equals(new ByteValue(new byte[] {1, 2}))
); // true
```

`instanceof` với biến pattern trong ví dụ là tính năng chính thức từ Java 16. Record `ByteValue` dùng nội dung mảng làm ngữ nghĩa bằng nhau và bảo đảm `hashCode` phù hợp với `equals`. Việc `clone` ở constructor và accessor giúp bên ngoài không thay đổi trực tiếp mảng đang lưu.

Nếu không bắt buộc dùng mảng, một lựa chọn đơn giản hơn thường là biểu diễn dữ liệu dưới dạng một collection bất biến có hợp đồng `equals` theo giá trị.

## 6. `equals` phụ thuộc đối tượng component có thể thay đổi

Các trường của record là `final`, nhưng đối tượng được tham chiếu **có thể vẫn sửa được**. Vì vậy, giá trị quan sát qua `Objects.equals` và `hashCode` có thể thay đổi theo thời gian.

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

record QueryKey(List<String> filters) {}

List<String> mutableFilters = new ArrayList<>(List.of("active"));
QueryKey key = new QueryKey(mutableFilters);
Map<QueryKey, String> cache = new HashMap<>();
cache.put(key, "result");

mutableFilters.add("premium");
// List.hashCode đã thay đổi; lookup bằng key có thể không thấy giá trị cũ.
```

Khi một component là `List`, `Objects.equals` sử dụng `List.equals`. `hashCode` mặc định của record cũng bắt nguồn từ các component. Nếu chúng thay đổi trong khi record đang làm khóa `Map`, hợp đồng sử dụng khóa theo giá trị có thể bị phá vỡ.

Với danh sách các kiểu bất biến như `String`, hãy sao chép phòng vệ vào compact constructor:

```java
import java.util.List;

record QueryKey(List<String> filters) {
    QueryKey {
        filters = List.copyOf(filters);
    }
}
```

`List.copyOf` tạo danh sách không thể sửa qua API của `List`, ngăn việc thay đổi cấu trúc danh sách từ tham chiếu gốc. Phương thức này không cho phép phần tử `null` và **không tự sao chép sâu** các đối tượng phần tử có thể thay đổi. Nếu phần tử là class mutable, cần thiết kế cơ chế bất biến phù hợp cho toàn bộ dữ liệu.

## 7. `equals` của component tùy chỉnh quyết định kết quả

Một class thường không ghi đè `equals` sẽ kế thừa hành vi so sánh danh tính của `Object`:

```java
final class Token {
    private final String code;

    Token(String code) {
        this.code = code;
    }
}

record Session(Token token) {}

System.out.println(
    new Session(new Token("abc")).equals(
        new Session(new Token("abc"))
    )
); // false: hai Token là hai đối tượng khác nhau
```

Với trường hợp này, record **không tự so sánh trường `code` bên trong `Token`**. Nếu cần bình đẳng theo giá trị của token, có thể mô hình hóa token thành một `record` hoặc triển khai `equals` và `hashCode` nhất quán cho `Token`.

Một lưu ý khác: nếu component có `equals` tùy chỉnh vi phạm tính phản xạ, đối xứng, bắc cầu hoặc tính ổn định, record chứa nó cũng có thể gặp vấn đề tương ứng. Record không thể sửa một hợp đồng `equals` bị lỗi từ lớp thành phần.

## 8. Accessor tùy chỉnh không làm thay đổi so sánh mặc định

Giá trị dùng để so sánh là **giá trị các trường component**, không phải kết quả trả về từ accessor đã ghi đè. Ví dụ sau minh họa lý do không nên cố dùng accessor để chuẩn hóa giá trị:

```java
record Tag(String text) {
    @Override
    public String text() {
        return text.trim();
    }
}

Tag a = new Tag("green");
Tag b = new Tag(" green ");

System.out.println(a.text().equals(b.text())); // true
System.out.println(a.equals(b));               // false
```

Mặc dù hai accessor trả về cùng `"green"`, giá trị gốc lưu trong hai trường `text` vẫn khác nhau. Việc accessor biến đổi dữ liệu còn có thể phá vỡ bất biến sao chép của record. Nếu muốn coi `"green"` và `" green "` là cùng một giá trị, hãy chuẩn hóa **trong constructor**:

```java
import java.util.Objects;

record Tag(String text) {
    Tag {
        text = Objects.requireNonNull(text, "text").trim();
    }
}

System.out.println(
    new Tag("green").equals(new Tag(" green "))
); // true
```

Đây là cách tận dụng `equals` mặc định mà vẫn giữ một biểu diễn dữ liệu nhất quán.

## 9. Hệ quả với `hashCode`, `Set` và `Map`

Với record mặc định, `hashCode` được sinh từ các component tương ứng và tuân thủ hợp đồng:

```text
Nếu a.equals(b) == true thì a.hashCode() == b.hashCode().
Chiều ngược lại không bắt buộc đúng.
```

```java
import java.util.HashSet;
import java.util.Set;

record Role(String name) {}
record User(String login, Role role) {}

Set<User> users = new HashSet<>();
users.add(new User("lan", new Role("admin")));
users.add(new User("lan", new Role("admin")));
users.add(new User("lan", new Role("reader")));

System.out.println(users.size()); // 2
```

`Role` là record và hai instance `Role("admin")` bằng nhau, nên hai `User` đầu bằng nhau; `HashSet` chỉ giữ một giá trị tương đương. Giá trị `role` khác làm `User` thứ ba không bằng hai giá trị trước.

Nếu tự viết `equals` cho record có component mảng hoặc class đặc biệt, cần sửa `hashCode` nhất quán. Không nên dựa vào giá trị hash số cụ thể hoặc thứ tự xử lý component do một phiên bản JDK tạo ra: đặc tả chỉ bảo đảm hợp đồng, không cố định thuật toán sinh hash.

## 10. Checklist và câu hỏi tự kiểm tra

Khi chọn component tham chiếu cho record, lần lượt tự hỏi:

1. Kiểu component đã có `equals` theo đúng ý nghĩa nghiệp vụ chưa, hay vẫn so sánh danh tính?
2. Giá trị `null` có hợp lệ không? Nếu không, có kiểm tra bằng `Objects.requireNonNull` không?
3. Component có chứa mảng hay object mutable khiến ngữ nghĩa bằng nhau và hash thay đổi không?
4. `List`, `Set`, `Map`, `BigDecimal` có hợp đồng bằng nhau phù hợp với dữ liệu đang biểu diễn không?
5. Có nên chuẩn hóa trong canonical constructor và giữ `equals`/`hashCode` mặc định không?

**Tình huống tự kiểm tra**

```java
import java.math.BigDecimal;
import java.util.List;

record Item(String code, List<String> tags, BigDecimal price) {}

Item x = new Item("A", List.of("new", "hot"), new BigDecimal("2.0"));
Item y = new Item("A", List.of("new", "hot"), new BigDecimal("2.00"));
Item z = new Item("A", List.of("hot", "new"), new BigDecimal("2.0"));
```

- `x.equals(y)` trả về gì? **`false`**: hai `BigDecimal` có `scale` khác nhau.
- `x.equals(z)` trả về gì? **`false`**: `List` giữ ngữ nghĩa có thứ tự.
- Nếu cả ba component đều cùng giá trị theo `equals` và cùng lớp record, kết quả sẽ là gì? **`true`**.

**Ghi nhớ:** Trong `equals(Object)` được compiler sinh cho record, component **tham chiếu** được so sánh theo ngữ nghĩa `Objects.equals`: an toàn với `null`, đồng thời phụ thuộc vào `equals` của chính đối tượng thành phần. Java không tự so sánh sâu toàn bộ đồ thị đối tượng. Thiết kế component có ngữ nghĩa giá trị và bảo đảm dữ liệu ổn định là chìa khóa để record hoạt động đúng.

## Tài liệu chính thức

- [Java SE 26 API — `java.lang.Record`, hợp đồng `equals`/`hashCode`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Record.html).
- [Java SE 26 API — `java.util.Objects.equals`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Objects.html#equals(java.lang.Object,java.lang.Object)).
- [Java Language Specification, §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10).
- [JEP 395 — Records, tính năng chính thức trong Java 16](https://openjdk.org/jeps/395).
