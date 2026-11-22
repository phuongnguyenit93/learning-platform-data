# Serializable, Cloneable và giới hạn của marker interface

Trong Java, **marker interface** là interface không khai báo phương thức, được dùng để đánh dấu một kiểu có ý nghĩa đặc biệt đối với thư viện hoặc runtime. Hai ví dụ kinh điển trong JDK là `java.io.Serializable` và `java.lang.Cloneable`.

Cả hai đều không có phương thức trừu tượng mà lớp phải triển khai. Tuy vậy, chúng có tác dụng khác nhau:

- **Serializable** đánh dấu rằng đối tượng thuộc kiểu có thể tham gia cơ chế tuần tự hóa đối tượng Java (*Java object serialization*), với điều kiện các phần dữ liệu cần tuần tự hóa đáp ứng quy tắc tương ứng.
- **Cloneable** đánh dấu rằng cơ chế `Object.clone()` được phép tạo bản sao của instance. Interface này không tự cung cấp một phương thức `clone()` công khai cho người dùng lớp gọi.

Marker interface có thể truyền tải thông tin về một kiểu, nhưng bản thân chúng không đảm bảo rằng mọi thao tác liên quan đều an toàn, đầy đủ hoặc phù hợp về mặt nghiệp vụ. Cần hiểu hợp đồng cụ thể mà JDK gắn với từng marker.

## 1. Marker interface hoạt động như thế nào?

Một interface thông thường thường mô tả hành vi thông qua các phương thức. Ví dụ, `Runnable` khai báo `run()`; một lớp triển khai `Runnable` phải cung cấp hành vi đó.

Marker interface không khai báo phương thức như vậy:

~~~java
public interface Serializable {
    // Không khai báo phương thức.
}

public interface Cloneable {
    // Không khai báo phương thức.
}
~~~

Đây chỉ là minh họa cấu trúc; trong ứng dụng, hãy dùng các interface thật từ JDK thay vì tự định nghĩa lại chúng.

Cơ chế sử dụng marker phụ thuộc vào API kiểm tra kiểu. Chẳng hạn, một API có thể kiểm tra `value instanceof SomeMarker` hoặc kiểm tra thông tin kiểu bằng reflection, rồi áp dụng một quy tắc riêng. Khi một lớp triển khai marker, nó tham gia hợp đồng mà API đó định nghĩa.

Điều này khác với việc một interface khai báo phương thức mà mọi lớp triển khai phải cung cấp. Marker không tự tạo ra phương thức, không tự sao chép dữ liệu, không tự xác thực trạng thái và cũng không đảm bảo mọi đối tượng liên quan đều tuân thủ các điều kiện khác của API.

## 2. Serializable: tuần tự hóa đối tượng Java

`java.io.Serializable` là marker interface dùng với cơ chế tuần tự hóa đối tượng Java. `ObjectOutputStream` có thể ghi đồ thị đối tượng có thể tuần tự hóa; `ObjectInputStream` có thể dựng lại đối tượng từ luồng dữ liệu tương ứng.

Ví dụ tối thiểu:

~~~java
import java.io.Serializable;

final class UserProfile implements Serializable {
    private static final long serialVersionUID = 1L;

    private final String username;

    UserProfile(String username) {
        this.username = username;
    }

    public String username() {
        return username;
    }
}
~~~

Khai báo `implements Serializable` không buộc lớp phải viết một phương thức như `serialize()`. Thay vào đó, các lớp thư viện đọc metadata và trạng thái đối tượng theo quy tắc serialization của Java.

### Các điểm quan trọng của Serializable

- Các trường instance không được đánh dấu `transient` thường thuộc trạng thái mặc định được tuần tự hóa. Những đối tượng được tham chiếu bởi các trường này cũng cần đáp ứng quy tắc tuần tự hóa, trừ khi cơ chế tùy chỉnh xử lý chúng.
- Nếu một đối tượng chứa trường tham chiếu tới một đối tượng không thể tuần tự hóa, thao tác ghi có thể ném `NotSerializableException`.
- Trường `static` thuộc về lớp, không phải trạng thái instance được lưu theo cách mặc định của đối tượng.
- Trường `transient` được bỏ qua bởi cơ chế tuần tự hóa mặc định. Khi đọc lại, trường đó nhận giá trị mặc định nếu không có logic tùy chỉnh khởi tạo lại nó.
- `serialVersionUID` là định danh phiên bản serialization. Khai báo rõ ràng có thể giúp kiểm soát khả năng tương thích giữa các phiên bản lớp. Giá trị này không tự bảo đảm rằng thay đổi cấu trúc lớp vẫn tương thích.
- Lớp có thể định nghĩa các phương thức đặc biệt như `private void writeObject(ObjectOutputStream out)` hoặc `private void readObject(ObjectInputStream in)` để tùy chỉnh serialization theo quy ước của Java. Các phương thức này không phải phương thức được khai báo trong `Serializable`; chữ ký và quy tắc của chúng phải chính xác.

