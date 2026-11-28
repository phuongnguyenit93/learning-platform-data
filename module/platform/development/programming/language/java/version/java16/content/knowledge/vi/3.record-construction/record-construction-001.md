# Canonical constructor và sự tương ứng với thứ tự component

> **Chương:** Khởi tạo record  
> **Học phần:** `JAVA_VERSION_JAVA16` — tìm hiểu các cải tiến từ Java 16 vẫn được sử dụng trong Java hiện đại. Bài này tập trung vào cách khởi tạo `record` ổn định, không sử dụng tính năng preview hay kỹ thuật đã lỗi thời.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **canonical constructor** (constructor chuẩn) của `record` được xác định từ danh sách component như thế nào.
- Phân biệt constructor chuẩn do trình biên dịch sinh, constructor chuẩn khai báo tường minh và **compact constructor**.
- Viết kiểm tra dữ liệu, chuẩn hóa giá trị và gán đầy đủ field khi khởi tạo record.
- Nhận diện lỗi do sai **thứ tự, kiểu hoặc tên tham số**; phân biệt constructor chuẩn với constructor nạp chồng.
- Tránh thay đổi thứ tự component gây sai lệch dữ liệu khi gọi constructor theo vị trí.

## 1. Record có canonical constructor để làm gì?

Từ Java 16, `record` là tính năng chính thức của ngôn ngữ để biểu diễn một nhóm dữ liệu có cấu trúc cố định. Ví dụ:

```java
public record OrderLine(String sku, int quantity) {}
```

Trong phần `(String sku, int quantity)`, `sku` và `quantity` được gọi là các **record component**. Từ khai báo này, Java cung cấp các thành phần tương ứng:

- Hai field `private final` lưu dữ liệu (`sku`, `quantity`).
- Hai phương thức truy cập `public`: `sku()` và `quantity()`.
- Các phương thức `equals()`, `hashCode()` và `toString()` có hành vi dựa trên giá trị component.
- Một **canonical constructor** có tham số tương ứng với mọi component.

Nếu không tự khai báo constructor chuẩn, trình biên dịch tạo constructor có hành vi tương đương với ý tưởng sau:

```java
public record OrderLine(String sku, int quantity) {
    public OrderLine(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }
}
```

Hai đoạn trên là **hai cách khai báo thay thế nhau**; không đặt cả hai phiên bản `OrderLine` trong cùng chương trình. Trong ví dụ, một lần tạo record diễn ra như sau:

```java
OrderLine line = new OrderLine("BK-001", 2);

System.out.println(line.sku());      // BK-001
System.out.println(line.quantity()); // 2
```

Constructor chuẩn là đường khởi tạo tương ứng trực tiếp với *hình dạng dữ liệu* đã mô tả trong record header. Nó tồn tại kể cả khi phần thân record để trống.

## 2. Quy tắc tương ứng: vị trí, kiểu và tên

Với khai báo:

```java
public record OrderLine(String sku, int quantity) {}
```

Các tham số của canonical constructor được suy ra **theo đúng thứ tự component trong header**:

| Vị trí | Component trong header | Tham số của canonical constructor | Field nhận giá trị |
| --- | --- | --- | --- |
| 1 | `String sku` | `String sku` | `this.sku` |
| 2 | `int quantity` | `int quantity` | `this.quantity` |

Vì vậy, chữ ký constructor chuẩn có thứ tự kiểu `(String, int)`, tương ứng với lời gọi `new OrderLine("BK-001", 2)`.

Có hai lớp quy tắc cần phân biệt:

1. **Với lời gọi `new`:** đối số được truyền **theo vị trí**, Java không có cú pháp truyền đối số theo tên như `sku = ...` hay `quantity = ...`. `new OrderLine(2, "BK-001")` không khớp constructor chuẩn `(String, int)`.
2. **Với constructor chuẩn tường minh:** mỗi tham số phải có **đúng tên và đúng kiểu** của component ở cùng vị trí. Không thể chỉ giữ đúng kiểu mà đổi tên tham số.

Ví dụ sau không hợp lệ:

```java
// SAI: tham số cùng vị trí không trùng tên component trong header.
public record Point(int x, int y) {
    public Point(int y, int x) {
        this.x = x;
        this.y = y;
    }
}
```

Vì cả hai component đều kiểu `int`, chữ ký vẫn là `(int, int)`; constructor này được nhận diện là ứng viên canonical nhưng vi phạm yêu cầu về **tên tham số ở từng vị trí**. Chỉ đổi tên tham số không tạo ra một constructor nạp chồng khác.

