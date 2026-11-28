# Kết hợp record với instanceof mà vẫn truy cập component bằng accessor

## 1. Record và type pattern giải quyết hai việc khác nhau

Từ Java 16, `record` trở thành tính năng chính thức để khai báo các lớp dữ liệu. Record mô tả dữ liệu qua các *component*; trình biên dịch tự tạo constructor chuẩn, accessor cho từng component, cùng các phương thức `equals`, `hashCode` và `toString`.

Cũng từ Java 16, pattern matching for `instanceof` cho phép kiểm tra kiểu và khai báo biến trong cùng một biểu thức. Hai tính năng kết hợp tự nhiên khi chương trình nhận một giá trị tổng quát như `Object`, xác nhận nó là một record cụ thể, rồi đọc dữ liệu qua accessor:

~~~java
record Point(int x, int y) {
}

class PointReader {
    static void print(Object value) {
        if (value instanceof Point point) {
            System.out.println("x = " + point.x());
            System.out.println("y = " + point.y());
        }
    }
}
~~~

Trong điều kiện `value instanceof Point point`:

1. Java kiểm tra đối tượng được tham chiếu bởi `value` có phải là một `Point` hay không.
2. Nếu khớp, biến pattern `point` được khai báo với kiểu tĩnh `Point`.
3. Trong nhánh đúng, chương trình gọi `point.x()` và `point.y()` để đọc các component.

Record định nghĩa hình dạng dữ liệu; type pattern giúp nhận diện kiểu record ở ranh giới nơi kiểu nguồn chưa cụ thể. Accessor là cách đọc component được cung cấp bởi record.

## 2. Accessor được tạo từ tên component

Khi khai báo:

~~~java
public record Customer(String name, int age) {
}
~~~

Java cung cấp các accessor công khai:

- `name()` trả về component `name` với kiểu `String`.
- `age()` trả về component `age` với kiểu `int`.

Có thể sử dụng record từ một kiểu khác như sau:

~~~java
class CustomerPrinter {
    static void print(Object value) {
        if (value instanceof Customer customer) {
            String name = customer.name();
            int age = customer.age();

            System.out.println(name + ", " + age);
        }
    }
}
~~~

Tên accessor trùng với tên component và không có tiền tố `get`. Ví dụ, component `accountId` có accessor `accountId()`, không phải `getAccountId()`.

Các component được lưu trong những field `private final`. Mã bên ngoài record không truy cập trực tiếp field đó; hãy dùng accessor công khai. Cách gọi `customer.name()` cũng làm rõ rằng chương trình đang đọc component thông qua API của record.

## 3. Chuyển từ kiểm tra kiểu và ép kiểu thủ công

Trước Java 16, một đoạn mã xử lý record từ `Object` thường phải kiểm tra rồi ép kiểu:

~~~java
record Money(long cents, String currency) {
}

class LegacyStyleReader {
    static void print(Object value) {
        if (value instanceof Money) {
            Money money = (Money) value;
            System.out.println(money.cents());
            System.out.println(money.currency());
        }
    }
}
~~~

Với type pattern, có thể gộp hai bước:

~~~java
record Money(long cents, String currency) {
}

class PatternReader {
    static void print(Object value) {
        if (value instanceof Money money) {
            System.out.println(money.cents());
            System.out.println(money.currency());
        }
    }
}
~~~

Biến `money` đã có kiểu `Money` sau khi pattern khớp. Không cần khai báo thêm biến và ép kiểu `(Money) value`. Cách viết này giảm lặp kiểu, đồng thời để trình biên dịch kiểm soát phạm vi sử dụng của biến.

## 4. Dùng accessor sau guard clause

Pattern variable có phạm vi dựa trên luồng điều khiển (*flow scoping*). Nếu phương thức kết thúc khi giá trị không khớp, biến record có thể dùng ở phần còn lại:

~~~java
record Point(int x, int y) {
}

class PointValidator {
    static int manhattanDistance(Object value) {
        if (!(value instanceof Point point)) {
            throw new IllegalArgumentException("Cần một Point");
        }

        return Math.abs(point.x()) + Math.abs(point.y());
    }
}
~~~

Nếu `value` là `null` hoặc không phải `Point`, pattern thất bại và phương thức ném ngoại lệ. Mọi đường đi tiếp tục đều đã khớp, nên `point` có thể được dùng ở câu lệnh `return`.

Cũng có thể dùng pattern trong biểu thức điều kiện với `&&`:

~~~java
record Point(int x, int y) {
}

