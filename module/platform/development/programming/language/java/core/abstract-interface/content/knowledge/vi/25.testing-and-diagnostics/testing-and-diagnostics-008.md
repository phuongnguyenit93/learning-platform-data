# Phân biệt lỗi biên dịch với AbstractMethodError, InstantiationError và linkage error

Khi làm việc với abstract class và interface trong Java, cần phân biệt lỗi mà trình biên dịch phát hiện từ mã nguồn với lỗi liên kết xảy ra khi JVM chạy bytecode. Hai nhóm lỗi có thể xuất phát từ vấn đề thiết kế tương tự, nhưng thời điểm phát hiện và cách chẩn đoán khác nhau.

- **Lỗi biên dịch (compile-time error):** `javac` không thể tạo bytecode hợp lệ từ mã nguồn, chẳng hạn lớp concrete chưa triển khai đủ phương thức abstract hoặc chương trình cố khởi tạo trực tiếp một abstract class.
- **`AbstractMethodError`:** JVM đang thực thi lời gọi phương thức nhưng lớp thực tế không có phần triển khai cụ thể cần thiết cho phương thức đã được phân giải. Trường hợp phổ biến là các class được biên dịch ở những thời điểm hoặc với phiên bản API khác nhau.
- **`InstantiationError`:** bytecode cố tạo instance của một lớp mà phiên bản lớp JVM đang nạp là abstract. Mã nguồn mới được biên dịch thông thường sẽ bị từ chối trước khi tạo bytecode như vậy; lỗi này thường gợi ý sự không khớp giữa các phiên bản class.
- **`LinkageError`:** nhóm lỗi cấp thấp hơn xảy ra khi JVM nạp, liên kết hoặc sử dụng các kiểu không tương thích. `AbstractMethodError` và `InstantiationError` đều thuộc nhánh `LinkageError`.

Nguyên tắc chẩn đoán quan trọng là kiểm tra **bytecode nào đã được biên dịch với phiên bản API nào, và phiên bản class nào thực sự được JVM nạp khi chạy**. Không nên xem các lỗi runtime này như lỗi cú pháp thông thường hoặc cố sửa bằng cách thêm một phương thức ngẫu nhiên mà chưa xác định nguyên nhân.

## 1. Bức tranh tổng quan: lỗi xuất hiện ở giai đoạn nào?

Một chương trình Java thường đi qua các giai đoạn: biên dịch mã nguồn, nạp lớp, liên kết và khởi tạo lớp, sau đó thực thi các câu lệnh. Các giai đoạn này liên quan nhau nhưng không giống nhau.

| Loại lỗi | Thời điểm thường gặp | Ví dụ điển hình |
|---|---|---|
| Lỗi biên dịch | Khi chạy `javac` | Khởi tạo abstract class; lớp concrete bỏ sót phương thức abstract |
| `AbstractMethodError` | Khi lời gọi phương thức được thực thi | Bytecode mong đợi phương thức nhưng lớp thực tế không cung cấp implementation |
| `InstantiationError` | Khi lệnh tạo instance được thực thi | Bytecode dùng `new` với lớp nay đã là abstract |
| `NoSuchMethodError` | Khi JVM phân giải lời gọi phương thức | Mã đã biên dịch gọi phương thức không còn trong phiên bản thư viện đang chạy |
| `NoClassDefFoundError` | Khi JVM cần một class nhưng không thể sử dụng định nghĩa cần thiết | Class có lúc biên dịch nhưng thiếu lúc chạy, hoặc khởi tạo lớp trước đó thất bại |
| `IncompatibleClassChangeError` | Khi loại hoặc cấu trúc thành viên đã đổi theo cách bytecode không mong đợi | Thành viên hoặc kiểu thay đổi không tương thích |
| `VerifyError` | Khi bytecode không vượt qua kiểm tra xác minh | Bytecode không hợp lệ hoặc không đáp ứng ràng buộc của JVM |

