# serialVersionUID và tương thích lớp trong Java Serialization

Khi một đối tượng Java được ghi bằng `ObjectOutputStream`, dữ liệu có thể tồn tại trên đĩa hoặc truyền sang một chương trình khác lâu hơn vòng đời của phiên bản lớp đã tạo ra nó. Nếu cấu trúc lớp thay đổi trước khi dữ liệu được đọc lại bằng `ObjectInputStream`, Java phải quyết định liệu dữ liệu cũ còn đọc được với lớp hiện tại hay không. `serialVersionUID` là một phần của cơ chế kiểm tra đó.

Bài này áp dụng cho **Java Object Serialization** (`java.io.Serializable`), không phải cơ chế đổi phiên bản dữ liệu của JSON, JDBC, protobuf hay Java Records theo một giao thức khác.

## 1. Vai trò của serialVersionUID

Một lớp muốn tham gia Java Object Serialization thường triển khai marker interface `Serializable`. Khi ghi đối tượng, `ObjectOutputStream` ghi thông tin mô tả lớp (class descriptor), trong đó có tên lớp, mô tả các trường được tuần tự hóa và **serial version UID**. Khi đọc, Java tìm lớp hiện có tương ứng và so sánh UID trong stream với UID của lớp cục bộ.

- **UID khớp:** Java tiếp tục kiểm tra cấu trúc và giải mã dữ liệu theo các quy tắc tương thích. Khớp UID **không bảo đảm** mọi thay đổi lớp đều tương thích.
- **UID khác:** Với lớp `Serializable` thông thường, quá trình đọc thất bại với `java.io.InvalidClassException` (thông báo thường chứa “local class incompatible” cùng hai UID).
- **Lớp không tìm thấy:** Có thể nhận `ClassNotFoundException` trước khi có đối tượng; đặt cùng UID không giải quyết tên lớp/package sai hoặc thiếu classpath.

Khai báo được khuyến nghị:

```java
import java.io.Serializable;

public class Invoice implements Serializable {
    private static final long serialVersionUID = 1L;

    private String code;
    private long total;
}
```

`serialVersionUID` phải là trường có tên chính xác, kiểu `long`, `static` và `final`; thông thường dùng `private`. Đây là **metadata về phiên bản lớp**, không phải trường dữ liệu của từng đối tượng. UID không mã hóa, xác thực hay kiểm tra tính toàn vẹn dữ liệu. Không cần tăng UID sau *mọi* lần sửa mã nguồn; chỉ đổi có chủ đích khi quyết định rằng dữ liệu serialized từ phiên bản trước **không còn được phép/không thể** đọc theo cấu trúc mới.

Nếu **không** khai báo UID, JVM tính UID mặc định dựa trên một số đặc điểm của lớp (tên lớp, modifiers, interfaces, các trường/phương thức/constructor tham gia thuật toán). Vì vậy, những thay đổi mã nguồn tưởng như không liên quan đến dữ liệu có thể làm UID tính toán thay đổi và khiến việc đọc stream cũ thất bại. Khai báo UID tường minh giúp giữ ổn định hợp đồng tương thích nhưng không biến thay đổi cấu trúc nguy hiểm thành an toàn.

> Hai lớp đều ghi `serialVersionUID = 1L` không có nghĩa chúng hoán đổi đối tượng cho nhau được. Việc giải tuần tự hóa còn dựa vào tên lớp nhị phân, cấu trúc lớp và mô tả các trường.

## 2. Java thực sự lưu gì?

Với cách tuần tự hóa mặc định của một lớp `Serializable`, Java lưu các trường instance **không phải `static` và không phải `transient`** trong các lớp serializable thuộc đồ thị đối tượng, cộng thông tin nhận dạng lớp và tham chiếu đối tượng cần thiết. Các đối tượng được tham chiếu từ những trường được lưu cũng phải tuần tự hóa được; nếu không, lúc ghi có thể xảy ra `NotSerializableException`.

