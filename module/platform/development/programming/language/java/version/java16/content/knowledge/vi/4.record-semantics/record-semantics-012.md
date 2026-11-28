# Invariant sao chép record từ các accessor của chính nó

**Module:** `JAVA_VERSION_JAVA16`  
**Chương:** Ngữ nghĩa record  
**Áp dụng:** Java 16 trở lên, bao gồm Java hiện đại.

Record được thiết kế như một *transparent carrier* cho các giá trị: component có tên, accessor công khai để đọc component và `equals` mặc định để so sánh dữ liệu. Tính minh bạch này được thể hiện qua **copy invariant**: nếu lấy các giá trị từ accessor của một record rồi truyền chúng vào canonical constructor để tạo record mới cùng kiểu, record mới phải bằng record ban đầu theo `equals`.

Quy tắc này có ý nghĩa thực tế khi dùng record để sao chép, chuyển đổi, kiểm thử hoặc truyền dữ liệu qua các tầng ứng dụng. Accessor tường minh, constructor chuẩn hóa và defensive copy đều cần được thiết kế sao cho invariant vẫn đúng.

## 1. Phát biểu copy invariant

Với record `R` có các component `c1`, `c2`, ..., `cn` và một instance `r`, copy invariant yêu cầu:

```java
R copy = new R(r.c1(), r.c2(), ..., r.cn());

assert r.equals(copy);
```

Nói cách khác:

1. Gọi accessor công khai của từng component trên instance gốc.
2. Truyền các giá trị nhận được vào canonical constructor của cùng record.
3. Instance mới phải bằng instance gốc theo `equals`.

Đây là bình đẳng theo giá trị, không phải đồng nhất đối tượng. Bản sao thường là instance khác:

```java
record Point(int x, int y) {}

Point original = new Point(10, 20);
Point copy = new Point(original.x(), original.y());

System.out.println(original == copy);      // false
System.out.println(original.equals(copy)); // true
```

Copy invariant không yêu cầu `original` và `copy` dùng chung identity. Nó yêu cầu dữ liệu mà record công khai qua accessor đủ để tái tạo một giá trị tương đương.

## 2. Vì sao invariant này quan trọng?

Record được định nghĩa từ các component. Người dùng có thể dựa vào accessor để:

- Tạo một bản sao có cùng giá trị.
- Chuyển dữ liệu sang record hoặc DTO khác.
- Xây dựng dữ liệu kiểm thử từ một instance có sẵn.
- Đưa component vào một bộ tuần tự hóa hoặc mapper.
- So sánh hai instance mà không cần biết chi tiết triển khai nội bộ.

Nếu accessor trả dữ liệu đã bị biến đổi theo cách không tương thích với `equals`, các thao tác này trở nên khó dự đoán. Một đối tượng có thể hiển thị các giá trị qua accessor nhưng lại không thể được tái tạo từ chính các giá trị đó.

Ví dụ với accessor chuẩn:

```java
record UserProfile(String username, int age) {}

UserProfile user = new UserProfile("linh", 25);
UserProfile recreated =
    new UserProfile(user.username(), user.age());

System.out.println(user.equals(recreated)); // true
```

Đây là hành vi mong đợi: component đọc được chính là dữ liệu xác định giá trị của record.

## 3. Accessor biến đổi dữ liệu có thể phá invariant

Không nên dùng accessor để âm thầm chuẩn hóa một component nếu canonical constructor vẫn lưu giá trị ban đầu:

```java
record DisplayName(String value) {
    public String value() {
        return value.strip();
    }
}

DisplayName original = new DisplayName("  Linh  ");
DisplayName copy = new DisplayName(original.value());

System.out.println(original.value()); // Linh
System.out.println(copy.value());     // Linh
System.out.println(original.equals(copy)); // false
```

Instance gốc lưu chuỗi `"  Linh  "`, trong khi bản sao lưu chuỗi `"Linh"`. Accessor đã công bố một giá trị không đủ để tái tạo component được lưu. `equals` mặc định so sánh hai giá trị đã lưu nên kết quả là `false`.

### Chuẩn hóa tại constructor