Bảng này chỉ ra thời điểm thường gặp, không phải mọi đường đi có thể xảy ra. Một số lỗi liên kết được phát hiện khi lớp được nạp hoặc khi một thành viên lần đầu được sử dụng, nên thời điểm chính xác phụ thuộc vào bytecode và cách JVM thực hiện việc nạp, phân giải.

## 2. Lỗi biên dịch liên quan đến abstract class và interface

Trình biên dịch kiểm tra các quy tắc ngôn ngữ dựa trên mã nguồn và những định nghĩa kiểu nhìn thấy trên classpath lúc biên dịch.

### Khởi tạo abstract class trực tiếp

Ví dụ sau không biên dịch được:

~~~java
abstract class Shape {
    abstract double area();
}

class Demo {
    public static void main(String[] args) {
        Shape shape = new Shape(); // Lỗi biên dịch
    }
}
~~~

Abstract class có thể chứa phương thức chưa triển khai, vì vậy không thể tạo instance trực tiếp của nó. Hãy tạo một lớp con concrete và triển khai các phương thức abstract:

~~~java
abstract class Shape {
    abstract double area();
}

final class Circle extends Shape {
    private final double radius;

    Circle(double radius) {
        this.radius = radius;
    }

    @Override
    double area() {
        return Math.PI * radius * radius;
    }
}

public class ShapeDemo {
    public static void main(String[] args) {
        Shape shape = new Circle(2.0);
        System.out.printf("%.2f%n", shape.area());
    }
}
~~~

Lưu mã trong **ShapeDemo.java**, biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac ShapeDemo.java
java ShapeDemo
~~~

Kết quả stdout:

~~~text
12.57
~~~

Biến có kiểu tham chiếu `Shape` vẫn có thể trỏ đến đối tượng `Circle`. Điều bị cấm là tạo instance trực tiếp từ abstract class, không phải sử dụng abstract class làm kiểu tham chiếu.

### Lớp concrete chưa triển khai đủ phương thức abstract

~~~java
abstract class Shape {
    abstract double area();
}

class Square extends Shape {
    // Thiếu area() nên lớp concrete này không biên dịch được.
}
~~~

Để hợp lệ, `Square` phải triển khai `area()` hoặc bản thân `Square` phải được khai báo `abstract`. Trình biên dịch thường báo rằng lớp không abstract chưa ghi đè phương thức abstract trong lớp cha.

### Chữ ký override không hợp lệ

~~~java
abstract class Reader {
    abstract String read();
}

class FileReaderImpl extends Reader {
    @Override
    int read() { // Lỗi: kiểu trả về không tương thích
        return 1;
    }
}
~~~

Một lỗi chữ ký như vậy được phát hiện lúc biên dịch. Với kiểu trả về tham chiếu, Java có cho phép kiểu trả về hiệp biến (covariant return type) trong một số trường hợp, nhưng kiểu trả về nguyên thủy phải khớp; các quy tắc override còn bao gồm mức truy cập và ngoại lệ checked.

Các ví dụ này khác về bản chất với `AbstractMethodError`: khi source code nhìn thấy đầy đủ và nhất quán, `javac` ngăn các lỗi hợp đồng thông thường trước khi chương trình chạy.

## 3. LinkageError là gì?

`java.lang.LinkageError` là một lớp `Error` dành cho các vấn đề liên kết giữa những định nghĩa kiểu hoặc thành phần mà JVM cần sử dụng. Những vấn đề này thường xuất hiện khi bytecode được biên dịch với một phiên bản thư viện nhưng chạy với phiên bản khác, hoặc khi classpath chứa các phiên bản không tương thích.

Một phần quan trọng của hệ phân cấp:

~~~text
java.lang.Error
└── java.lang.LinkageError
    └── java.lang.IncompatibleClassChangeError
        ├── java.lang.AbstractMethodError
        └── java.lang.InstantiationError
