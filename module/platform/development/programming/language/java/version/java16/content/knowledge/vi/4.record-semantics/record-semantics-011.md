# Accessor tường minh và quy tắc bảo toàn giá trị quan sát được

**Module:** `JAVA_VERSION_JAVA16`  
**Chương:** Ngữ nghĩa record  
**Áp dụng:** Java 16 trở lên, bao gồm Java hiện đại.

Mỗi record component có một accessor công khai do compiler tự sinh. Ví dụ, component `name` tạo ra phương thức `name()` để đọc giá trị. Record cũng cho phép khai báo accessor tường minh khi cần bảo vệ dữ liệu mutable, chẳng hạn trả về bản sao của mảng.

Khi tự viết accessor, cần giữ đúng vai trò của nó: cung cấp giá trị tương ứng với component. Một record được kỳ vọng có tính minh bạch (*transparent carrier*): nếu tạo một bản sao bằng cách truyền các giá trị lấy từ accessor của record ban đầu vào canonical constructor, bản sao đó phải bằng record ban đầu theo `equals`. Đây là **copy invariant** của record.

Bài học tập trung vào cách dùng accessor tường minh mà vẫn bảo toàn ngữ nghĩa giá trị, đặc biệt khi chuẩn hóa dữ liệu và bảo vệ mảng.

## 1. Accessor được sinh tự động từ record component

Với khai báo:

```java
record User(String username, int age) {}
```

Compiler cung cấp hai accessor công khai có chữ ký tương đương:

```java
public String username()
public int age()
```

Cách sử dụng:

```java
User user = new User("linh", 25);

System.out.println(user.username()); // linh
System.out.println(user.age());      // 25
```

Accessor có các đặc điểm:

- Tên phương thức trùng với tên component.
- Không nhận tham số.
- Có kiểu trả về giống kiểu component.
- Là phương thức `public` để component có thể được đọc từ bên ngoài.
- Khi không khai báo tường minh, accessor trả về giá trị component được lưu trong record.

Record có thể khai báo tường minh accessor trong thân class. Accessor tường minh phải giữ đúng tên, không có tham số, có kiểu trả về tương ứng và phải là `public`:

```java
record User(String username, int age) {
    public String username() {
        return username;
    }
}
```

Trong ví dụ này, accessor tường minh vẫn trả về đúng giá trị đã lưu. Hành vi quan sát được của record không thay đổi.

## 2. Accessor là một phần của hợp đồng biểu diễn dữ liệu

Record được thiết kế để component mô tả dữ liệu của instance. Accessor công khai là cách người dùng lấy các giá trị đó. Vì vậy, accessor không nên âm thầm trả về một giá trị khác với component được lưu.

Ví dụ không nên dùng accessor để chuẩn hóa:

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

Record ban đầu lưu `"  Linh  "`, còn bản sao được tạo từ accessor chỉ lưu `"Linh"`. Với `equals` mặc định, hai giá trị component được lưu khác nhau nên hai record không bằng nhau.

Điều này vi phạm kỳ vọng copy invariant: nếu tạo một record mới bằng cách truyền kết quả accessor của record ban đầu vào canonical constructor, record mới phải bằng record ban đầu theo `equals`.

**Cách đúng:** chuẩn hóa dữ liệu khi tạo record, trong canonical constructor, để trường component lưu ngay giá trị chuẩn hóa. Khi đó accessor tự sinh trả về đúng giá trị đã lưu:

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

Compact constructor nhận các tham số component, cho phép kiểm tra và gán lại tham số trước khi compiler gán chúng vào các trường component. Vì vậy đây là vị trí phù hợp để xác thực, chuẩn hóa và thiết lập bất biến.

## 3. Copy invariant là gì?

Copy invariant mô tả tính nhất quán giữa accessor, canonical constructor và `equals`:

1. Đọc từng component của record bằng accessor công khai.
2. Truyền các giá trị vừa đọc vào canonical constructor để tạo record mới cùng kiểu.
3. Record mới phải bằng record ban đầu theo `equals`.

Ví dụ:

```java
record Coordinates(int x, int y) {}

Coordinates point = new Coordinates(10, 20);
Coordinates copy = new Coordinates(point.x(), point.y());

System.out.println(point.equals(copy)); // true
```

Đây là một kỳ vọng quan trọng đối với record vì người dùng có thể dựa vào component để sao chép, chuyển đổi hoặc tái tạo giá trị. Accessor trả về dữ liệu đã bị biến đổi theo cách không tương thích với `equals` sẽ làm record khó dự đoán.

Copy invariant không có nghĩa hai biến tham chiếu phải trỏ đến cùng instance. Bản sao là một instance khác, nhưng phải bằng nhau theo giá trị:

```java
System.out.println(point == copy);      // false
System.out.println(point.equals(copy)); // true
```

## 4. Khi nào nên khai báo accessor tường minh?