- `static` thuộc về lớp, nên không nằm trong trạng thái instance được lưu. Khi đọc, giá trị của nó lấy từ lớp/JVM đang chạy.
- `transient` chủ động loại trường khỏi dữ liệu mặc định. Khi đọc, trường nhận giá trị mặc định của Java (ví dụ `null`, `0`, `false`) trừ khi code khôi phục riêng.
- Constructor và field initializer của chính lớp `Serializable` **không được gọi/chạy để tạo lại trạng thái** trong quá trình giải tuần tự hóa mặc định. Constructor không đối số của superclass đầu tiên **không** Serializable được gọi, theo cơ chế của Java.
- `serialVersionUID` là trường `static final` nên không phải field instance được ghi; giá trị UID thuộc **class descriptor**.

`Serializable` không có phương thức bắt buộc. `writeObject`, `readObject`, `serialPersistentFields` hoặc `Externalizable` là các cơ chế tùy biến riêng, làm thay đổi hợp đồng dữ liệu và cần được quản lý cẩn thận.

## 3. Thực hành: ghi bằng phiên bản 1, đọc bằng phiên bản 2

Ta dùng hai bộ nguồn cùng tên lớp `Customer` và cùng UID, nhưng **biên dịch ở hai thư mục riêng và chạy trong hai tiến trình khác nhau**. Không đặt hai file `Customer.java` cùng một classpath khi chạy.

### Bước A — phiên bản 1 ghi file

Tạo `v1/Customer.java`:

```java
import java.io.Serializable;

public class Customer implements Serializable {
    private static final long serialVersionUID = 1L;

    String name;
    int points;

    Customer(String name, int points) {
        this.name = name;
        this.points = points;
    }
}
```

Tạo `v1/Writer.java`:

```java
import java.io.FileOutputStream;
import java.io.ObjectOutputStream;

public class Writer {
    public static void main(String[] args) throws Exception {
        try (ObjectOutputStream out =
                new ObjectOutputStream(new FileOutputStream("customer.ser"))) {
            out.writeObject(new Customer("Lan", 120));
        }
        System.out.println("Da ghi customer.ser");
    }
}
```

Biên dịch và chạy từ thư mục chứa `v1` (cần JDK 17+; Java 17 và 21 đều dùng được):

```bash
javac -encoding UTF-8 -d v1-classes v1/Customer.java v1/Writer.java
java -cp v1-classes Writer
```

Stdout:

```text
Da ghi customer.ser
```

Lệnh tạo `customer.ser` trong thư mục làm việc hiện tại. Đây là **định dạng serialization nhị phân của Java**, không phải file text; đừng sửa bằng text editor. Giữ nguyên file để kiểm tra bản đọc v2.

### Bước B — phiên bản 2 thêm trường nhưng giữ UID

Tạo `v2/Customer.java`:

```java
import java.io.Serializable;

public class Customer implements Serializable {
    private static final long serialVersionUID = 1L;

    String name;
    int points;
    String level = "BASIC";
}
```

Tạo `v2/Reader.java`:

```java
import java.io.FileInputStream;
import java.io.ObjectInputStream;

public class Reader {
    public static void main(String[] args) throws Exception {
        try (ObjectInputStream in =
                new ObjectInputStream(new FileInputStream("customer.ser"))) {
            Customer c = (Customer) in.readObject();
            System.out.printf("name=%s, points=%d, level=%s%n",
                    c.name, c.points, c.level);
        }
    }
}
```

Biên dịch v2 **riêng**, đọc chính file `customer.ser` đã ghi ở bước A:

```bash
javac -encoding UTF-8 -d v2-classes v2/Customer.java v2/Reader.java
java -cp v2-classes Reader
```

Stdout chính xác:

```text
name=Lan, points=120, level=null
```

Giải thích:

1. `Customer` ở hai phía có cùng tên lớp và `serialVersionUID = 1L`.
2. Hai trường `name` và `points` có tên/kiểu tương ứng nên dữ liệu cũ được khôi phục.
3. `level` **không tồn tại trong stream phiên bản 1**, vì thế khi đọc bằng v2, Java gán mặc định `null`. Dòng khởi tạo `String level = "BASIC";` của lớp Serializable không chạy lúc giải tuần tự hóa, nên không có giá trị `"BASIC"`.

Đây là ví dụ về một thay đổi **tương thích ở mức cơ chế serialization**, nhưng có thể vẫn gây lỗi nghiệp vụ nếu code mới giả định `level` luôn khác `null`.

### Bước C — cố ý đổi UID và quan sát lỗi

Trong `v2/Customer.java`, chỉ đổi:

```java
private static final long serialVersionUID = 2L;
```

Biên dịch lại rồi đọc file cũ:

```bash
javac -encoding UTF-8 -d v2-classes v2/Customer.java v2/Reader.java
java -cp v2-classes Reader
```

Lệnh thứ hai thất bại với `java.io.InvalidClassException`; thông báo sẽ nêu stream UID `1` và local UID `2`. Đây là **lỗi có chủ đích** minh họa “không chấp nhận dữ liệu phiên bản cũ”. Muốn chạy lại B, khôi phục UID v2 về `1L` rồi biên dịch lại. Chỉ đổi UID về đúng số cũng **không sửa được** mọi thay đổi field bất tương thích.

## 4. Những thay đổi lớp nào tương thích?

Các quy tắc sau nói về **default serialization của Serializable**, giả sử tên lớp được tìm thấy và UID tương ứng được giữ nguyên. “Tương thích” nghĩa là stream có thể được đọc theo các quy tắc serialization; không tự bảo đảm dữ liệu còn đúng nghĩa nghiệp vụ.

| Thay đổi ở phiên bản mới | Kết quả thông thường khi đọc dữ liệu cũ | Hệ quả cần xử lý |
| --- | --- | --- |
| Thêm trường instance được serialize | Tương thích; trường mới mang giá trị mặc định `null`/`0`/`false` | Chuẩn hóa giá trị khi đọc nếu nghiệp vụ cần |
| Xóa trường instance | Tương thích; dữ liệu của trường cũ trong stream bị bỏ qua | Mất phần trạng thái cũ khi đọc bằng lớp mới |
| Đổi tên trường instance | Tương đương xóa tên cũ và thêm tên mới | Giá trị tên cũ không tự chuyển sang tên mới |
| Đổi `private`/`public` của trường nhưng giữ tên/kiểu | Thông thường tương thích khi UID cố định | Vẫn cần xem tác động về đóng gói |
| Biến trường instance thành `static` hoặc `transient` | Tương tự xóa field khỏi serialized form | Không khôi phục giá trị cũ vào trường ấy |
| Biến trường `static`/`transient` thành trường instance được serialize | Tương tự thêm field | Dữ liệu cũ không chứa field này; nhận mặc định |
| Đổi kiểu trường (ví dụ `int` sang `long`, hoặc `String` sang `Integer`) | **Không được coi là tương thích**; có thể `InvalidClassException` | Thiết kế chuyển đổi dữ liệu có phiên bản |
| Thêm/sửa phương thức bình thường | Thường không thay đổi serialized form mặc định nếu UID cố định | Có thể thay đổi logic dùng dữ liệu cũ |
| Đổi tên lớp, package hay chuyển classpath thiếu lớp | Việc ánh xạ tên lớp thất bại; có thể `ClassNotFoundException` | Cần chiến lược migration hoặc đọc bằng code cũ |
| Đổi từ `Serializable` sang `Externalizable` (hoặc ngược lại) | Bất tương thích định dạng/cơ chế | Không áp dụng cùng quy tắc field mặc định |
| Thay superclass, cấp kế thừa, cách ghi custom data | Phụ thuộc trường hợp và có thể bất tương thích | Kiểm thử trên file thật của các phiên bản |