~~~

Ngoài nhánh này còn có những loại linkage error khác, ví dụ `NoSuchMethodError`, `NoSuchFieldError`, `NoClassDefFoundError` và `VerifyError` nằm trong các nhánh liên quan của `LinkageError`. Không phải mọi lỗi runtime đều là linkage error: `NullPointerException`, `IllegalArgumentException` hay `ClassCastException` có nguyên nhân và hệ phân cấp khác.

Vì `LinkageError` là `Error`, thông thường không nên bắt chung nó để tiếp tục chạy như thể đó là một lỗi nghiệp vụ có thể phục hồi. Trong mã ứng dụng, cách phù hợp thường là chẩn đoán và sửa classpath, phiên bản dependency hoặc tính tương thích của bytecode. Bắt một loại lỗi cụ thể có thể hữu ích trong chương trình minh họa hoặc công cụ chẩn đoán, nhưng không thay thế việc sửa nguyên nhân.

## 4. AbstractMethodError: lời gọi không tìm được implementation cụ thể

`AbstractMethodError` là một lớp con của `IncompatibleClassChangeError`. Lỗi có thể xuất hiện khi mã đã được biên dịch dựa trên một hợp đồng phương thức, nhưng lớp thực tế lúc chạy không cung cấp implementation cụ thể mà lời gọi yêu cầu.

Một tình huống thường gặp là **binary incompatibility** (không tương thích nhị phân): phiên bản API thay đổi sau khi lớp triển khai đã được biên dịch, nhưng lớp triển khai không được biên dịch lại. Ví dụ, một abstract class được bổ sung phương thức abstract mới. Lớp con cũ vẫn có thể được JVM nạp trong một số trường hợp, nhưng khi mã mới gọi phương thức mới trên instance của lớp con cũ, JVM có thể ném `AbstractMethodError`.

Điều này khác với việc biên dịch toàn bộ source code hiện tại. Nếu lớp con được biên dịch lại với abstract method mới mà không triển khai nó và vẫn được khai báo concrete, `javac` sẽ từ chối chương trình. Runtime error xuất hiện vì bytecode cũ không được kiểm tra lại như một lần biên dịch source code mới với toàn bộ định nghĩa hiện tại.

## 5. Tái hiện AbstractMethodError bằng hai phiên bản API

Ví dụ này cố ý tạo ra hai phiên bản của cùng một abstract class để minh họa sự không khớp giữa API mới và lớp triển khai cũ. Không dùng cách bố trí nhiều phiên bản như vậy trong ứng dụng bình thường; đây là bài thực hành chẩn đoán.

Cấu trúc thư mục:

~~~text
abstract-method-demo/
├── src-v1/
│   └── demo/
│       ├── Base.java
│       └── Impl.java
├── src-v2/
│   └── demo/
│       ├── Base.java
│       └── Client.java
└── build/
~~~

Phiên bản 1, tệp **src-v1/demo/Base.java**:

~~~java
package demo;

public abstract class Base {
    public abstract void run();
}
~~~

Phiên bản 1, tệp **src-v1/demo/Impl.java**:

~~~java
package demo;

public final class Impl extends Base {
    @Override
    public void run() {
        System.out.println("old run");
    }
}
~~~

Biên dịch API và implementation cũ:

~~~bash
javac -d build/v1 src-v1/demo/Base.java src-v1/demo/Impl.java
~~~

Giờ API phiên bản 2 thêm một phương thức abstract mới. Tệp **src-v2/demo/Base.java**:

~~~java
package demo;

public abstract class Base {
    public abstract void run();
    public abstract void close();
}
~~~

Tệp **src-v2/demo/Client.java**:

~~~java
package demo;