Nếu quy tắc nghiệp vụ yêu cầu bỏ khoảng trắng ở hai đầu, hãy chuẩn hóa trước khi giá trị được lưu vào component:

```java
import java.util.Objects;

record DisplayName(String value) {
    DisplayName {
        value = Objects.requireNonNull(value, "value").strip();
    }
}

DisplayName original = new DisplayName("  Linh  ");
DisplayName copy = new DisplayName(original.value());

System.out.println(original.value()); // Linh
System.out.println(original.equals(copy)); // true
```

Compact constructor nhận các tham số component và cho phép kiểm tra hoặc gán lại tham số trước khi compiler gán chúng vào các trường component. Sau khi chuẩn hóa, accessor tự sinh trả đúng giá trị đã lưu. Vì thế việc tạo lại record từ accessor bảo toàn equality.

Đây thường là cách thiết kế rõ ràng nhất: constructor thiết lập giá trị hợp lệ, accessor đọc giá trị đó.

## 4. Accessor trả defensive copy vẫn có thể giữ invariant

Accessor không bắt buộc phải trả cùng tham chiếu nội bộ. Khi component là object mutable, accessor có thể trả một bản sao để bảo vệ trạng thái bên trong. Điều kiện là bản sao trả về phải có ngữ nghĩa equality phù hợp với component được lưu.

Với collection chứa phần tử immutable như `String`, có thể tạo snapshot trong constructor:

```java
import java.util.List;
import java.util.Objects;

record SearchQuery(List<String> tags) {
    SearchQuery {
        tags = List.copyOf(
            Objects.requireNonNull(tags, "tags")
        );
    }
}

SearchQuery original =
    new SearchQuery(List.of("java", "records"));
SearchQuery copy = new SearchQuery(original.tags());

System.out.println(original.equals(copy)); // true
```

`List.copyOf` trả về danh sách không thể sửa qua API `List`. `List.equals` so sánh nội dung và thứ tự phần tử, nên record được tạo lại từ accessor vẫn bằng record gốc.

Nếu accessor tường minh trả về một snapshot khác:

```java
record SearchQuery(List<String> tags) {
    SearchQuery {
        tags = List.copyOf(tags);
    }

    public List<String> tags() {
        return List.copyOf(tags);
    }
}
```

Copy invariant vẫn được giữ vì hai danh sách có cùng các phần tử theo `List.equals`. Tuy nhiên, khi constructor đã lưu một danh sách không thể sửa, accessor tự sinh thường đã đủ; chỉ viết lại accessor nếu có lý do cụ thể.

Lưu ý `List.copyOf` là snapshot nông. Nếu các phần tử là object mutable, bản sao danh sách vẫn chứa các tham chiếu đến chính những object đó. Muốn trạng thái sâu ổn định, cần dùng phần tử bất biến hoặc sao chép sâu theo cấu trúc dữ liệu.

## 5. Array component cần xử lý đồng bộ với equals và hashCode

Mảng Java không ghi đè `Object.equals` và `Object.hashCode`. Vì vậy record mặc định chứa mảng so sánh component theo identity của mảng, không theo nội dung.

Nếu accessor trả một bản sao mảng, copy invariant sẽ bị phá vỡ khi vẫn dùng `equals` mặc định:

```java
record BytePayload(byte[] bytes) {
    public byte[] bytes() {
        return bytes.clone();
    }
}

BytePayload original = new BytePayload(new byte[] {1, 2, 3});
BytePayload copy = new BytePayload(original.bytes());

System.out.println(original.equals(copy)); // false
```

Accessor tạo ra mảng mới. Canonical constructor lưu tham chiếu mảng mới đó. Hai mảng có nội dung giống nhau nhưng khác identity, nên `Object.equals` của mảng trả về `false`.

Nếu mảng đại diện cho một giá trị theo nội dung, hãy kết hợp bốn việc:

- Sao chép mảng đầu vào trong constructor.
- Trả bản sao từ accessor.
- Dùng `Arrays.equals` để so sánh nội dung.
- Dùng `Arrays.hashCode` để tạo mã băm nhất quán.

Ví dụ đầy đủ:

