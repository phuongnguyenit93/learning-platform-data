# Khởi tạo anonymous subclass của abstract class

Trong Java, một **anonymous class** (lớp ẩn danh) là lớp được khai báo và khởi tạo ngay tại một biểu thức, không có tên lớp do lập trình viên đặt. Khi cần tạo một đối tượng dựa trên **abstract class**, ta có thể viết một lớp con ẩn danh bằng cú pháp `new AbstractClass(...){ ... }`, cung cấp phần triển khai cho các phương thức trừu tượng ngay tại chỗ.

Cách này hữu ích khi chỉ cần một triển khai nhỏ, dùng tại một vị trí và không có nhu cầu tái sử dụng như một lớp riêng. Nó cũng giúp ta sử dụng được cả trạng thái, constructor và phương thức đã triển khai sẵn của abstract class.

## 1. Cú pháp cơ bản

Cấu trúc tổng quát:

~~~java
AbstractClass reference = new AbstractClass(arguments) {
    @Override
    public ReturnType abstractMethod(Parameters parameters) {
        // Cung cấp phần triển khai cụ thể
    }

    // Có thể ghi đè các phương thức khác nếu cần
};
~~~

Các phần cần hiểu:

- `AbstractClass` là abstract class mà đối tượng ẩn danh sẽ kế thừa.
- `arguments` được truyền vào constructor của abstract class. Nếu lớp cha không có constructor không tham số truy cập được, phải gọi một constructor phù hợp.
- Phần thân trong cặp ngoặc nhọn `{ ... }` khai báo lớp con ẩn danh và triển khai các phương thức trừu tượng bắt buộc.
- Biến `reference` thường được khai báo theo kiểu abstract class để sử dụng đối tượng thông qua hợp đồng chung.
- Dấu chấm phẩy sau dấu `}` là cần thiết khi kết thúc câu lệnh khai báo và khởi tạo biến.

Không thể tạo trực tiếp một instance của abstract class bằng `new AbstractClass(...)` nếu không có phần thân lớp con. Phần thân trong biểu thức `new AbstractClass(...){...}` định nghĩa một lớp con cụ thể, và đối tượng được tạo là instance của lớp con đó.

## 2. Ví dụ hoàn chỉnh có thể chạy

Tạo tệp **AnonymousAbstractSubclassDemo.java** với nội dung:

~~~java
abstract class Report {
    private final String owner;

    protected Report(String owner) {
        if (owner == null || owner.isBlank()) {
            throw new IllegalArgumentException("owner must not be blank");
        }
        this.owner = owner;
    }

    public String label() {
        return "Report for " + owner;
    }

    public abstract String format(String message);

    public abstract void deliver(String message);
}