public final class Client {
    public static void main(String[] args) throws ReflectiveOperationException {
        Base target = (Base) Class.forName("demo.Impl")
                .getDeclaredConstructor()
                .newInstance();

        try {
            target.close();
        } catch (AbstractMethodError error) {
            System.out.println(error.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch API phiên bản 2 và client bằng API mới:

~~~bash
javac -d build/v2 src-v2/demo/Base.java
javac -cp build/v2 -d build/v2 src-v2/demo/Client.java
~~~

Chạy với API mới đứng trước và implementation cũ đứng sau trên classpath. Trên Linux/macOS, dấu phân cách classpath là dấu hai chấm:

~~~bash
java -cp "build/v2:build/v1" demo.Client
~~~

Trên Windows, dấu phân cách classpath là dấu chấm phẩy:

~~~powershell
java -cp "build/v2;build/v1" demo.Client
~~~

Kết quả stdout:

~~~text
AbstractMethodError
~~~

Trong lần chạy này, JVM nạp `demo.Base` phiên bản 2 nhưng nạp `demo.Impl` đã biên dịch với phiên bản 1. `Impl` có implementation cho `run()` nhưng không có implementation cho `close()`. Lệnh gọi `target.close()` vì vậy gây ra `AbstractMethodError`, được ví dụ bắt riêng để chỉ in tên lớp lỗi.

Cách sửa thực tế là đồng bộ phiên bản API và các implementation: triển khai phương thức mới, biên dịch lại các module phụ thuộc, kiểm tra artifact được đóng gói và loại bỏ bản class cũ khỏi classpath. Không nên chỉ bắt `AbstractMethodError` rồi bỏ qua lời gọi, vì hành vi nghiệp vụ cần thiết có thể chưa được thực hiện.

## 6. InstantiationError: bytecode tạo instance của lớp nay đã abstract

`InstantiationError` cũng là một lớp con của `IncompatibleClassChangeError`. Nó có thể xảy ra khi bytecode chứa thao tác tạo instance cho một lớp, nhưng định nghĩa mà JVM nạp lúc chạy đã trở thành abstract.

Trong source code được biên dịch với định nghĩa mới, câu lệnh `new SomeAbstractClass()` không hợp lệ và bị `javac` từ chối. Nhưng nếu một client được biên dịch lúc lớp còn concrete, bytecode cũ vẫn có thể chứa lệnh `new`. Khi runtime thay định nghĩa lớp đó bằng một phiên bản abstract không tương thích, lệnh tạo instance có thể ném `InstantiationError`.

## 7. Tái hiện InstantiationError với phiên bản lớp không khớp

Phiên bản 1, tệp **src-v1/demo/Product.java**:

~~~java
package demo;

public class Product {
    public Product() {
    }
}
~~~

Phiên bản 1, tệp **src-v1/demo/Client.java**:

~~~java
package demo;

public final class Client {
    public static void main(String[] args) {
        try {
            new Product();
            System.out.println("created");
        } catch (InstantiationError error) {
            System.out.println(error.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch cả client và lớp concrete ban đầu:

~~~bash
javac -d build/v1 src-v1/demo/Product.java src-v1/demo/Client.java
~~~

Phiên bản 2, thay **src-v2/demo/Product.java** bằng một abstract class:

~~~java
package demo;

public abstract class Product {
    public Product() {
    }

    public abstract void execute();
}
~~~

Biên dịch phiên bản lớp mới vào thư mục riêng:

~~~bash
javac -d build/v2 src-v2/demo/Product.java
~~~

Chạy client cũ với lớp mới đứng trước trên classpath. Trên Linux/macOS:

~~~bash
java -cp "build/v2:build/v1" demo.Client
~~~

Trên Windows:

~~~powershell
java -cp "build/v2;build/v1" demo.Client
~~~

Kết quả stdout:

~~~text
InstantiationError
~~~

Client được biên dịch khi `Product` còn là lớp concrete, vì vậy bytecode của nó có thao tác tạo instance. Khi chạy, JVM tìm thấy `Product` phiên bản 2, hiện là abstract, và không thể thực hiện thao tác đó.

Để khắc phục, hãy đồng bộ client và dependency với API hiện tại. Nếu `Product` được chuyển thành abstract theo chủ đích, client phải tạo một lớp con concrete thích hợp thay vì tiếp tục khởi tạo `Product` trực tiếp. Với bản phát hành thông thường, cần build và triển khai các artifact tương thích cùng nhau, tránh để một phiên bản class cũ được ưu tiên trên classpath.

## 8. Những linkage error khác cần phân biệt

Không phải mọi lỗi do phiên bản thư viện không khớp đều là `AbstractMethodError` hoặc `InstantiationError`.

- **`NoSuchMethodError`:** bytecode gọi một phương thức mà định nghĩa lớp/interface đang chạy không có chữ ký được phân giải. Hãy kiểm tra thay đổi API, phiên bản dependency và các bản JAR trùng lặp.
- **`NoSuchFieldError`:** bytecode tham chiếu đến một trường đã không còn hoặc không còn phù hợp trong lớp lúc chạy.
- **`NoClassDefFoundError`:** JVM không thể sử dụng định nghĩa lớp cần thiết khi chạy. Có thể thiếu class trên runtime classpath, hoặc lần khởi tạo trước đó của lớp thất bại. Trường hợp thiếu class thường cần đối chiếu với `ClassNotFoundException`, nhưng hai lỗi không đồng nghĩa.
- **`IncompatibleClassChangeError`:** bytecode mong đợi một cấu trúc kiểu hoặc thành viên khác với cấu trúc được cung cấp lúc chạy; các lớp con cụ thể bao gồm `AbstractMethodError` và `InstantiationError`.
- **`VerifyError`:** bytecode không vượt qua xác minh của JVM, thường vì bytecode không hợp lệ hoặc có vấn đề tương thích ở mức bytecode.
- **`ExceptionInInitializerError`:** quá trình khởi tạo tĩnh của lớp thất bại do ngoại lệ; đây cũng là một lớp con của `LinkageError`, nhưng thường cần điều tra lỗi bên trong static initializer thay vì chỉ tìm chữ ký API bị thiếu.

Thông báo và stack trace cung cấp manh mối ban đầu, nhưng cần kiểm tra đúng class và JAR mà runtime thực sự nạp. Dòng đầu stack trace thường chỉ ra nơi lỗi được quan sát; nguyên nhân gốc có thể nằm ở dependency hoặc artifact đã được nạp trước đó.

## 9. Vì sao mã biên dịch được nhưng chạy lại lỗi?

Trình biên dịch và JVM có thể sử dụng các định nghĩa lớp khác nhau vào hai thời điểm khác nhau. Ví dụ:

1. Thư viện phiên bản 1 khai báo một abstract class hoặc interface.
2. Một module được biên dịch với phiên bản 1 và tạo ra bytecode.
3. Thư viện được nâng cấp lên phiên bản 2, có thay đổi không tương thích nhị phân.
4. Module cũ vẫn được triển khai mà không biên dịch lại.
5. Khi đường thực thi đi đến thành viên bị ảnh hưởng, JVM phát hiện sự không khớp và có thể ném linkage error.

Các nguồn gốc thường gặp gồm:

- Một JAR cũ bị đóng gói cùng JAR mới.
- Thứ tự classpath khiến JVM nạp phiên bản không mong muốn.
- Một module được biên dịch lại nhưng module triển khai chưa được cập nhật.
- Thay đổi một phương thức concrete thành abstract hoặc bổ sung hợp đồng abstract mà các lớp triển khai cũ chưa đáp ứng.
- Thay đổi loại thành viên hoặc chữ ký phương thức mà bytecode đã biên dịch phụ thuộc vào.
- Môi trường build và môi trường triển khai dùng tập dependency khác nhau.

Không phải mọi thay đổi API đều gây lỗi linkage. Java có những quy tắc tương thích nhị phân cụ thể, và kết quả phụ thuộc vào loại thay đổi, kiểu thành viên và đường thực thi. Khi một lỗi xuất hiện, hãy xác minh trường hợp thực tế thay vì kết luận chỉ từ tên loại lỗi.

## 10. Quy trình chẩn đoán có hệ thống

### Bước 1: Xác định chính xác loại lỗi

Đọc tên lớp ngoại lệ/lỗi đầu tiên trong stack trace và xác định lỗi xảy ra trong lúc biên dịch hay lúc chạy. Nếu `javac` báo lỗi, hãy giải quyết mã nguồn và hợp đồng kiểu. Nếu JVM ném `LinkageError`, tập trung vào bytecode và các phiên bản class đang được sử dụng.

### Bước 2: Tìm điểm sử dụng đầu tiên bị lỗi

Với `AbstractMethodError`, tìm lời gọi phương thức cụ thể và xác định kiểu khai báo cùng kiểu thực tế của đối tượng. Với `InstantiationError`, tìm lệnh `new` hoặc đường tạo instance liên quan. Dùng stack trace để thu hẹp phạm vi, nhưng vẫn kiểm tra nguồn gốc dependency.

### Bước 3: Xác minh phiên bản class runtime

Kiểm tra runtime classpath, thứ tự JAR, artifact được đóng gói và phiên bản thư viện ở môi trường triển khai. Trong chương trình chẩn đoán, có thể in vị trí class được nạp:

~~~java
System.out.println(
    SomeType.class.getProtectionDomain()
        .getCodeSource()
        .getLocation()
);
~~~

Đoạn này chỉ dùng khi `CodeSource` và thông tin lớp khả dụng; một số môi trường có thể trả về `null`. Hãy xác định đúng kiểu đang nghi ngờ và kiểm tra các lớp liên quan, không chỉ một lớp duy nhất.

### Bước 4: So sánh hợp đồng giữa phiên bản build và runtime

Kiểm tra phương thức abstract, mức truy cập, chữ ký, kiểu trả về, trạng thái abstract/concrete và thay đổi API. Xác định implementation nào được biên dịch với hợp đồng cũ và liệu nó có được triển khai cùng API mới hay không.

### Bước 5: Build sạch và triển khai đồng bộ

Xóa output build cũ thông qua quy trình build chuẩn của dự án, biên dịch lại các module liên quan và tạo artifact nhất quán. Tránh tự xóa ngẫu nhiên các file trong môi trường đang chạy trước khi xác định cách triển khai. Sau đó chạy lại trong môi trường có classpath tương ứng với production.

### Bước 6: Thêm kiểm thử tương thích

Nếu thư viện được nhiều module sử dụng, thêm kiểm thử tích hợp hoặc kiểm tra tương thích API để phát hiện các thay đổi làm implementation cũ không còn hoạt động. Kiểm thử phải sử dụng cùng cách đóng gói và dependency resolution với ứng dụng thật; chỉ chạy unit test trong một classpath khác có thể không tái hiện vấn đề.

## 11. Cách xử lý theo loại lỗi

| Phát hiện | Hướng xử lý |
|---|---|
| Lỗi biên dịch do lớp concrete bỏ sót abstract method | Triển khai đúng phương thức hoặc khai báo lớp là abstract nếu thiết kế yêu cầu |
| Lỗi biên dịch do khởi tạo abstract class | Khởi tạo lớp con concrete hoặc dùng factory trả về một implementation phù hợp |
| `AbstractMethodError` sau khi nâng cấp dependency | Tìm implementation cũ, đồng bộ phiên bản, triển khai phương thức mới và build lại các module liên quan |
| `InstantiationError` sau khi API đổi từ concrete sang abstract | Cập nhật client để tạo lớp con concrete; kiểm tra classpath và artifact cũ |
| `NoSuchMethodError` hoặc `NoSuchFieldError` | So sánh chữ ký/thành viên trong bản build với bản runtime và loại bỏ dependency không tương thích |
| `NoClassDefFoundError` | Kiểm tra classpath runtime và nguyên nhân khởi tạo lớp thất bại nếu có |
| `VerifyError` | Xác minh nguồn bytecode, công cụ biến đổi bytecode và tính nhất quán của các artifact |

Tránh giải quyết các lỗi này bằng cách thêm catch tổng quát quanh toàn bộ ứng dụng, bỏ qua lời gọi hoặc chỉ thay đổi mã nguồn ở một module. Nếu vấn đề là binary incompatibility, mã nguồn đã sửa nhưng artifact runtime cũ vẫn còn trên classpath thì lỗi có thể tiếp tục xảy ra.

## 12. Các ngộ nhận thường gặp

- **“AbstractMethodError nghĩa là tôi quên override.”** Nếu toàn bộ source code hiện tại được biên dịch cùng nhau, việc thiếu override trong lớp concrete thường bị phát hiện khi biên dịch. Khi gặp lỗi runtime này, hãy kiểm tra phiên bản bytecode và API.
- **“InstantiationError giống lỗi `new AbstractClass()` trong source.”** Source code đó bị `javac` từ chối. `InstantiationError` thường cho thấy bytecode cũ đang chạy với một định nghĩa lớp mới đã trở thành abstract.
- **“Mọi LinkageError đều do thiếu JAR.”** Thiếu class là một nguyên nhân, nhưng thay đổi chữ ký, thay đổi cấu trúc kiểu hoặc phiên bản class không tương thích cũng có thể gây lỗi.
- **“Build thành công nghĩa là runtime chắc chắn tương thích.”** Build chỉ kiểm tra theo các định nghĩa được dùng lúc build. Môi trường chạy có thể nạp các artifact khác.
- **“Có thể bắt LinkageError rồi tiếp tục bình thường.”** Tiếp tục sau khi hợp đồng kiểu bị phá vỡ có thể khiến thao tác nghiệp vụ không thực hiện hoặc trạng thái chương trình không đáng tin cậy.
- **“Chỉ cần kiểm tra phiên bản trong file build.”** Cần xác minh artifact thực tế được đóng gói và nạp lúc chạy, vì classpath có thể chứa nhiều phiên bản hoặc nguồn lớp khác nhau.

## 13. Checklist khi gặp lỗi abstract/linkage

- Xác nhận lỗi là compile-time error hay lỗi runtime.
- Ghi lại loại lỗi và vị trí lời gọi trong stack trace.
- Với `AbstractMethodError`, xác định phương thức được gọi, kiểu runtime của đối tượng và implementation đang được nạp.
- Với `InstantiationError`, xác định lớp bị khởi tạo và kiểm tra xem phiên bản runtime có còn concrete không.
- Kiểm tra thứ tự classpath, dependency tree và các JAR trùng phiên bản.
- So sánh API được dùng khi biên dịch với API thực tế lúc chạy.
- Đồng bộ phiên bản và build lại các module phụ thuộc; chạy lại kiểm thử trong môi trường triển khai tương đương.
- Ghi nhận bài học vào quy trình phát hành để tránh trộn artifact cũ và mới.

Phân biệt lỗi biên dịch với `AbstractMethodError`, `InstantiationError` và các `LinkageError` giúp chọn đúng hướng điều tra. Lỗi biên dịch thường chỉ ra source code chưa thỏa hợp đồng kiểu hiện tại; linkage error thường yêu cầu kiểm tra quan hệ giữa bytecode đã biên dịch và định nghĩa lớp thực tế lúc chạy. Hãy sửa tính nhất quán của API, implementation và artifact triển khai, thay vì chỉ xử lý biểu hiện của lỗi.