Cũng cần chú ý trường hợp **hai component cùng kiểu** ở phía gọi:

```java
record FullName(String firstName, String lastName) {}

FullName a = new FullName("Minh", "Trần"); // đúng ý nghĩa
FullName b = new FullName("Trần", "Minh"); // biên dịch được, dữ liệu bị đảo
```

Trình biên dịch không thể nhận biết người dùng đã đảo ý nghĩa của hai chuỗi. Đây là lý do thứ tự component là một phần quan trọng của API và cần nhất quán từ lúc thiết kế.

## 3. Tự viết canonical constructor dạng đầy đủ

Khai báo constructor chuẩn tường minh khi cần kiểm tra đầu vào, chuẩn hóa giá trị hoặc xử lý việc lưu dữ liệu:

```java
public record OrderLine(String sku, int quantity) {

    public OrderLine(String sku, int quantity) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        this.sku = sku.strip();
        this.quantity = quantity;
    }
}
```

Cách sử dụng:

```java
OrderLine line = new OrderLine("  BK-001  ", 2);

System.out.println(line.sku());      // BK-001
System.out.println(line.quantity()); // 2

// new OrderLine("", 2);  -> IllegalArgumentException
// new OrderLine("A", 0); -> IllegalArgumentException
```

Quy tắc với constructor chuẩn dạng đầy đủ:

- Danh sách tham số phải tương ứng với header về **số lượng, kiểu, thứ tự và tên**.
- Bạn phải đảm bảo **mọi component field được khởi tạo** trên các luồng chạy kết thúc bình thường; các field này là `final`. Ví dụ trên gán cả `this.sku` và `this.quantity`.
- **Thứ tự câu lệnh gán** không bắt buộc giống thứ tự header. Điều bắt buộc là đúng field nhận đúng giá trị và tất cả field được khởi tạo hợp lệ.
- Constructor chuẩn khai báo tường minh phải có mức truy cập **ít nhất bằng** record. Vì `OrderLine` là `public record`, constructor chuẩn của nó phải `public`.
- Constructor chuẩn không khai báo tham số kiểu riêng, không có mệnh đề `throws`, không gọi constructor khác bằng `this(...)` hoặc `super(...)` một cách tường minh. Việc ném ngoại lệ không kiểm tra như `IllegalArgumentException` trong thân constructor vẫn hợp lệ.

Ví dụ gán thiếu field sẽ gây lỗi biên dịch:

```java
// SAI: field y chưa được khởi tạo.
record Point(int x, int y) {
    Point(int x, int y) {
        this.x = x;
    }
}
```

## 4. Compact constructor: cùng canonical constructor, ít mã hơn

Khi chỉ cần kiểm tra hoặc chuẩn hóa dữ liệu, dạng **compact** thường dễ đọc hơn:

```java
public record OrderLine(String sku, int quantity) {

    public OrderLine {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        sku = sku.strip();
    }
}
```

`public OrderLine { ... }` là **compact canonical constructor**, không có danh sách tham số tường minh. Java tự lấy tham số `sku` và `quantity` từ record header **đúng thứ tự đã khai báo**. Sau khi thân constructor kết thúc bình thường, trình biên dịch tự thực hiện việc gán tương ứng:

```java
// Mô tả tác dụng của phần được trình biên dịch bổ sung,
// KHÔNG đặt các dòng này vào thân compact constructor.
this.sku = sku;
this.quantity = quantity;
```

Vì thế, trong thân compact constructor:

- Tên không kèm `this` như `sku` chỉ **tham số ngầm**, có thể được kiểm tra và gán lại để chuẩn hóa.
- Không viết `this.sku = sku` hoặc `this.quantity = quantity`: compact constructor không cho phép tự gán vào component field.
- Không đặt câu lệnh `return` hay gọi tường minh `this(...)` / `super(...)`.
- Các field được gán ngầm **theo thứ tự khai báo component**, sau khi thân constructor chạy xong.

| Đặc điểm | Canonical dạng đầy đủ | Compact canonical |
| --- | --- | --- |
| Khai báo tham số | Viết đủ tham số theo header | Không viết danh sách tham số |
| Kiểm tra, chuẩn hóa | Có | Có |
| Gán component field | Tự gán đầy đủ bằng `this.field = ...` | Trình biên dịch tự gán sau thân constructor |
| Khả năng cập nhật tham số | Có thể dùng giá trị xử lý khi gán field | Có thể gán lại tham số ngầm |
| Phù hợp nhất khi | Muốn điều khiển tường minh cách khởi tạo từng field | Chỉ cần ràng buộc và chuẩn hóa dữ liệu |