class PointChecks {
    static boolean isInFirstQuadrant(Object value) {
        return value instanceof Point point
                && point.x() > 0
                && point.y() > 0;
    }
}
~~~

Vế phải chỉ được đánh giá khi pattern đúng. Vì vậy, nếu `value` là `null` hoặc không phải `Point`, các accessor không được gọi.

## 5. Record vẫn có thể triển khai interface

Record tự động kế thừa `java.lang.Record` và không thể kế thừa thêm một lớp khác; record vẫn có thể triển khai interface. Khi chỉ quan tâm đến hợp đồng hành vi, có thể kiểm tra interface và gọi phương thức qua biến pattern:

~~~java
interface Identified {
    String id();
}

record UserId(String id) implements Identified {
}

class IdentifierPrinter {
    static void print(Object value) {
        if (value instanceof Identified identified) {
            System.out.println(identified.id());
        }
    }
}
~~~

`UserId` là record và triển khai `Identified`. Pattern `Identified identified` chấp nhận một `UserId` cũng như bất kỳ đối tượng nào khác triển khai interface này. Biến `identified` có kiểu tĩnh `Identified`, nên chương trình chỉ gọi được các thành viên được khai báo trong interface.

Nếu cần component riêng của record, hãy kiểm tra kiểu record cụ thể:

~~~java
class UserRecordReader {
    static void print(Object value) {
        if (value instanceof UserId userId) {
            System.out.println(userId.id());
        }
    }
}
~~~

Record là kiểu `final`, nên một record không có các lớp con mở rộng thêm component. Điều này giúp ranh giới kiểu của record rõ ràng khi dùng trong pattern.

## 6. Record lồng nhau: gọi accessor theo từng cấp

Component của record có thể là một record khác. Trong cú pháp Java 16, trước hết xác nhận kiểu record bên ngoài, sau đó gọi accessor để lấy record lồng và tiếp tục kiểm tra nếu cần:

~~~java
record Address(String city, String country) {
}

record Customer(String name, Address address) {
}

class CustomerAddressPrinter {
    static void print(Object value) {
        if (value instanceof Customer customer) {
            System.out.println("Khách hàng: " + customer.name());

            Address address = customer.address();
            if (address != null) {
                System.out.println(address.city());
                System.out.println(address.country());
            }
        }
    }
}
~~~

Ở đây `customer.address()` trả về component `Address`. Vì component tham chiếu có thể là `null` nếu constructor không ngăn điều đó, mã kiểm tra trước khi gọi `city()` và `country()`.

Cách làm này dùng type pattern thông thường cho record bên ngoài và accessor cho component bên trong. Đây là cú pháp ổn định tương thích Java 16.

## 7. Generic record và type erasure

Record có thể khai báo tham số kiểu:

~~~java
record Box<T>(T value) {
}
~~~

Khi nhận một giá trị chưa biết kiểu, có thể kiểm tra bằng `Box<?>`:

~~~java
record Box<T>(T value) {
}

class BoxReader {
    static void print(Object candidate) {
        if (candidate instanceof Box<?> box) {
            Object component = box.value();

            if (component instanceof String text) {
                System.out.println(text.toUpperCase());
            }
        }
    }
}
~~~

Accessor `box.value()` trả về giá trị có kiểu tĩnh là `Object` khi biến pattern có kiểu `Box<?>`. Muốn dùng component như `String`, hãy kiểm tra component riêng.

Không thể kiểm tra trực tiếp `Box<String>` trong type pattern:

~~~java
class InvalidBoxPattern {
    static void inspect(Object candidate) {
        // Lỗi biên dịch: Box<String> không phải kiểu reifiable.
        // if (candidate instanceof Box<String> box) {
        //     System.out.println(box.value());
        // }
    }
}
~~~

Do type erasure, JVM không giữ thông tin tham số kiểu để xác nhận `Box<String>` thay vì `Box<Integer>`. `Box<?>` là kiểu phù hợp để xác nhận cấu trúc generic ở runtime.

## 8. Accessor không đồng nghĩa với bản sao sâu của component

Record có các field component là `private final`, nhưng điều đó không tự làm cho mọi đối tượng được tham chiếu trở nên bất biến. Nếu component là collection có thể sửa đổi, accessor trả về tham chiếu tới collection đó:

~~~java
import java.util.List;

record SearchResult(List<String> items) {
}

class SearchResultReader {
    static void print(Object value) {
        if (value instanceof SearchResult result) {
            for (String item : result.items()) {
                System.out.println(item);
            }
        }
    }
}
~~~