Một trường hợp điển hình là component tham chiếu đến object mutable mà record không muốn để bên gọi sửa trực tiếp. Accessor có thể trả về bản sao phòng vệ (*defensive copy*).

Ví dụ với mảng:

```java
record BytePayload(byte[] bytes) {
    public byte[] bytes() {
        return bytes.clone();
    }
}
```

Accessor này không trả tham chiếu trực tiếp đến mảng nội bộ. Bên gọi nhận một mảng mới và có thể sửa bản sao mà không sửa trực tiếp mảng được lưu trong record.

Tuy nhiên, chỉ ghi đè accessor là chưa đủ để tạo một record bất biến:

```java
record BytePayload(byte[] bytes) {
    public byte[] bytes() {
        return bytes.clone();
    }
}

byte[] source = {1, 2, 3};
BytePayload payload = new BytePayload(source);

source[0] = 99; // Vẫn sửa được mảng nội bộ vì constructor chưa sao chép.
```

Mảng đầu vào vẫn là cùng tham chiếu được lưu trong component. Muốn bảo vệ cả đầu vào lẫn đầu ra, cần sao chép ở constructor và accessor.

## 5. Defensive copy cho array cần giữ cả copy invariant

Khi component là mảng, có một điểm đặc biệt: mảng Java dùng `Object.equals` và `Object.hashCode` theo identity, không theo nội dung. Nếu accessor trả bản sao mảng, canonical constructor lại sao chép mảng đó, thì hai record sẽ giữ hai mảng khác tham chiếu. `equals` mặc định sẽ xem chúng không bằng nhau.

Vì vậy, nếu mảng đại diện cho một giá trị được so sánh theo nội dung, hãy triển khai đồng bộ:

- Constructor sao chép mảng đầu vào.
- Accessor trả về bản sao mảng.
- `equals` so sánh nội dung mảng.
- `hashCode` tính từ nội dung mảng tương ứng.

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

Kiểm tra:

```java
byte[] input = {1, 2, 3};
BytePayload payload = new BytePayload(input);

input[0] = 99; // Không ảnh hưởng mảng nội bộ.

byte[] returned = payload.bytes();
returned[1] = 88; // Chỉ sửa bản sao được trả về.

System.out.println(Arrays.toString(payload.bytes())); // [1, 2, 3]

BytePayload copy = new BytePayload(payload.bytes());
System.out.println(payload.equals(copy)); // true
System.out.println(payload.hashCode() == copy.hashCode()); // true
```

Trong thiết kế này:

- Đầu vào được sao chép trước khi lưu.
- Mảng nội bộ không bị lộ qua accessor.
- Equality theo nội dung và hash theo cùng nội dung.
- Bản sao được tạo từ accessor vẫn bằng record gốc, nên copy invariant được giữ.

Đây là ví dụ hợp lệ của accessor tường minh vì giá trị trả về là bản sao có cùng nội dung theo ngữ nghĩa `equals` mà record đã định nghĩa.

## 6. Nếu component là collection, ưu tiên snapshot trong constructor

Với collection chứa phần tử immutable như `String`, thường không cần viết accessor tường minh. Hãy tạo snapshot không thể sửa trong compact constructor:

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
```

Accessor tự sinh trả về danh sách snapshot không thể sửa:

```java
List<String> source = new java.util.ArrayList<>(List.of("java"));
SearchQuery query = new SearchQuery(source);

source.add("records");
System.out.println(query.tags()); // [java]