**Chỉ chọn một cách khai báo canonical constructor trong cùng một record.** Không thể khai báo cả bản đầy đủ và bản compact có chữ ký chuẩn tương đương.

## 5. Constructor nạp chồng không thay thế constructor chuẩn

Một record có thể có constructor khác với danh sách tham số của canonical constructor. Khi đó, constructor bổ sung phải **ủy quyền đến một constructor khác của chính record qua `this(...)`**, sao cho quá trình khởi tạo cuối cùng đi qua canonical constructor.

```java
public record Ticket(String code, int seat) {

    // Constructor phụ: chữ ký (int, String).
    public Ticket(int seat, String code) {
        this(code, seat);
    }
}
```

Cả hai lời gọi đều hợp lệ:

```java
Ticket a = new Ticket("A-101", 7); // canonical: (String, int)
Ticket b = new Ticket(7, "A-101"); // constructor phụ: (int, String)

System.out.println(a.equals(b)); // true
```

Trong ví dụ này, constructor chuẩn `(String, int)` vẫn được sinh ngầm vì chưa được khai báo tường minh. Constructor `(int, String)` là **nạp chồng**, không phải một phiên bản canonical với thứ tự bị đảo.

Phân biệt hai tình huống:

- Đảo **kiểu** tham số thành chữ ký khác (ví dụ `(int, String)` thay `(String, int)`) có thể tạo constructor nạp chồng, nhưng phải dùng `this(...)` để đưa dữ liệu về canonical constructor.
- Chỉ đảo **tên** của các tham số cùng kiểu (ví dụ `(int y, int x)` thay `(int x, int y)`) vẫn là chữ ký `(int, int)`, nên không tạo được overload; nó vi phạm quy tắc của canonical constructor.

Nên ưu tiên một thứ tự đối số dễ hiểu và nhất quán. Constructor nạp chồng đảo thứ tự chỉ thích hợp khi có lý do rõ ràng; nếu không, nó khiến lời gọi khó đọc và dễ nhầm.

## 6. Ví dụ thực tế: kiểm tra bất biến và sao chép phòng vệ

Record có các field `final`, nhưng nếu một component trỏ đến đối tượng có thể thay đổi thì dữ liệu bên trong đối tượng đó **chưa chắc bất biến**. Canonical constructor là nơi phù hợp để bảo vệ dữ liệu đầu vào.

```java
import java.util.List;
import java.util.Objects;

public record UserProfile(String username, List<String> roles) {

    public UserProfile {
        if (username == null || username.isBlank()) {
            throw new IllegalArgumentException("username is required");
        }

        username = username.strip();
        roles = List.copyOf(Objects.requireNonNull(roles, "roles"));
    }
}
```

Sử dụng:

```java
import java.util.ArrayList;
import java.util.List;

List<String> inputRoles = new ArrayList<>(List.of("READER"));
UserProfile user = new UserProfile("  linh  ", inputRoles);

inputRoles.add("ADMIN");           // sửa danh sách đầu vào
System.out.println(user.username()); // linh
System.out.println(user.roles());    // [READER]

// user.roles().add("ADMIN"); // UnsupportedOperationException
```

`List.copyOf(...)` tạo một danh sách không cho sửa qua những thao tác thay đổi thông thường và tách dữ liệu của record khỏi danh sách đầu vào có thể bị chỉnh sửa. Đây là **bất biến nông**: nếu danh sách chứa các đối tượng vốn có thể thay đổi, trạng thái bên trong từng đối tượng vẫn cần được cân nhắc riêng.

Trong trường hợp này, compact constructor bảo đảm cả hai điều kiện trước khi trình biên dịch gán các tham số đã chuẩn hóa cho component field theo thứ tự `username`, rồi `roles`.

## 7. Thứ tự component ảnh hưởng đến API và tích hợp

Giả sử ban đầu khai báo:

```java
record Metric(String name, long value) {}
Metric m = new Metric("requests", 100L);
```

Nếu đổi header thành `record Metric(long value, String name) {}`, canonical constructor tương ứng cũng đổi từ `(String, long)` sang `(long, String)`. Các chỗ gọi constructor cũ có thể không còn biên dịch, mã đã biên dịch trước đó cũng có thể không còn tương thích nhị phân.