public class AnonymousAbstractSubclassDemo {
    public static void main(String[] args) {
        Report report = new Report("Mai") {
            @Override
            public String format(String message) {
                return "[EMAIL] " + message.trim();
            }

            @Override
            public void deliver(String message) {
                System.out.println(label() + ": " + format(message));
            }
        };

        report.deliver("  Build passed  ");
        System.out.println(report.getClass().isAnonymousClass());
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac AnonymousAbstractSubclassDemo.java
java AnonymousAbstractSubclassDemo
~~~

Kết quả stdout:

~~~text
Report for Mai: [EMAIL] Build passed
true
~~~

Điều gì xảy ra trong ví dụ này?

1. `new Report("Mai")` gọi constructor của abstract class `Report`; chuỗi `"Mai"` được truyền vào tham số `owner`.
2. Phần thân sau dấu ngoặc tròn khai báo một lớp con ẩn danh của `Report`.
3. Lớp con triển khai cả hai phương thức trừu tượng `format` và `deliver`, vì vậy nó là lớp cụ thể có thể khởi tạo.
4. Phương thức `label()` là phương thức cụ thể được kế thừa. Bên trong `deliver`, lời gọi `label()` sử dụng phần triển khai kế thừa đó.
5. Biến `report` có kiểu khai báo `Report`, nên mã gọi sử dụng các phương thức được định nghĩa trong abstract class. Kiểu thực tế của đối tượng là lớp con ẩn danh.
6. `getClass().isAnonymousClass()` trả về `true`, xác nhận đối tượng thuộc một lớp ẩn danh.

Lớp `Report` được khai báo không có từ khóa `public` để có thể đặt cùng tệp với lớp public `AnonymousAbstractSubclassDemo`. Trong mã ứng dụng, hãy tuân theo quy tắc tên tệp và lớp public của Java.

## 3. Vì sao cần abstract class?

Abstract class cho phép gom trạng thái và hành vi chung vào một lớp cơ sở, đồng thời yêu cầu lớp con cung cấp một số hành vi cụ thể. Nó có thể chứa:

- Trường dữ liệu, bao gồm trường `private` và `final`.
- Constructor để kiểm tra hoặc khởi tạo trạng thái chung.
- Phương thức cụ thể có sẵn phần thân.
- Phương thức trừu tượng chỉ khai báo chữ ký.
- Phương thức `final`, `static`, hoặc các thành phần khác theo quy tắc của Java.

Lớp con ẩn danh kế thừa các thành phần có thể truy cập từ abstract class. Nó phải triển khai tất cả phương thức trừu tượng còn chưa được triển khai từ lớp cha hoặc các lớp cha của nó. Nếu bỏ sót một phương thức trừu tượng bắt buộc, trình biên dịch báo lỗi; lớp ẩn danh được tạo trong biểu thức này không thể được khai báo là abstract để trì hoãn việc triển khai.

Nếu abstract class có phương thức cụ thể mà ta muốn thay đổi riêng cho đối tượng này, có thể ghi đè thêm phương thức đó. Không bắt buộc phải ghi đè mọi phương thức cụ thể.

## 4. Truyền đối số vào constructor của lớp cha

Phần nằm trong ngoặc tròn ngay sau tên abstract class là lời gọi constructor của lớp cha. Điều này cho phép lớp cha khởi tạo trạng thái dùng chung trước khi các phương thức của đối tượng được sử dụng.

~~~java
abstract class Greeting {
    private final String name;

    Greeting(String name) {
        this.name = name;
    }

    public String greetingPrefix() {
        return "Hello, " + name;
    }

    public abstract String message();
}
~~~

Có thể tạo một triển khai ẩn danh như sau:

~~~java
Greeting greeting = new Greeting("Linh") {
    @Override
    public String message() {
        return greetingPrefix() + "!";
    }
};

System.out.println(greeting.message());
~~~

Đây là đoạn minh họa để đặt bên trong một phương thức; nó phụ thuộc vào lớp `Greeting` ở trên. Kết quả:

~~~text
Hello, Linh!
~~~

Nếu abstract class không khai báo constructor, Java cung cấp constructor mặc định khi các điều kiện của ngôn ngữ cho phép. Nếu lớp cha khai báo constructor có tham số và không có constructor không tham số truy cập được, biểu thức tạo lớp con ẩn danh phải truyền đối số phù hợp. Quyền truy cập của constructor cũng được áp dụng như với một lớp con thông thường.

Lớp ẩn danh không khai báo constructor riêng có tên. Nếu cần truyền dữ liệu ban đầu, thường truyền dữ liệu đó vào constructor của lớp cha; các trường bổ sung của lớp ẩn danh có thể được khởi tạo bằng biểu thức khởi tạo trường hoặc khối khởi tạo instance khi cần.

## 5. Kiểu tham chiếu và đa hình

Một đối tượng tạo từ anonymous subclass có thể được lưu trong biến kiểu abstract class:

~~~java
Report report = new Report("Mai") {
    @Override
    public String format(String message) {
        return message.toUpperCase();
    }

    @Override
    public void deliver(String message) {
        System.out.println(format(message));
    }
};
~~~

Mã sử dụng `report` chỉ cần biết hợp đồng được khai báo trong `Report`. Khi gọi `report.deliver(...)`, Java thực thi phần triển khai của lớp con ẩn danh. Đây là **đa hình**: lời gọi qua tham chiếu kiểu cha có thể dẫn đến phần triển khai được ghi đè trong lớp con.

Kiểu khai báo và kiểu thực tế có vai trò khác nhau:

- **Kiểu khai báo** quyết định những thành viên nào có thể được gọi trực tiếp khi biên dịch.
- **Kiểu thực tế** quyết định phương thức instance nào được chọn khi thực thi theo cơ chế ghi đè động.
- Nếu lớp ẩn danh khai báo thêm một phương thức riêng không có trong abstract class, không thể gọi phương thức đó qua biến chỉ có kiểu abstract class nếu không có cách truy cập kiểu an toàn khác. Thông thường, nên thiết kế hợp đồng cần thiết ngay trong lớp cơ sở hoặc một interface phù hợp.

Cách sử dụng theo kiểu cha giúp mã gọi ít phụ thuộc vào chi tiết của lớp con ẩn danh và giữ được tính thay thế của đa hình.

## 6. Ghi đè phương thức đúng cách

Nên đặt chú thích `@Override` trước mỗi phương thức được ghi đè. Trình biên dịch sẽ phát hiện trường hợp chữ ký không khớp với phương thức cần ghi đè.

Ví dụ, nếu lớp cha khai báo:

~~~java
public abstract int calculate(int value);
~~~

thì lớp con cần cung cấp một triển khai tương thích:

~~~java
@Override
public int calculate(int value) {
    return value * 2;
}
~~~

Tên phương thức, danh sách tham số và kiểu trả về phải tuân thủ quy tắc ghi đè của Java. Không thể giảm mức truy cập của phương thức khi ghi đè; ví dụ, không thể ghi đè một phương thức `public` bằng phương thức `protected`. Nếu phương thức cha khai báo ngoại lệ checked, phương thức ghi đè cũng phải tuân theo các giới hạn về ngoại lệ của quy tắc ghi đè.

Nếu phương thức abstract có kiểu trả về khác `void`, mọi nhánh thực thi cần trả về giá trị tương thích. Nếu kiểu trả về là `void`, triển khai phải thực hiện hành động phù hợp và không trả về giá trị.

## 7. Cảnh báo vòng đời: constructor lớp cha gọi phương thức có thể ghi đè

Khi chạy `new AbstractClass(...) { ... }`, **constructor lớp cha chạy trước phần khởi tạo trường của lớp con ẩn danh**. Nếu constructor lớp cha gọi một phương thức có thể ghi đè, Java sẽ phân phối lời gọi đến phần triển khai lớp con, dù trạng thái riêng của lớp con chưa được khởi tạo đầy đủ.

Ví dụ sau cố ý mô tả một thiết kế nguy hiểm; đặt khai báo `Base` bên ngoài và câu lệnh tạo đối tượng trong một phương thức:

```java
abstract class Base {
    Base() { display(); }
    abstract void display();
}

Base instance = new Base() {
    private final String status = " ready ".trim();
    @Override void display() {
        System.out.println(status);
    }
};
```

Đầu ra là `null`, **không phải** `ready`: lời gọi `display()` xảy ra trong constructor `Base` trước khi trường `status` được gán. Phép gọi `trim()` khiến biểu thức khởi tạo chạy khi tạo đối tượng; nếu dùng `final String status = "ready"`, đây là hằng tại thời điểm biên dịch và trình biên dịch có thể *inline* giá trị, che khuất lỗi thứ tự khởi tạo. Đây là rủi ro của mọi lớp con, đặc biệt dễ bị bỏ sót khi lớp con được viết ngay trong biểu thức `new`. Tốt hơn, constructor lớp cha chỉ thiết lập trạng thái của mình; gọi các phương thức có thể ghi đè sau khi xây dựng đối tượng xong.

## 8. Ranh giới với lambda và biến bên ngoài

Anonymous subclass có `this` của chính đối tượng lớp con, có thể ghi đè nhiều phương thức và kế thừa trạng thái từ `Report`. Lambda không thể kế thừa abstract class, kể cả khi lớp cha chỉ có một phương thức abstract: kiểu đích của lambda phải là **functional interface**.

Khi thân lớp ẩn danh dùng biến cục bộ của phương thức chứa nó, biến phải `final` hoặc *effectively final*. Quy tắc này áp dụng cho **biến cục bộ được bắt giữ**, không ngăn lớp con có các trường instance riêng. Nếu anonymous class nằm trong instance method và cần đối tượng bao ngoài, dùng `Outer.this` khi có enclosing instance thích hợp.

## 9. Khi nào nên dùng anonymous subclass?

Cách này phù hợp khi:

- Cần một triển khai duy nhất, nhỏ và cục bộ cho một abstract class.
- Muốn tận dụng constructor, trường dữ liệu hoặc phương thức chung đã được định nghĩa trong lớp cơ sở.
- Cần ghi đè một hoặc nhiều phương thức cho một tình huống cụ thể.
- Việc tạo một lớp có tên riêng sẽ làm tăng số lượng lớp mà không đem lại lợi ích tái sử dụng rõ ràng.

Hãy cân nhắc tạo một lớp con có tên nếu phần triển khai dài, có nhiều trạng thái hoặc quy tắc nghiệp vụ, cần được tái sử dụng ở nhiều nơi, hoặc cần được kiểm thử và đọc hiểu độc lập. Một lớp có tên thường giúp đặt tên cho ý định của hành vi và giảm độ phức tạp ở nơi khởi tạo.

Anonymous subclass cũng không phải lựa chọn tốt nếu phần thân trở thành một khối mã dài với nhiều trách nhiệm. Trong trường hợp đó, tách logic thành các phương thức hoặc một lớp riêng sẽ làm cấu trúc rõ ràng hơn.

## 10. Lỗi thường gặp

- **Không triển khai đủ phương thức abstract:** kiểm tra toàn bộ phương thức trừu tượng chưa được triển khai trong cây kế thừa. Nếu còn thiếu, trình biên dịch báo lỗi.
- **Gọi constructor không tồn tại hoặc không truy cập được:** truyền đối số phù hợp và kiểm tra mức truy cập của constructor lớp cha.
- **Quên dấu chấm phẩy sau biểu thức tạo đối tượng:** câu lệnh gán biến cần kết thúc bằng dấu `;` sau dấu ngoặc nhọn.
- **Sai chữ ký khi ghi đè:** thêm `@Override` và kiểm tra tên, tham số, kiểu trả về cùng mức truy cập.
- **Gán lại biến cục bộ được sử dụng bên trong lớp ẩn danh:** giữ biến `final`/effectively final hoặc thiết kế lại cách truyền dữ liệu.
- **Hiểu nhầm kiểu đối tượng:** biến kiểu abstract class chỉ cho phép gọi các thành viên có thể truy cập qua kiểu khai báo; phương thức được ghi đè sẽ được phân giải khi chạy.
- **Dùng lambda để kế thừa abstract class:** lambda chỉ nhắm tới functional interface. Dùng anonymous subclass nếu cần kế thừa một lớp.
- **Để lớp ẩn danh quá phức tạp:** chuyển triển khai thành lớp có tên khi cần tái sử dụng, kiểm thử hoặc thể hiện nghiệp vụ rõ ràng.

## 11. Quy trình thực hiện

1. Xác định abstract class cần kế thừa và các phương thức trừu tượng chưa được triển khai.
2. Kiểm tra constructor lớp cha, tham số cần truyền và quyền truy cập của constructor đó.
3. Viết `new AbstractClass(arguments) { ... }` và triển khai mọi phương thức trừu tượng bắt buộc.
4. Dùng `@Override` để xác minh các phương thức đang ghi đè đúng chữ ký.
5. Gán đối tượng vào tham chiếu kiểu abstract class hoặc truyền trực tiếp cho API phù hợp.
6. Biên dịch bằng `javac`, chạy chương trình và kiểm tra đầu ra.
7. Nếu phần thân lớn hoặc cần tái sử dụng, cân nhắc chuyển thành lớp con có tên.

Anonymous subclass là cách Java tạo một lớp con cụ thể ngay tại nơi cần đối tượng. Nó cho phép triển khai phương thức trừu tượng, sử dụng trạng thái và hành vi chung của abstract class, đồng thời tận dụng đa hình mà không cần khai báo một lớp con có tên riêng.