**Phân biệt hai tầng:** UID khác thường chặn đọc ngay ở bước nhận diện version; UID giống chỉ cho phép Java thử đối chiếu dữ liệu theo quy tắc của serialization. Vì thế *giữ UID* phải đi cùng quyết định bảo toàn cấu trúc có thể đọc được và ý nghĩa dữ liệu.

Java định nghĩa chi tiết trong tài liệu **Java Object Serialization Specification**, mục *Versioning of Serializable Objects*. Với những thay đổi phức tạp về cây thừa kế, `writeObject/readObject`, `readResolve`, proxy hoặc enum/record, cần xem chính đặc tả và kiểm chứng bằng fixture hai chiều.

## 5. Khi thêm trường cần giá trị mặc định nghiệp vụ

Một trường mới không có dữ liệu trong stream cũ nên chỉ nhận giá trị mặc định của kiểu Java, **không nhận initializer** của chính lớp Serializable. Nếu `null` không hợp lệ cho `level`, có thể sửa logic sử dụng dữ liệu cũ, hoặc tùy biến `readObject` để bù giá trị thiếu.

Ví dụ đoạn sau **thay thế logic đọc mặc định trong lớp `Customer` v2** (đặt vào thân lớp; cần `import java.io.IOException;` và `import java.io.ObjectInputStream;`). Không phải chương trình độc lập:

```java
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    ObjectInputStream.GetField fields = in.readFields();

    name = (String) fields.get("name", null);
    points = fields.get("points", 0);
    level = fields.defaulted("level")
            ? "BASIC"
            : (String) fields.get("level", null);
}
```

`GetField.defaulted("level")` kiểm tra field có vắng mặt khỏi stream đang đọc không; nhờ vậy có thể phân biệt “bản cũ chưa có field” với “bản mới chủ động lưu `null`”. Với yêu cầu đơn giản hơn, có thể dùng `in.defaultReadObject()` rồi kiểm tra và chuẩn hóa field, nhưng khi đó không phân biệt hai trường hợp nói trên. Nếu đã có `writeObject/readObject` riêng hoặc `serialPersistentFields`, phải duy trì cẩn thận định dạng đã công bố.

Không nên âm thầm đổi UID để “sửa” dữ liệu hay dùng ép kiểu để vượt qua lỗi. Đối với dữ liệu cần sống lâu, giải pháp bền vững thường là **định dạng dữ liệu có schema/version rõ ràng** với bước migration và bài kiểm thử dữ liệu lưu từ các phiên bản đã phát hành.

## 6. Tạo, kiểm tra và quản lý UID

- **Khai báo UID tường minh** cho các lớp Serializable mà ứng dụng thật sự lưu, cache bền vững hoặc gửi qua ranh giới phiên bản. Ví dụ `private static final long serialVersionUID = 1L;`.
- **Giữ UID** khi thay đổi vẫn tương thích và chương trình mới vẫn hiểu dữ liệu cũ. Kiểm tra từ cả cấp dữ liệu và cấp nghiệp vụ.
- **Đổi UID có chủ đích** khi cần từ chối file cũ và chấp nhận `InvalidClassException`. Sau đó có kế hoạch xóa cache cũ, migration hoặc hỗ trợ phiên bản cũ nếu cần.
- **Không coi UID là số phiên bản ứng dụng** hay timestamp. Không có quy tắc bắt buộc phải dùng `1L`, `2L` theo mỗi release.
- **Công cụ `serialver`** của JDK có thể in `serialVersionUID` của class đã biên dịch, ví dụ `serialver -classpath v1-classes Customer`. API `ObjectStreamClass.lookup(Customer.class).getSerialVersionUID()` cũng cho biết UID class theo runtime.
- **Không dựa vào UID tự tính** nếu yêu cầu tương thích dữ liệu lâu dài. Một thay đổi chữ ký, modifier hoặc toolchain có thể làm UID mặc định khác.
- **Kiểm thử bằng file fixture thật:** ghi bằng v1 và đọc bằng v2 (cân nhắc cả chiều ngược nếu hỗ trợ rollback); kiểm tra cả giá trị, invariant và lỗi mong đợi. Giữ fixture trong bộ kiểm thử tương thích khi schema thay đổi.