// query.tags().add("streams"); // UnsupportedOperationException
```

Nếu cần khai báo accessor tường minh để làm rõ hợp đồng trả về snapshot, nó có thể trả về `List.copyOf` của component:

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

Vì `List.equals` so sánh nội dung và `List.copyOf` giữ cùng các phần tử, bản sao tạo từ accessor vẫn bằng record gốc. Tuy nhiên, nếu constructor đã lưu danh sách không thể sửa, accessor tự sinh thường đã đủ; viết lại accessor chỉ nên làm khi có lý do rõ ràng.

Lưu ý `List.copyOf` là sao chép nông. Nếu phần tử là object mutable, bên ngoài vẫn có thể sửa trạng thái của phần tử đó. Khi ấy cần dùng phần tử immutable hoặc tạo snapshot sâu phù hợp với miền dữ liệu.

## 7. Tránh dùng accessor để che hoặc thay đổi dữ liệu nghiệp vụ

Accessor không phải ranh giới bảo mật và cũng không nên trở thành nơi biến đổi ngữ nghĩa của component.

Ví dụ, accessor trả về chuỗi đã che:

```java
record Credentials(String username, String password) {
    public String password() {
        return "<redacted>";
    }
}
```

Đây không phải cách an toàn để bảo vệ password:

- Canonical constructor và trường component vẫn lưu password gốc.
- Accessor không thể cung cấp giá trị gốc cho mã nghiệp vụ cần xác thực.
- Tạo bản sao qua accessor sẽ tạo record có password là `"<redacted>"`, không bằng record gốc theo `equals` mặc định.
- Một component nhạy cảm vẫn có thể bị lộ qua những đường truy cập hoặc log khác.

Hãy tách trách nhiệm: accessor trả về component theo hợp đồng dữ liệu; logging hoặc giao diện hiển thị dùng một biểu diễn đã được redaction riêng. Không dùng accessor để thay thế cơ chế bảo vệ bí mật.

## 8. Những lưu ý về accessor tường minh

| Việc cần làm | Khuyến nghị | Lý do |
| --- | --- | --- |
| Trả về component bất biến như `String`, `int`, `LocalDate` | Dùng accessor tự sinh | Không cần thêm logic. |
| Chuẩn hóa dữ liệu đầu vào | Làm trong canonical/compact constructor | Giá trị lưu và giá trị đọc nhất quán. |
| Bảo vệ mảng mutable | Sao chép ở constructor và accessor; định nghĩa `equals`/`hashCode` theo nội dung nếu đó là value | Bảo vệ dữ liệu và copy invariant. |
| Bảo vệ collection chứa phần tử immutable | Snapshot bằng `List.copyOf`, `Set.copyOf`, `Map.copyOf` trong constructor | Accessor tự sinh có thể trả collection không thể sửa. |
| Che dữ liệu nhạy cảm | Dùng log view hoặc DTO hiển thị riêng | Accessor không phải ranh giới bảo mật. |
| Trả dữ liệu đã định dạng khác component | Tránh nếu làm thay đổi equality quan sát được | Có thể phá copy invariant và gây bất ngờ. |

Một accessor tường minh cũng không nên tạo trạng thái phụ để cache một giá trị không liên quan đến component. Record không cho phép khai báo instance field tùy ý; trạng thái biểu diễn của record cần xuất phát từ các component.

## 9. Những nhầm lẫn cần tránh

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| Mọi record component đều có accessor công khai do compiler sinh nếu không khai báo tường minh. | **Đúng** | Tên và kiểu trả về tương ứng với component. |
| Accessor tường minh có thể đổi tên hoặc nhận thêm tham số. | **Sai** | Nó phải giữ chữ ký accessor của component. |
| Có thể chuẩn hóa dữ liệu trong accessor mà không ảnh hưởng record. | **Sai** | Giá trị accessor dùng để tái tạo bản sao có thể khác component đã lưu. |
| Chuẩn hóa trong compact constructor giúp accessor tự sinh trả giá trị chuẩn hóa. | **Đúng** | Component được lưu sau khi tham số constructor được chuẩn hóa. |
| Accessor trả bản sao mảng luôn tương thích với `equals` mặc định. | **Sai** | Mảng mặc định so sánh theo identity; cần equality/hash theo nội dung nếu đó là semantics mong muốn. |
| Chỉ sao chép mảng ở accessor là đủ bảo vệ record. | **Sai** | Mảng đầu vào vẫn có thể bị sửa nếu constructor không sao chép. |
| `List.copyOf` bảo vệ sâu mọi object bên trong danh sách. | **Sai** | Nó bảo vệ cấu trúc collection, không sao chép sâu phần tử. |
| Copy invariant yêu cầu bản sao cùng instance với record gốc. | **Sai** | Bản sao là instance khác nhưng phải bằng nhau theo `equals`. |

## 10. Checklist khi viết accessor tường minh

1. Accessor có đúng tên, không tham số, kiểu trả về tương ứng và là `public` không?
2. Giá trị trả về có đại diện đúng component đã lưu không?
3. Nếu accessor trả bản sao, bản sao có bằng component theo ngữ nghĩa `equals` không?
4. Tạo record mới từ các accessor có bảo toàn copy invariant không?
5. Nếu component mutable, constructor đã sao chép đầu vào chưa?
6. Accessor có trả tham chiếu mutable nội bộ ra ngoài không?
7. Nếu tùy chỉnh `equals`, `hashCode`, hai phương thức có nhất quán không?
8. Có đang dùng accessor để chuẩn hóa, che dữ liệu hoặc thay đổi ngữ nghĩa mà lẽ ra nên xử lý ở constructor/log view không?

**Ghi nhớ:** Accessor tường minh hữu ích khi cần trả bản sao phòng vệ, nhưng nó phải giữ hợp đồng component và copy invariant. Hãy chuẩn hóa dữ liệu trong canonical/compact constructor; với mảng, kết hợp defensive copy ở cả constructor và accessor cùng `equals`/`hashCode` theo nội dung; với collection chứa phần tử immutable, ưu tiên snapshot trong constructor và dùng accessor tự sinh.

## Tài liệu chính thức

- [Java SE 26 API — `java.lang.Record`, accessor methods và copy invariant](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Record.html).
- [Java Language Specification, Section 8.10 — Record Classes và record component accessors](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10).
- [JEP 395 — Records, tính năng chính thức trong Java 16](https://openjdk.org/jeps/395).