Với các component cùng kiểu, đổi thứ tự còn nguy hiểm hơn vì lời gọi cũ có thể **vẫn biên dịch nhưng diễn giải sai dữ liệu**. Do đó:

- Xem danh sách component và thứ tự của chúng là một phần của hợp đồng API.
- Khi sửa cấu trúc record, kiểm tra lại các lệnh `new`, ánh xạ dữ liệu và những công cụ tạo đối tượng dựa vào thứ tự tham số.
- Ưu tiên tên component rõ nghĩa, đặt các thành phần theo thứ tự ổn định và chỉ thay đổi có chủ đích.

Java còn cung cấp API reflection để đọc thứ tự component đúng như header:

```java
for (var component : OrderLine.class.getRecordComponents()) {
    System.out.println(component.getName());
}
// sku
// quantity
```

`Class.getRecordComponents()` trả component theo **thứ tự khai báo**. Đây là cách đáng tin cậy khi công cụ cần xem cấu trúc record; không suy diễn thứ tự từ danh sách field do `getDeclaredFields()` trả về.

## 8. Các lỗi thường gặp

| Tình huống | Kết quả hoặc cách sửa |
| --- | --- |
| `new OrderLine(3, "BK-001")` với header `(String sku, int quantity)` | Sai thứ tự kiểu, không khớp canonical constructor tương ứng. |
| Viết `OrderLine(String code, int quantity)` làm canonical constructor cho header có `sku` | Cùng kiểu nhưng tên tham số đầu khác tên component; lỗi biên dịch. |
| Viết constructor dạng đầy đủ nhưng quên gán `this.quantity` | Component field `final` chưa được khởi tạo; lỗi biên dịch. |
| Gán `this.sku = sku` trong compact constructor | Bị cấm; hãy gán lại **tham số** `sku` nếu cần, để Java tự gán field. |
| Khai báo canonical constructor ít quyền truy cập hơn một `public record` | Lỗi biên dịch; khai báo constructor `public`. |
| Khai báo cả canonical dạng đầy đủ và compact cho cùng record | Trùng canonical constructor; chỉ giữ một dạng. |
| Cho rằng `final` làm mọi đối tượng component trở nên bất biến | Không đúng; cần sao chép phòng vệ với dữ liệu có thể thay đổi. |

## 9. Tự kiểm tra

**Câu 1.** Với `record Size(int width, int height) {}`, lời gọi nào đặt `width = 640`, `height = 480`?

```java
Size a = new Size(640, 480);
Size b = new Size(480, 640);
```

**Đáp án:** `a`. Constructor nhận theo **vị trí**: đối số thứ nhất ứng với `width`, thứ hai ứng với `height`. Vì cùng kiểu `int` nên cả hai lời gọi đều biên dịch.

**Câu 2.** Sửa compact constructor sau:

```java
// SAI
record Range(int start, int end) {
    Range {
        if (start > end) {
            throw new IllegalArgumentException("start > end");
        }
        this.start = start;
        this.end = end;
    }
}
```

**Đáp án:** Xóa hai dòng gán `this.start` và `this.end`. Java tự gán field khi thân compact constructor kết thúc bình thường:

```java
record Range(int start, int end) {
    Range {
        if (start > end) {
            throw new IllegalArgumentException("start > end");
        }
    }
}
```

**Câu 3.** Có thể bổ sung `Ticket(int seat, String code)` cho `record Ticket(String code, int seat)` hay không?

**Đáp án:** Có. Đó là constructor nạp chồng nếu nó ủy quyền bằng `this(code, seat)`. Canonical constructor vẫn gắn với thứ tự `(String code, int seat)` trong header.

## Ghi nhớ

**Canonical constructor là hình ảnh trực tiếp của record header ở cấp tham số: số lượng, kiểu, thứ tự và tên đều tương ứng với component.** Dạng đầy đủ yêu cầu tự khởi tạo các field; dạng compact để trình biên dịch tự gán field sau khi phần kiểm tra và chuẩn hóa kết thúc. Trong code gọi constructor, Java truyền đối số theo vị trí, vì vậy thứ tự component cần được thiết kế và duy trì cẩn thận.

## Tài liệu tham khảo

- [Java Language Specification, mục 8.10.4 — Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.4).
- [Oracle Java Language Updates — Record Classes](https://docs.oracle.com/en/java/javase/25/language/records.html).
- [JEP 395 — Records (được hoàn thiện trong Java 16)](https://openjdk.org/jeps/395).