Lưu ý: một số kiểu Java có quy tắc serialization đặc biệt, ví dụ `enum` được biểu diễn chủ yếu theo tên hằng và `record` có quy tắc versioning riêng. Không suy diễn toàn bộ ví dụ class Serializable thông thường sang những kiểu đó.

## 7. Sự cố thường gặp và cách phân biệt

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `InvalidClassException: local class incompatible` | UID trong stream khác UID của lớp đang chạy | Kiểm tra classpath/build thực tế, UID hai phía và chính sách migration |
| `InvalidClassException` dù UID bằng nhau | Thay đổi cấu trúc hoặc yêu cầu serialization không hợp lệ | Đối chiếu field type, hierarchy, Serializable/Externalizable, custom format |
| `ClassNotFoundException` khi `readObject()` | Không tìm thấy tên lớp trong stream | Bổ sung đúng classpath, duy trì lớp cũ hoặc chuyển đổi định dạng |
| `NotSerializableException` khi `writeObject()` | Một đối tượng trong graph không Serializable | Sửa model hoặc đánh dấu `transient` nếu có chủ đích |
| Trường mới trả về `null` dù đã có initializer | Initializer Serializable không chạy lúc đọc object cũ | Migrate/khôi phục ở `readObject` hoặc lớp nghiệp vụ |
| Dữ liệu cũ đọc được nhưng hành vi sai | Tương thích binary không đồng nghĩa tương thích ngữ nghĩa | Validate invariant, cung cấp giá trị mặc định, migrate dữ liệu |

Vì `ObjectInputStream.readObject()` có thể tạo đối tượng, kích hoạt cơ chế khôi phục tùy biến và tiếp cận cả đồ thị đối tượng, **không bao giờ coi dữ liệu Java serialized từ nguồn không tin cậy là an toàn**. Với hệ thống mới, ưu tiên định dạng dữ liệu có schema và kiểm soát kiểu. Nếu bắt buộc đọc Java serialization, kiểm soát nguồn dữ liệu, đặt giới hạn kích thước/độ sâu/tham chiếu và allowlist class bằng `ObjectInputFilter` (Java 9+), đồng thời áp dụng quy trình bảo mật phù hợp. UID không cung cấp bảo vệ bảo mật.

## 8. Câu hỏi tự kiểm tra

1. V1 có `int points`, v2 thêm `boolean active` và giữ UID. Khi đọc dữ liệu từ v1, `active` là gì? **Đáp án:** `false` (nếu không tùy biến khôi phục).
2. V1 lưu `String fullName`, v2 đổi tên thành `name` và giữ UID. Giá trị cũ có tự gán sang `name` không? **Không**; cần migration/ánh xạ cụ thể.
3. V1 và v2 giống field nhưng đổi UID từ `1L` thành `2L`. `readObject()` sẽ làm gì? **Ném `InvalidClassException`** đối với Serializable class thông thường.
4. Có thể giữ UID để biến field `int` thành `long` rồi kỳ vọng Java tự chuyển đổi không? **Không**. Cần thiết kế thay đổi serialized form hoặc migration.
5. Vì sao ví dụ `level = "BASIC"` vẫn in `null` ở bản v2? **Vì initializer của lớp Serializable không thực thi khi đối tượng v1 được giải tuần tự hóa**.

**Tài liệu gốc:** Java Object Serialization Specification — các phần *Class Descriptors*, *Versioning of Serializable Objects* và *Input*; Java API docs cho `Serializable`, `ObjectInputStream`, `ObjectStreamClass` và `ObjectInputFilter`.