`result.items()` trả về component `items`. Nếu record được tạo với một `ArrayList`, mã bên ngoài vẫn có thể sửa danh sách đó thông qua tham chiếu được trả về. `final` chỉ ngăn gán lại field component, không khóa trạng thái bên trong collection.

Nếu muốn snapshot không thể sửa đổi cho collection đầu vào, có thể sao chép trong compact constructor:

~~~java
import java.util.List;
import java.util.Objects;

record SearchResult(List<String> items) {
    SearchResult {
        items = List.copyOf(Objects.requireNonNull(items));
    }
}
~~~

Constructor này từ chối collection `null`, đồng thời `List.copyOf` cũng từ chối phần tử `null` và lưu bản sao không thể sửa đổi. `List.copyOf` có từ Java 10 và vẫn là API hiện hành. Đây là bản sao nông: nếu phần tử là đối tượng mutable, bản thân các phần tử vẫn có thể thay đổi.

Khi đọc bằng pattern, accessor vẫn được gọi như bình thường:

~~~java
class SearchResultSize {
    static void print(Object value) {
        if (value instanceof SearchResult result) {
            System.out.println(result.items().size());
        }
    }
}
~~~

Pattern matching không thay đổi quy tắc mutability của component; nó chỉ xác nhận kiểu record và cung cấp biến để gọi accessor.

## 9. equals, hashCode và việc so sánh component

Record tự sinh `equals` và `hashCode` dựa trên các component. Nếu hai record cùng kiểu có các component tương ứng bằng nhau theo quy tắc của component, chúng được xem là bằng nhau:

~~~java
record Point(int x, int y) {
}

class PointEqualityDemo {
    static void compare() {
        Object first = new Point(3, 4);
        Object second = new Point(3, 4);

        if (first instanceof Point point
                && second instanceof Point other) {
            System.out.println(point.equals(other)); // true
            System.out.println(point.x() == other.x());
            System.out.println(point.y() == other.y());
        }
    }
}
~~~

Ở đây `instanceof` chỉ giúp lấy hai biến có kiểu `Point`; việc so sánh giá trị có thể dùng `equals` tự sinh hoặc đọc từng component qua accessor. Không cần tự viết lại `equals` chỉ để có thể so sánh record theo component mặc định.

Nếu record chứa collection, `equals` của collection sẽ được sử dụng. Với `List`, phép so sánh xét nội dung và thứ tự phần tử. Nếu collection có thể thay đổi, kết quả `equals` và `hashCode` của record cũng có thể thay đổi theo; hãy cân nhắc sao chép phòng vệ khi record được dùng làm giá trị hoặc khóa.

## 10. Giới hạn cú pháp cần nhớ khi viết mã Java 16

Trong Java 16, cách kết hợp hai tính năng này là:

~~~java
record Point(int x, int y) {
}

class Java16RecordPatternUsage {
    static void print(Object value) {
        if (value instanceof Point point) {
            int x = point.x();
            int y = point.y();
        }
    }
}
~~~

Pattern variable `point` đại diện cho toàn bộ record; các component được lấy bằng accessor `x()` và `y()`.

Cú pháp phân rã trực tiếp component bên trong pattern, chẳng hạn:

~~~java
// Không phải cú pháp Java 16:
// if (value instanceof Point(int x, int y)) { ... }
~~~

được gọi là *record pattern* và thuộc một tính năng ngôn ngữ được chuẩn hóa ở phiên bản Java sau. Khi biên dịch với mức ngôn ngữ Java 16, hãy dùng type pattern `instanceof Point point` rồi gọi accessor. Cách này vẫn rõ ràng, ổn định và tiếp tục hợp lệ trong Java hiện đại.

| Nhu cầu | Cách dùng với Java 16 |
| --- | --- |
| Xác nhận một `Object` là record `Point` | `value instanceof Point point` |
| Đọc component nguyên thủy | `point.x()` hoặc `point.y()` |
| Đọc component tham chiếu | `customer.name()` hoặc `customer.address()` |
| Đọc record generic chưa biết tham số | `candidate instanceof Box<?> box` |
| Kiểm tra component có kiểu cụ thể | Lấy bằng accessor, sau đó dùng `instanceof` cho component |
| Kiểm tra hành vi qua interface | `value instanceof Identified identified` |

**Ghi nhớ:** Với Java 16, type pattern tạo biến đại diện cho toàn bộ record, còn accessor như `point.x()` và `customer.name()` dùng để đọc từng component. Cách kết hợp này tận dụng record và pattern matching đã ổn định, giữ kiểm tra kiểu an toàn và không phụ thuộc vào cú pháp record pattern của các phiên bản Java sau.