Một đối tượng được tuần tự hóa có thể tham chiếu tới các đối tượng khác, vì vậy cần xem xét toàn bộ đồ thị đối tượng chứ không chỉ lớp ngoài cùng. Ví dụ, nếu `UserProfile` chứa một đối tượng `Address`, việc lớp `UserProfile` triển khai `Serializable` chưa đủ nếu `Address` không thể được tuần tự hóa và trường đó không được xử lý riêng.

## 3. Chương trình Java hoàn chỉnh: serialize và deserialize

Tạo tệp **SerializableDemo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class SerializableDemo {
    static final class UserProfile implements Serializable {
        private static final long serialVersionUID = 1L;

        private final String username;
        private final String city;

        UserProfile(String username, String city) {
            this.username = username;
            this.city = city;
        }

        String username() {
            return username;
        }

        String city() {
            return city;
        }
    }

    public static void main(String[] args)
            throws IOException, ClassNotFoundException {
        UserProfile original = new UserProfile("linh", "Hanoi");

        byte[] bytes;
        try (ByteArrayOutputStream buffer = new ByteArrayOutputStream();
             ObjectOutputStream out = new ObjectOutputStream(buffer)) {
            out.writeObject(original);
            out.flush();
            bytes = buffer.toByteArray();
        }

        UserProfile restored;
        try (ByteArrayInputStream buffer =
                     new ByteArrayInputStream(bytes);
             ObjectInputStream in = new ObjectInputStream(buffer)) {
            restored = (UserProfile) in.readObject();
        }

        System.out.println(restored.username() + ", " + restored.city());
        System.out.println("Serialized bytes: " + (bytes.length > 0));
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac SerializableDemo.java
java SerializableDemo
~~~

Kết quả stdout:

~~~text
linh, Hanoi
Serialized bytes: true
~~~

Chương trình ghi đối tượng vào một luồng byte trong bộ nhớ, sau đó đọc nó trở lại. Nó minh họa cơ chế tuần tự hóa; ứng dụng thực tế có thể ghi ra tệp hoặc một luồng khác, nhưng cần quản lý vòng đời dữ liệu và kiểm tra tính tương thích giữa các phiên bản.

Ví dụ trên sử dụng các trường `String`, vốn có thể tuần tự hóa. Nếu thêm một trường là đối tượng tùy chỉnh, hãy xem xét kiểu của đối tượng đó và các trường mà nó chứa.

## 4. Giới hạn và rủi ro của Serializable

Triển khai `Serializable` không đồng nghĩa với việc mọi trạng thái của đối tượng được lưu theo đúng cách ứng dụng mong muốn.

**Trạng thái bị bỏ qua:** trường `transient` không được ghi theo cơ chế mặc định. Nếu trường đó giữ trạng thái cần thiết để đối tượng hoạt động, lớp cần có cách khôi phục hoặc tái tạo trạng thái hợp lệ.

**Tương thích phiên bản:** việc thêm, xóa hoặc đổi kiểu trường và thay đổi cấu trúc lớp có thể ảnh hưởng quá trình đọc dữ liệu cũ. `serialVersionUID` giúp kiểm soát một phần việc nhận diện phiên bản, nhưng không thay thế việc thiết kế, kiểm thử và quản lý định dạng dữ liệu.

**Bất biến của đối tượng:** khi đọc đối tượng, không nên mặc định rằng mọi điều kiện khởi tạo trong constructor thông thường đều đã được thực thi theo cùng cách như lúc gọi `new`. Cần hiểu quy tắc serialization, cách khôi phục trạng thái và những hook tùy chỉnh có liên quan.

**An toàn dữ liệu:** không nên deserialize dữ liệu không đáng tin cậy bằng cơ chế Java native serialization. Đối tượng được khôi phục có thể kích hoạt các đường xử lý phức tạp thông qua đồ thị đối tượng và mã thư viện. Nếu cần nhận dữ liệu từ bên ngoài, ưu tiên định dạng dữ liệu có schema rõ ràng, xác thực đầu vào và cơ chế chuyển đổi có kiểm soát.

**Không phải định dạng trao đổi bền vững mặc định:** Java serialization thường gắn chặt với mô hình lớp Java và quy tắc tương thích của nó. Với API công khai, dữ liệu cần dùng giữa nhiều ngôn ngữ hoặc lưu trữ lâu dài, định dạng như JSON, Protocol Buffers hoặc một schema dữ liệu rõ ràng có thể phù hợp hơn, tùy yêu cầu.

Chỉ triển khai `Serializable` khi ứng dụng thực sự cần cơ chế này và đã xem xét trạng thái, tương thích, bảo mật cùng vòng đời dữ liệu.

## 5. Cloneable: hợp đồng với Object.clone()

`java.lang.Cloneable` cũng là marker interface, nhưng mục đích của nó rất khác. Nó cho biết rằng `Object.clone()` có thể tạo bản sao của instance đó mà không ném `CloneNotSupportedException` chỉ vì lớp không đánh dấu khả năng clone.

Interface `Cloneable` không khai báo phương thức `clone()`. Phương thức `clone()` trong `Object` là `protected`, vì vậy mã bên ngoài thường không thể gọi `clone()` trực tiếp trên mọi đối tượng. Nếu muốn cung cấp API clone, lớp thường phải tự ghi đè phương thức với mức truy cập phù hợp.

Ví dụ:

~~~java
class Counter implements Cloneable {
    private int value;

    Counter(int value) {
        this.value = value;
    }

    int value() {
        return value;
    }

    @Override
    public Counter clone() {
        try {
            return (Counter) super.clone();
        } catch (CloneNotSupportedException e) {
            throw new AssertionError(e);
        }
    }
}
~~~

Ở đây, `Counter` triển khai `Cloneable` và cung cấp một phương thức `clone()` công khai. Lệnh `super.clone()` gọi cơ chế sao chép từ `Object`. Với lớp này, giá trị `int` được sao chép trực tiếp nên bản sao có giá trị ban đầu giống đối tượng gốc.

Việc bắt `CloneNotSupportedException` rồi ném `AssertionError` là lựa chọn thường dùng trong ví dụ khi lớp đã triển khai `Cloneable` và lời gọi `super.clone()` được kỳ vọng thành công. Trong thiết kế thực tế, hãy xác định API sao chép và cách xử lý lỗi một cách nhất quán.

## 6. Cloneable không tự tạo ra API clone

Có ba việc riêng biệt cần phân biệt:

1. **Triển khai marker:** lớp khai báo `implements Cloneable`.
2. **Thực hiện sao chép:** mã gọi `super.clone()` hoặc tự tạo một đối tượng mới và sao chép trạng thái.
3. **Cung cấp API cho người dùng:** lớp quyết định có khai báo phương thức sao chép công khai hay không, cùng kiểu trả về và hợp đồng của phương thức đó.

Chỉ thực hiện bước thứ nhất không có nghĩa là người gọi có thể viết `someObject.clone()` từ mã ở bất kỳ đâu. Phương thức `Object.clone()` vẫn là `protected`, và `Cloneable` không khai báo phương thức để thay đổi điều đó.

Nếu lớp không triển khai `Cloneable` nhưng gọi `super.clone()`, cơ chế của `Object.clone()` sẽ ném `CloneNotSupportedException`. Nếu lớp triển khai `Cloneable` nhưng không ghi đè hoặc cung cấp phương thức clone thích hợp, mã sử dụng lớp vẫn có thể không có cách gọi clone phù hợp.

## 7. Shallow copy và deep copy

Điểm giới hạn lớn nhất của `Object.clone()` là nó tạo **shallow copy** (bản sao nông). Các trường primitive được sao chép giá trị; các trường tham chiếu được sao chép giá trị tham chiếu. Các đối tượng mà những tham chiếu đó trỏ tới không tự động được nhân bản.

Ví dụ, nếu một đối tượng `Person` có trường `Address address`, sau khi clone:

- `person != copy` thường là `true`: hai tham chiếu trỏ tới hai instance ngoài khác nhau.
- `person.address == copy.address` là `true`: cả hai instance cùng tham chiếu một đối tượng địa chỉ.
- Nếu địa chỉ có trạng thái mutable, thay đổi thông qua một tham chiếu sẽ được nhìn thấy khi truy cập địa chỉ từ đối tượng còn lại.

**Deep copy** (bản sao sâu) đòi hỏi sao chép thêm các đối tượng mutable bên trong theo một quy tắc rõ ràng. Không có một thao tác clone tổng quát nào tự biết nên sao chép sâu mọi trường, chia sẻ đối tượng bất biến hay giữ lại các tài nguyên dùng chung. Lớp cần xác định hợp đồng sao chép phù hợp.

## 8. Ví dụ hoàn chỉnh: Cloneable và giới hạn shallow copy

Tạo tệp **MarkerInterfacesDemo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class MarkerInterfacesDemo {
    static final class Address implements Serializable {
        private static final long serialVersionUID = 1L;
        private final String city;

        Address(String city) {
            this.city = city;
        }
    }

    static final class Person implements Serializable, Cloneable {
        private static final long serialVersionUID = 1L;
        private final String name;
        private final Address address;

        Person(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        @Override
        public Person clone() {
            try {
                return (Person) super.clone();
            } catch (CloneNotSupportedException e) {
                throw new AssertionError(e);
            }
        }

        Person deepCopy() {
            return new Person(name, new Address(address.city));
        }
    }

    public static void main(String[] args)
            throws IOException, ClassNotFoundException {
        Person original = new Person("An", new Address("Hanoi"));
        Person shallow = original.clone();
        Person deep = original.deepCopy();

        System.out.println("Clone is a distinct object: "
                + (original != shallow));
        System.out.println("Address is shared after shallow clone: "
                + (original.address == shallow.address));
        System.out.println("Address is independent after deep copy: "
                + (original.address != deep.address));

        byte[] bytes;
        try (ByteArrayOutputStream buffer = new ByteArrayOutputStream();
             ObjectOutputStream out = new ObjectOutputStream(buffer)) {
            out.writeObject(original);
            out.flush();
            bytes = buffer.toByteArray();
        }

        Person restored;
        try (ByteArrayInputStream buffer =
                     new ByteArrayInputStream(bytes);
             ObjectInputStream in = new ObjectInputStream(buffer)) {
            restored = (Person) in.readObject();
        }

        System.out.println("Deserialized person: "
                + restored.name + ", " + restored.address.city);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MarkerInterfacesDemo.java
java MarkerInterfacesDemo
~~~

Kết quả stdout chính xác:

~~~text
Clone is a distinct object: true
Address is shared after shallow clone: true
Address is independent after deep copy: true
Deserialized person: An, Hanoi
~~~

Trong ví dụ này, `Person.clone()` sử dụng `super.clone()`, nên `address` được sao chép như một tham chiếu và vẫn trỏ đến cùng một instance `Address`. Phương thức `deepCopy()` chủ động tạo một `Address` mới, thể hiện cách lớp định nghĩa bản sao sâu theo mô hình của nó.

Cả `Person` lẫn `Address` đều triển khai `Serializable`, vì vậy đồ thị đối tượng dùng trong ví dụ có thể được ghi bằng cơ chế mặc định. `serialVersionUID` được khai báo cho cả hai lớp để thể hiện chủ đích quản lý phiên bản serialization.

## 9. Những hạn chế của Cloneable và Object.clone()

- **Sao chép nông:** tham chiếu tới các đối tượng mutable vẫn được chia sẻ nếu lớp không tự sao chép chúng.
- **Không có phương thức trong interface:** `Cloneable` không định nghĩa chữ ký `clone()`, nên không cung cấp một API sao chép thống nhất để mọi mã có thể gọi qua kiểu `Cloneable`.
- **Hợp đồng khó hiểu:** người gọi thường không biết bản sao là nông hay sâu, trường nào được chia sẻ, hoặc điều kiện nào được giữ nguyên nếu tài liệu không nêu rõ.
- **Xử lý kế thừa phức tạp:** một lớp con có thể thêm trường mutable. Phương thức clone kế thừa từ lớp cha có thể chưa sao chép sâu những trường mới đó, khiến lớp con cần ghi đè và hoàn thiện hợp đồng sao chép.
- **Constructor không được dùng theo cách khởi tạo thông thường:** `Object.clone()` tạo bản sao theo cơ chế của Java thay vì gọi constructor của lớp đó như khi dùng `new`. Vì vậy, không nên dựa vào constructor để tái lập bất biến khi clone.
- **Tài nguyên bên ngoài:** sao chép tham chiếu đến file handle, socket, khóa, kết nối hoặc tài nguyên có vòng đời riêng thường không tạo ra một tài nguyên độc lập hợp lệ.

Do các giới hạn này, nhiều API hiện đại chọn constructor sao chép, factory method hoặc một phương thức có tên rõ như `copy()` thay vì phơi bày `clone()`. Cách đó cho phép xác định chính xác trường nào được sao chép, trường nào được chia sẻ và cách khởi tạo trạng thái.

## 10. Chọn Serializable, Cloneable hay một cách khác?

| Nhu cầu | Lựa chọn có thể phù hợp | Điều cần làm rõ |
|---|---|---|
| Ghi và đọc đồ thị đối tượng bằng Java native serialization | `Serializable` | Các trường, `transient`, tương thích phiên bản, dữ liệu không đáng tin cậy |
| Cho phép `Object.clone()` tạo bản sao | `Cloneable` cùng API clone phù hợp | Shallow/deep copy, trường mutable, hợp đồng của lớp con |
| Sao chép một đối tượng theo quy tắc nghiệp vụ | Constructor sao chép hoặc `copy()` | Trường nào sao chép sâu, trường nào chia sẻ |
| Trao đổi dữ liệu giữa dịch vụ hoặc ngôn ngữ khác nhau | DTO cùng định dạng dữ liệu có schema | Xác thực, phiên bản schema, biểu diễn dữ liệu |
| Đánh dấu khả năng cho một API tùy chỉnh | Marker interface riêng chỉ khi hợp đồng thực sự phù hợp | Ý nghĩa marker, cách API kiểm tra và hành vi khi không có marker |

Marker interface có thể hữu ích khi một API cần nhận biết một khả năng hoặc điều kiện kiểu. Tuy nhiên, nếu cần hành vi có thể gọi, một interface với phương thức thường diễn đạt hợp đồng rõ hơn. Nếu cần sao chép có kiểm soát, một phương thức `copy()` hoặc constructor sao chép thường làm rõ ý định hơn `Cloneable`.

## 11. Lỗi thường gặp và cách khắc phục

- **Cho rằng Serializable tự ghi được mọi trường:** kiểm tra toàn bộ đồ thị đối tượng và xử lý những trường không thể tuần tự hóa.
- **Cho rằng `transient` được khôi phục tự động:** thiết kế cách khởi tạo lại trường nếu ứng dụng cần giá trị khác giá trị mặc định.
- **Xem `serialVersionUID` là bảo đảm tương thích:** kiểm thử việc đọc dữ liệu cũ và quản lý thay đổi cấu trúc lớp.
- **Deserialize dữ liệu không đáng tin cậy:** tránh native serialization cho đầu vào không tin cậy; ưu tiên định dạng và bộ giải mã có kiểm soát.
- **Cho rằng implements Cloneable là đã có phương thức clone công khai:** cung cấp API sao chép rõ ràng nếu người gọi cần dùng nó.
- **Cho rằng clone luôn sao chép sâu:** kiểm tra mọi trường tham chiếu và quyết định rõ đối tượng nào cần được sao chép.
- **Không xem xét lớp con khi clone:** xác định hợp đồng sao chép qua cây kế thừa và kiểm tra các trường mutable được thêm ở lớp con.
- **Dùng clone cho tài nguyên có vòng đời độc lập:** định nghĩa quy trình mở/tạo tài nguyên mới thay vì sao chép tham chiếu một cách máy móc.

## 12. Quy trình thiết kế và kiểm thử

1. Xác định nhu cầu thật: tuần tự hóa dữ liệu, sao chép đối tượng hay đánh dấu khả năng cho một API.
2. Nếu chọn `Serializable`, rà soát các trường instance, các đối tượng được tham chiếu, trường `transient`, phiên bản lớp và nguồn dữ liệu.
3. Nếu chọn `Cloneable`, quyết định API công khai và hợp đồng shallow/deep copy trước khi triển khai.
4. Với sao chép sâu, liệt kê các trường mutable và xác định trường nào phải tạo bản sao mới, trường nào có thể chia sẻ.
5. Viết kiểm thử xác nhận cả giá trị lẫn danh tính tham chiếu; hai đối tượng có giá trị bằng nhau không nhất thiết phải chia sẻ cùng instance.
6. Kiểm thử serialization/deserialization trên dữ liệu đại diện và phiên bản cần hỗ trợ, đồng thời tránh đọc dữ liệu không đáng tin cậy.
7. Tài liệu hóa giới hạn, các trường bị bỏ qua và cách khôi phục trạng thái để người gọi hiểu chính xác hợp đồng.

`Serializable` và `Cloneable` minh họa cách marker interface truyền tải một ý nghĩa đặc biệt trong JDK mà không cần khai báo phương thức. Nhưng marker chỉ là tín hiệu cho một cơ chế cụ thể: Serializable không bảo đảm mọi dữ liệu đều tương thích hay an toàn, còn Cloneable không tự cung cấp API sao chép sâu. Thiết kế tốt cần nêu rõ hợp đồng, quản lý trạng thái và kiểm thử những giới hạn đó.