```java
import java.util.Arrays;
import java.util.Objects;

record BytePayload(byte[] bytes) {
    BytePayload {
        bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }

    public byte[] bytes() {
        return bytes.clone();
    }

    @Override
    public boolean equals(Object other) {
        return this == other
            || (other instanceof BytePayload that
                && Arrays.equals(this.bytes, that.bytes));
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(bytes);
    }
}
```

Kiểm tra invariant:

```java
byte[] source = {1, 2, 3};
BytePayload original = new BytePayload(source);

source[0] = 99; // Không đổi trạng thái nội bộ.

byte[] exposed = original.bytes();
exposed[1] = 88; // Chỉ sửa bản sao accessor trả về.

BytePayload copy = new BytePayload(original.bytes());

System.out.println(original.equals(copy)); // true
System.out.println(original.hashCode() == copy.hashCode()); // true
System.out.println(Arrays.toString(original.bytes())); // [1, 2, 3]
```

Ở đây accessor trả mảng mới, nhưng `Arrays.equals` so sánh nội dung. Bản sao tạo qua canonical constructor vì thế vẫn bằng record gốc. `hashCode` cũng dùng cùng ngữ nghĩa nội dung, đáp ứng hợp đồng `equals`/`hashCode`.

Với mảng lồng nhau, cần dùng cặp `Arrays.deepEquals` và `Arrays.deepHashCode` tương ứng, đồng thời sao chép sâu nếu muốn bảo vệ cả các mảng con.

## 6. Không dùng accessor để che dữ liệu nhạy cảm

Accessor không phải API redaction. Trả về chuỗi đã che có thể khiến bản sao được tạo từ accessor không còn bằng record gốc:

```java
record Credentials(String username, String password) {
    public String password() {
        return "<redacted>";
    }
}

Credentials original =
    new Credentials("linh", "secret-value");
Credentials copy =
    new Credentials(original.username(), original.password());

System.out.println(original.equals(copy)); // false
```

Record gốc lưu mật khẩu thật; bản sao lưu chuỗi `"<redacted>"`. Ngoài việc phá copy invariant, cách này còn khiến mã nghiệp vụ không thể lấy giá trị thật qua accessor.

Hãy giữ accessor đúng hợp đồng dữ liệu và tạo một kiểu riêng cho mục đích hiển thị hoặc logging:

```java
record Credentials(String username, String password) {}
record CredentialsLogView(String username, String passwordStatus) {}

CredentialsLogView toLogView(Credentials credentials) {
    return new CredentialsLogView(
        credentials.username(),
        "REDACTED"
    );
}
```

Log view chỉ chứa thông tin được phép hiển thị. Record dữ liệu vẫn giữ accessor phản ánh component của nó; không dùng accessor để vừa che bí mật vừa đóng vai trò đọc dữ liệu.

## 7. Copy invariant và equals/hashCode tùy chỉnh

Record cho phép khai báo tường minh `equals` và `hashCode`. Khi tùy chỉnh, cần bảo đảm:

1. Record mới được tạo từ các accessor của record gốc bằng record gốc theo `equals`.
2. Nếu hai record bằng nhau theo `equals` thì chúng có cùng `hashCode`.
3. Equality phản ánh đúng ý nghĩa giá trị của record, bao gồm quy tắc cho từng component.

Accessor trả bản sao không tự động phá invariant. Vấn đề chỉ xảy ra khi bản sao đó được xem là khác giá trị theo `equals` đang dùng. Ví dụ với mảng, bản sao có identity khác nhưng nội dung giống nhau; vì vậy cần định nghĩa equality theo nội dung.

Tương tự, nếu accessor chuyển đổi dữ liệu, có thể thiết kế `equals` theo cùng dạng chuẩn hóa. Tuy nhiên, cách này làm hợp đồng phức tạp hơn. Trong hầu hết trường hợp, nên chuẩn hóa trong canonical constructor để accessor trả thẳng giá trị chuẩn hóa đã lưu.

## 8. Cách kiểm thử copy invariant

Với mỗi record, tạo một bản sao bằng cách gọi canonical constructor từ accessor và kiểm tra equality:

```java
record Person(String name, int age) {}

Person original = new Person("Linh", 25);
Person copy = new Person(original.name(), original.age());

if (!original.equals(copy)) {
    throw new AssertionError("Record copy invariant violated");
}

if (original.hashCode() != copy.hashCode()) {
    throw new AssertionError("Equal records must have equal hash codes");
}
```

Với record có nhiều component, cần đưa tất cả accessor vào constructor theo đúng thứ tự khai báo component. Kiểm thử nên bao gồm:

- Giá trị biên và trường hợp `null` nếu constructor cho phép.
- Dữ liệu đã được chuẩn hóa trong compact/canonical constructor.
- Collection được snapshot và các phần tử bên trong.
- Array được sao chép trong constructor và accessor.
- Các accessor tường minh có trả dữ liệu tương đương với component không.
- `equals` và `hashCode` tùy chỉnh có cùng ngữ nghĩa hay không.

Copy invariant không thay thế các kiểm thử bất biến nghiệp vụ hoặc kiểm thử bảo mật. Nó tập trung xác minh tính nhất quán giữa accessor, constructor và equality.

## 9. Những nhầm lẫn cần tránh

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| Copy invariant yêu cầu bản sao phải cùng instance với record gốc. | **Sai** | Bản sao là instance mới nhưng phải bằng nhau theo `equals`. |
| Accessor tự sinh thường trả về component đã được constructor lưu. | **Đúng** | Với accessor mặc định, giá trị đọc phản ánh component. |
| Có thể chuẩn hóa dữ liệu trong accessor mà không cần xem xét `equals`. | **Sai** | Bản sao tạo từ accessor có thể khác giá trị đã lưu. |
| Chuẩn hóa trong compact constructor thường giúp giữ invariant. | **Đúng** | Giá trị được chuẩn hóa trước khi lưu; accessor trả đúng giá trị đó. |
| Accessor trả bản sao luôn vi phạm copy invariant. | **Sai** | Bản sao vẫn hợp lệ nếu equality của component xem nó là cùng giá trị. |
| Array accessor trả clone vẫn tương thích với `equals` mặc định. | **Sai** | Mảng so sánh theo identity; cần custom equality theo nội dung nếu đó là yêu cầu. |
| Ghi đè accessor để che password là cách redaction phù hợp. | **Sai** | Nó phá hợp đồng đọc component và có thể phá copy invariant. |
| Copy invariant bảo đảm object graph bất biến sâu. | **Sai** | Nó chỉ quy định quan hệ giữa accessor, constructor và equality. |

## 10. Checklist thiết kế record giữ copy invariant

1. Accessor có trả giá trị đại diện cho component tương ứng không?
2. Có chuẩn hóa dữ liệu trong canonical/compact constructor thay vì trong accessor không?
3. Tạo record mới từ toàn bộ accessor có cho kết quả bằng record gốc không?
4. Nếu accessor trả defensive copy, kiểu component có equality theo nội dung hay identity?
5. Với mảng, đã kết hợp defensive copy, `Arrays.equals` và `Arrays.hashCode` chưa?
6. Với collection, snapshot có giữ cùng nội dung và phần tử có bất biến không?
7. Nếu tùy chỉnh `equals`, `hashCode`, hai phương thức có nhất quán và phản ánh cùng một semantics không?
8. Có đang dùng accessor để redaction hoặc trả một biểu diễn khác dữ liệu component không?

**Ghi nhớ:** Copy invariant yêu cầu một record có thể được tái tạo từ các accessor của chính nó mà vẫn bằng record ban đầu theo `equals`. Hãy chuẩn hóa dữ liệu trong constructor; chỉ trả defensive copy khi equality vẫn nhận diện bản sao là cùng giá trị; với array, đồng bộ accessor, constructor, `equals` và `hashCode`. Đây là nền tảng để record giữ đúng vai trò carrier dữ liệu minh bạch trong Java hiện đại.

## Tài liệu chính thức

- [Java SE 26 API — `java.lang.Record`, record component accessors và copy invariant](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Record.html).
- [Java Language Specification, Section 8.10 — Record Classes và record component accessors](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10).
- [JEP 395 — Records, tính năng chính thức trong Java 16](https://openjdk.org/jeps/395).
